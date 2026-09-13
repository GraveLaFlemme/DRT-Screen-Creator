from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QWidget

from .topology import exclude_window_from_capture


class ToastWidget(QWidget):
    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._label = QLabel()
        self._label.setWordWrap(True)
        self._label.setMinimumWidth(300)
        self._label.setMaximumWidth(460)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, message: str, success: bool, duration_ms: int = 2200) -> None:
        color = "#a3d12d" if success else "#ef6655"
        background = "#263017" if success else "#3a1f1b"
        icon = "✓" if success else "!"
        self._label.setText(f"{icon}  {message}")
        self._label.setStyleSheet(
            f"QLabel {{ background: {background}; color: #f6f0e4; border: 2px solid {color}; "
            "border-radius: 11px; padding: 13px 16px; font-weight: 700; }}"
        )
        self.adjustSize()
        screen = QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.move(area.right() - self.width() - 24, area.bottom() - self.height() - 24)
        self.show()
        self.raise_()
        exclude_window_from_capture(int(self.winId()))
        self._timer.start(duration_ms)
