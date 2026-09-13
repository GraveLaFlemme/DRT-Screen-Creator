from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPainterPath, QPen, QScreen
from PySide6.QtWidgets import QApplication, QWidget

from .models import CaptureRegion, MonitorInfo
from .topology import get_cursor_position, virtual_bounds


MINIMUM_REGION_SIZE = 8
HANDLE_TOLERANCE = 14


class RegionSelectionController(QObject):
    selected = Signal(object)
    cancelled = Signal()

    def __init__(
        self,
        monitors: list[MonitorInfo],
        existing_region: CaptureRegion | None = None,
        parent: QObject | None = None,
        single_click_to_confirm: bool = False,
    ) -> None:
        super().__init__(parent)
        self.monitors = monitors
        self.bounds = virtual_bounds(monitors)
        self.region = existing_region
        self.single_click_to_confirm = single_click_to_confirm
        self._overlays: list[MonitorOverlay] = []
        self._action = ""
        self._pointer_moved = False
        self._start_point = (0, 0)
        self._original_region: CaptureRegion | None = None
        self._mouse_owner: MonitorOverlay | None = None
        self._closed = False

    def begin(self) -> None:
        screens = QApplication.screens()
        unused_screens = list(screens)
        for monitor in self.monitors:
            screen = self._match_screen(monitor, unused_screens)
            if screen is None:
                continue
            unused_screens.remove(screen)
            overlay = MonitorOverlay(self, monitor, screen)
            self._overlays.append(overlay)
            overlay.show()
            overlay.raise_()

        if not self._overlays:
            self.cancel()
            return
        focus_overlay = next((item for item in self._overlays if item.monitor.primary), self._overlays[0])
        focus_overlay.activateWindow()
        focus_overlay.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        focus_overlay.grabKeyboard()
        QApplication.setOverrideCursor(Qt.CursorShape.CrossCursor)

    @staticmethod
    def _match_screen(monitor: MonitorInfo, screens: list[QScreen]) -> QScreen | None:
        if not screens:
            return None
        exact = next(
            (screen for screen in screens if screen.name().casefold() == monitor.name.casefold()),
            None,
        )
        if exact:
            return exact
        position_match = next(
            (
                screen
                for screen in screens
                if screen.geometry().left() == monitor.left and screen.geometry().top() == monitor.top
            ),
            None,
        )
        return position_match or screens[0]

    def mouse_press(self, owner: "MonitorOverlay", point: tuple[int, int]) -> None:
        self._mouse_owner = owner
        owner.grabMouse()
        self._start_point = point
        self._original_region = self.region
        self._pointer_moved = False
        hit = self._hit_test(point)
        if hit:
            self._action = hit
        elif self.region and self.region.contains(*point):
            self._action = "move"
        else:
            self._action = "new"
            self.region = CaptureRegion(point[0], point[1], 1, 1)
        self._update_overlays()

    def mouse_move(self, point: tuple[int, int]) -> None:
        if not self._action:
            return
        x = min(max(point[0], self.bounds.left), self.bounds.right - 1)
        y = min(max(point[1], self.bounds.top), self.bounds.bottom - 1)
        start_x, start_y = self._start_point
        if abs(x - start_x) >= 3 or abs(y - start_y) >= 3:
            self._pointer_moved = True

        if self._action == "new":
            left = min(start_x, x)
            top = min(start_y, y)
            right = max(start_x, x) + 1
            bottom = max(start_y, y) + 1
            self.region = CaptureRegion(left, top, right - left, bottom - top)
        elif self._action == "move" and self._original_region:
            delta_x = x - start_x
            delta_y = y - start_y
            region = self._original_region
            left = min(max(region.left + delta_x, self.bounds.left), self.bounds.right - region.width)
            top = min(max(region.top + delta_y, self.bounds.top), self.bounds.bottom - region.height)
            self.region = replace(region, left=left, top=top)
        elif self._original_region:
            self.region = self._resize_region(self._original_region, self._action, x - start_x, y - start_y)
        self._update_overlays()

    def mouse_release(self) -> None:
        confirm_selection = (
            self.single_click_to_confirm
            and self._action == "move"
            and not self._pointer_moved
        )
        if self._mouse_owner:
            self._mouse_owner.releaseMouse()
        self._mouse_owner = None
        self._action = ""
        self._original_region = None
        self._update_overlays()
        if confirm_selection:
            self.confirm()

    def confirm(self) -> None:
        if not self.region or self.region.width < MINIMUM_REGION_SIZE or self.region.height < MINIMUM_REGION_SIZE:
            return
        region = self.region
        self._close_overlays()
        self.selected.emit(region)

    def cancel(self) -> None:
        self._close_overlays()
        self.cancelled.emit()

    def _close_overlays(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._mouse_owner:
            self._mouse_owner.releaseMouse()
        for overlay in self._overlays:
            overlay.releaseKeyboard()
            overlay.hide()
            overlay.deleteLater()
        self._overlays.clear()
        QApplication.restoreOverrideCursor()

    def _update_overlays(self) -> None:
        for overlay in self._overlays:
            overlay.update()

    def _hit_test(self, point: tuple[int, int]) -> str:
        if not self.region:
            return ""
        x, y = point
        region = self.region
        within_x = region.left - HANDLE_TOLERANCE <= x <= region.right + HANDLE_TOLERANCE
        within_y = region.top - HANDLE_TOLERANCE <= y <= region.bottom + HANDLE_TOLERANCE
        near_left = within_y and abs(x - region.left) <= HANDLE_TOLERANCE
        near_right = within_y and abs(x - region.right) <= HANDLE_TOLERANCE
        near_top = within_x and abs(y - region.top) <= HANDLE_TOLERANCE
        near_bottom = within_x and abs(y - region.bottom) <= HANDLE_TOLERANCE
        if near_left and near_top:
            return "nw"
        if near_right and near_top:
            return "ne"
        if near_right and near_bottom:
            return "se"
        if near_left and near_bottom:
            return "sw"
        if near_left:
            return "w"
        if near_right:
            return "e"
        if near_top:
            return "n"
        if near_bottom:
            return "s"
        return ""

    def _resize_region(self, region: CaptureRegion, handle: str, delta_x: int, delta_y: int) -> CaptureRegion:
        left, top, right, bottom = region.left, region.top, region.right, region.bottom
        if "w" in handle:
            left = min(right - MINIMUM_REGION_SIZE, max(self.bounds.left, region.left + delta_x))
        if "e" in handle:
            right = max(left + MINIMUM_REGION_SIZE, min(self.bounds.right, region.right + delta_x))
        if "n" in handle:
            top = min(bottom - MINIMUM_REGION_SIZE, max(self.bounds.top, region.top + delta_y))
        if "s" in handle:
            bottom = max(top + MINIMUM_REGION_SIZE, min(self.bounds.bottom, region.bottom + delta_y))
        return CaptureRegion(left, top, right - left, bottom - top)


class MonitorOverlay(QWidget):
    def __init__(self, controller: RegionSelectionController, monitor: MonitorInfo, screen: QScreen) -> None:
        super().__init__(None)
        self.controller = controller
        self.monitor = monitor
        self.screen = screen
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.winId()
        if self.windowHandle():
            self.windowHandle().setScreen(screen)
        self.setGeometry(screen.geometry())

    def paintEvent(self, _event) -> None:  # noqa: N802 - API Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        full_path = QPainterPath()
        full_path.addRect(QRectF(self.rect()))

        local_selection = self._local_selection_rect()
        if local_selection:
            hole_path = QPainterPath()
            hole_path.addRect(local_selection)
            painter.fillPath(full_path.subtracted(hole_path), QColor(12, 9, 6, 190))
            painter.fillRect(local_selection, QColor(241, 154, 40, 22))
            painter.setPen(QPen(QColor("#f19a28"), 3))
            painter.drawRect(local_selection.adjusted(1.5, 1.5, -1.5, -1.5))
            self._draw_handles(painter)
            self._draw_dimensions(painter, local_selection)
        else:
            painter.fillPath(full_path, QColor(12, 9, 6, 190))

        self._draw_instructions(painter)

    def _local_selection_rect(self) -> QRectF | None:
        region = self.controller.region
        if not region:
            return None
        overlap = region.intersection(self.monitor.region)
        if not overlap:
            return None
        scale_x = self.width() / self.monitor.width
        scale_y = self.height() / self.monitor.height
        return QRectF(
            (overlap.left - self.monitor.left) * scale_x,
            (overlap.top - self.monitor.top) * scale_y,
            overlap.width * scale_x,
            overlap.height * scale_y,
        )

    def _physical_to_local(self, x: int, y: int) -> QPointF:
        scale_x = self.width() / self.monitor.width
        scale_y = self.height() / self.monitor.height
        return QPointF((x - self.monitor.left) * scale_x, (y - self.monitor.top) * scale_y)

    def _draw_handles(self, painter: QPainter) -> None:
        region = self.controller.region
        if not region:
            return
        points = [
            (region.left, region.top),
            ((region.left + region.right) // 2, region.top),
            (region.right, region.top),
            (region.right, (region.top + region.bottom) // 2),
            (region.right, region.bottom),
            ((region.left + region.right) // 2, region.bottom),
            (region.left, region.bottom),
            (region.left, (region.top + region.bottom) // 2),
        ]
        painter.setPen(QPen(QColor("#3b2b1c"), 1))
        painter.setBrush(QColor("#f4c873"))
        for x, y in points:
            if (
                self.monitor.left - 1 <= x <= self.monitor.left + self.monitor.width + 1
                and self.monitor.top - 1 <= y <= self.monitor.top + self.monitor.height + 1
            ):
                point = self._physical_to_local(x, y)
                painter.drawRoundedRect(QRectF(point.x() - 5, point.y() - 5, 10, 10), 2, 2)

    def _draw_dimensions(self, painter: QPainter, selection: QRectF) -> None:
        region = self.controller.region
        if not region:
            return
        text = f"{region.width} × {region.height} px"
        box = QRectF(selection.left() + 8, selection.top() + 8, 170, 30)
        if box.right() > self.width() - 8:
            box.moveRight(self.width() - 8)
        if box.bottom() > self.height() - 8:
            box.moveBottom(self.height() - 8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(40, 29, 20, 230))
        painter.drawRoundedRect(box, 7, 7)
        painter.setPen(QColor("#f6f0e4"))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    def _draw_instructions(self, painter: QPainter) -> None:
        width = min(560, max(280, self.width() - 40))
        box = QRectF((self.width() - width) / 2, 24, width, 62)
        painter.setPen(QPen(QColor("#7a5f42"), 2))
        painter.setBrush(QColor(35, 26, 19, 238))
        painter.drawRoundedRect(box, 12, 12)
        painter.setPen(QColor("#f6f0e4"))
        painter.drawText(
            box.adjusted(14, 5, -14, -26),
            Qt.AlignmentFlag.AlignCenter,
            "Tracez, déplacez ou redimensionnez la zone",
        )
        painter.setPen(QColor("#c8b79a"))
        validation_hint = (
            "Clic dans la zone : valider"
            if self.controller.single_click_to_confirm
            else "Double-clic : valider"
        )
        painter.drawText(
            box.adjusted(14, 29, -14, -4),
            Qt.AlignmentFlag.AlignCenter,
            f"Entrée : valider  •  Échap : annuler  •  {validation_hint}",
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - API Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self.controller.mouse_press(self, get_cursor_position())
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - API Qt
        self.controller.mouse_move(get_cursor_position())
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - API Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self.controller.mouse_release()
            event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - API Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self.controller.confirm()
            event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - API Qt
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.controller.confirm()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.controller.cancel()
            event.accept()
        else:
            super().keyPressEvent(event)
