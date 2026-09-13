from __future__ import annotations

import logging
import os
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, QThreadPool, QTimer, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices, QIcon, QKeySequence, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
    QKeySequenceEdit,
)

from .capture import CaptureService
from .config import SettingsRepository
from .hotkey import GlobalHotkeyManager, InvalidHotkey, parse_hotkey
from .models import CaptureRegion, CaptureResult, CaptureSettings, MonitorInfo
from .naming import InvalidBaseName, capture_filename, find_next_index, sequence_key, validate_base_name
from .notifications import ToastWidget
from .selector import RegionSelectionController
from .sound import SuccessSound
from .topology import enumerate_monitors, region_coverage, region_is_visible, topology_fingerprint
from .workers import CaptureTask


LOGGER = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings_repository: SettingsRepository,
        hotkey_manager: GlobalHotkeyManager,
        app_icon: QIcon,
        logo_path: Path,
        success_sound: SuccessSound | None = None,
    ) -> None:
        super().__init__()
        self.settings_repository = settings_repository
        self.hotkey_manager = hotkey_manager
        self.settings = settings_repository.load()
        self.app_icon = app_icon
        self.logo_path = logo_path
        self.capture_service = CaptureService()
        self.success_sound = success_sound or SuccessSound()
        self.thread_pool = QThreadPool.globalInstance()
        self.toast = ToastWidget()
        self._capture_tasks: set[CaptureTask] = set()
        self._capture_in_progress = False
        self._armed = False
        self._quitting = False
        self._loading_ui = False
        self._selector: RegionSelectionController | None = None
        self._selector_restore_window = False
        self._restore_window_after_capture = False
        self._monitors: list[MonitorInfo] = []
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_settings)

        self.setWindowTitle("DRT Screen Creator")
        self.setWindowIcon(app_icon)
        self.setMinimumSize(780, 700)
        self.resize(860, 820)
        self._build_interface()
        self._build_tray()
        self._load_settings_into_interface()
        self.hotkey_manager.signals.activated.connect(self._capture_requested)
        self.hotkey_manager.signals.free_activated.connect(self._free_capture_requested)
        self._refresh_topology(initial=True)
        self._update_configuration_state()

    def _build_interface(self) -> None:
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        scroll_area.setWidget(container)
        self.setCentralWidget(scroll_area)

        root = QVBoxLayout(container)
        root.setContentsMargins(22, 20, 22, 22)
        root.setSpacing(14)

        header = QFrame()
        header.setObjectName("header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 14, 18, 14)
        logo = QLabel()
        pixmap = QPixmap(str(self.logo_path))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(58, 58, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        logo.setFixedSize(64, 64)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(logo)
        title_box = QVBoxLayout()
        title = QLabel("DRT Screen Creator")
        title.setObjectName("appTitle")
        subtitle = QLabel("Captures prédéfinies pour Dofus Retro Tools")
        subtitle.setObjectName("muted")
        title_box.addStretch()
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        title_box.addStretch()
        header_layout.addLayout(title_box, 1)
        self.status_label = QLabel("Non configuré")
        self.status_label.setObjectName("statusPill")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setMinimumWidth(132)
        header_layout.addWidget(self.status_label)
        root.addWidget(header)

        region_panel, region_layout = self._make_panel("1. Zone de capture", "Tracez une zone fixe sur votre bureau virtuel.")
        region_row = QHBoxLayout()
        self.region_value = QLabel("Aucune zone définie")
        self.region_value.setObjectName("valueLabel")
        self.region_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        region_row.addWidget(self.region_value, 1)
        self.region_button = QPushButton("Définir la zone")
        self.region_button.setObjectName("secondaryButton")
        self.region_button.clicked.connect(self._choose_region)
        region_row.addWidget(self.region_button)
        region_layout.addLayout(region_row)
        self.region_warning = QLabel()
        self.region_warning.setObjectName("warningText")
        self.region_warning.setWordWrap(True)
        self.region_warning.hide()
        region_layout.addWidget(self.region_warning)
        root.addWidget(region_panel)

        destination_panel, destination_layout = self._make_panel(
            "2. Destination et nom",
            "Le compteur reprend automatiquement après le plus grand numéro existant.",
        )
        folder_grid = QGridLayout()
        folder_grid.setHorizontalSpacing(10)
        folder_grid.setVerticalSpacing(10)
        folder_grid.addWidget(QLabel("Dossier"), 0, 0)
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Choisissez le dossier des captures…")
        self.output_edit.textChanged.connect(self._configuration_changed)
        folder_grid.addWidget(self.output_edit, 0, 1)
        self.folder_button = QPushButton("Parcourir")
        self.folder_button.setObjectName("secondaryButton")
        self.folder_button.clicked.connect(self._choose_folder)
        folder_grid.addWidget(self.folder_button, 0, 2)
        folder_grid.addWidget(QLabel("Nom de base"), 1, 0)
        self.base_name_edit = QLineEdit()
        self.base_name_edit.setPlaceholderText("Exemple : quête")
        self.base_name_edit.setMaxLength(120)
        self.base_name_edit.textChanged.connect(self._configuration_changed)
        folder_grid.addWidget(self.base_name_edit, 1, 1, 1, 2)
        folder_grid.addWidget(QLabel("Prochain fichier"), 2, 0)
        self.next_file_label = QLabel("—")
        self.next_file_label.setObjectName("filePreview")
        self.next_file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        folder_grid.addWidget(self.next_file_label, 2, 1, 1, 2)
        destination_layout.addLayout(folder_grid)
        root.addWidget(destination_panel)

        hotkey_panel, hotkey_layout = self._make_panel(
            "3. Raccourcis globaux",
            "La zone prédéfinie capture immédiatement. Pour la capture libre, tracez puis cliquez une fois dans la zone.",
        )
        hotkey_grid = QGridLayout()
        hotkey_grid.setHorizontalSpacing(10)
        hotkey_grid.setVerticalSpacing(10)
        hotkey_grid.addWidget(QLabel("Zone prédéfinie"), 0, 0)
        self.hotkey_edit = QKeySequenceEdit()
        self.hotkey_edit.setMaximumSequenceLength(1)
        self.hotkey_edit.setClearButtonEnabled(True)
        self.hotkey_edit.editingFinished.connect(self._configuration_changed)
        hotkey_grid.addWidget(self.hotkey_edit, 0, 1)
        hotkey_grid.addWidget(QLabel("Capture libre"), 1, 0)
        self.free_hotkey_edit = QKeySequenceEdit()
        self.free_hotkey_edit.setMaximumSequenceLength(1)
        self.free_hotkey_edit.setClearButtonEnabled(True)
        self.free_hotkey_edit.editingFinished.connect(self._configuration_changed)
        hotkey_grid.addWidget(self.free_hotkey_edit, 1, 1)
        hotkey_layout.addLayout(hotkey_grid)
        self.hotkey_error = QLabel()
        self.hotkey_error.setObjectName("errorText")
        self.hotkey_error.setWordWrap(True)
        self.hotkey_error.hide()
        hotkey_layout.addWidget(self.hotkey_error)
        root.addWidget(hotkey_panel)

        self.arm_button = QPushButton("Armer la capture")
        self.arm_button.setObjectName("primaryButton")
        self.arm_button.setMinimumHeight(52)
        self.arm_button.clicked.connect(self._toggle_armed)
        root.addWidget(self.arm_button)
        self.status_details = QLabel()
        self.status_details.setObjectName("statusDetails")
        self.status_details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_details.setWordWrap(True)
        root.addWidget(self.status_details)

        preview_panel, preview_layout = self._make_panel(
            "Dernière capture",
            "Aperçu chargé depuis le JPEG réellement enregistré.",
        )
        self.preview_label = QLabel("Aucune capture enregistrée")
        self.preview_label.setObjectName("preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(210)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        preview_layout.addWidget(self.preview_label)
        self.last_capture_details = QLabel("—")
        self.last_capture_details.setObjectName("muted")
        self.last_capture_details.setWordWrap(True)
        self.last_capture_details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        preview_layout.addWidget(self.last_capture_details)
        preview_actions = QHBoxLayout()
        self.open_image_button = QPushButton("Ouvrir l’image")
        self.open_image_button.setObjectName("secondaryButton")
        self.open_image_button.clicked.connect(self._open_last_capture)
        self.open_folder_button = QPushButton("Ouvrir le dossier")
        self.open_folder_button.setObjectName("secondaryButton")
        self.open_folder_button.clicked.connect(self._open_output_folder)
        preview_actions.addWidget(self.open_image_button)
        preview_actions.addWidget(self.open_folder_button)
        preview_actions.addStretch()
        preview_layout.addLayout(preview_actions)
        root.addWidget(preview_panel)

        footer = QLabel("JPEG qualité 95 • 4:4:4 • sans curseur • son de capture personnalisé • fonctionnement local")
        footer.setObjectName("footerText")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(footer)

    @staticmethod
    def _make_panel(title: str, description: str) -> tuple[QFrame, QVBoxLayout]:
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(9)
        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        description_label = QLabel(description)
        description_label.setObjectName("muted")
        description_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(description_label)
        return panel, layout

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.app_icon, self)
        menu = QMenu()
        self.tray_open_action = menu.addAction("Ouvrir DRT Screen Creator")
        self.tray_open_action.triggered.connect(self._show_window)
        self.tray_arm_action = menu.addAction("Armer la capture")
        self.tray_arm_action.triggered.connect(self._toggle_armed)
        menu.addSeparator()
        self.tray_last_action = menu.addAction("Ouvrir la dernière capture")
        self.tray_last_action.triggered.connect(self._open_last_capture)
        self.tray_folder_action = menu.addAction("Ouvrir le dossier")
        self.tray_folder_action.triggered.connect(self._open_output_folder)
        menu.addSeparator()
        quit_action = menu.addAction("Quitter")
        quit_action.triggered.connect(self.request_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()
        self._update_tray()

    def _load_settings_into_interface(self) -> None:
        self._loading_ui = True
        try:
            self.output_edit.setText(self.settings.output_dir)
            self.base_name_edit.setText(self.settings.base_name)
            self.hotkey_edit.setKeySequence(QKeySequence(self.settings.hotkey))
            self.free_hotkey_edit.setKeySequence(QKeySequence(self.settings.free_hotkey))
        finally:
            self._loading_ui = False
        self._update_region_label()
        self._load_last_preview()

    def _refresh_topology(self, initial: bool = False) -> bool:
        try:
            self._monitors = enumerate_monitors()
        except (OSError, RuntimeError) as error:
            LOGGER.exception("Échec de détection des écrans")
            self._set_status("Erreur", "error", str(error))
            return False
        if not initial:
            self._update_region_label()
        return True

    def _topology_matches(self) -> bool:
        return bool(
            self.settings.region
            and self._monitors
            and self.settings.topology_fingerprint == topology_fingerprint(self._monitors)
            and region_is_visible(self.settings.region, self._monitors)
        )

    def _choose_region(self) -> None:
        self._disarm(silent=True)
        if not self._refresh_topology():
            return
        current = self.settings.region if self.settings.region and region_is_visible(self.settings.region, self._monitors) else None
        self.hide()
        self._selector = RegionSelectionController(self._monitors, current, self)
        self._selector.selected.connect(self._region_selected)
        self._selector.cancelled.connect(self._region_cancelled)
        QTimer.singleShot(100, self._selector.begin)

    def _region_selected(self, region: CaptureRegion) -> None:
        self.settings.region = region
        self.settings.topology_fingerprint = topology_fingerprint(self._monitors)
        self._selector = None
        self._show_window()
        self._update_region_label()
        self._schedule_save()
        self._update_configuration_state()

    def _region_cancelled(self) -> None:
        self._selector = None
        self._show_window()
        self._update_configuration_state()

    def _update_region_label(self) -> None:
        region = self.settings.region
        self.region_warning.hide()
        if not region:
            self.region_value.setText("Aucune zone définie")
            return
        self.region_value.setText(
            f"X {region.left}  •  Y {region.top}  •  {region.width} × {region.height} px"
        )
        if self._monitors:
            coverage = region_coverage(region, self._monitors)
            if not self._topology_matches():
                self.region_warning.setText(
                    "La configuration des écrans a changé. Redéfinissez la zone avant d’armer la capture."
                )
                self.region_warning.show()
            elif coverage < 0.999:
                self.region_warning.setText(
                    "Une partie du rectangle se trouve entre les écrans et apparaîtra noire dans le JPEG."
                )
                self.region_warning.show()

    def _choose_folder(self) -> None:
        start = self.output_edit.text().strip()
        if not Path(start).is_dir():
            start = str(Path.home() / "Pictures")
        selected = QFileDialog.getExistingDirectory(self, "Choisir le dossier des captures", start)
        if selected:
            self.output_edit.setText(selected)

    def _configuration_changed(self) -> None:
        if self._armed or self._loading_ui:
            return
        self.settings.output_dir = self.output_edit.text().strip()
        self.settings.base_name = self.base_name_edit.text().strip()
        sequence = self.hotkey_edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        free_sequence = self.free_hotkey_edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        self.settings.hotkey = sequence
        self.settings.free_hotkey = free_sequence
        self._refresh_next_index()
        self._validate_hotkey_display()
        self._schedule_save()
        self._update_configuration_state()

    def _refresh_next_index(self) -> None:
        self.next_file_label.setText("—")
        output_dir = Path(self.settings.output_dir) if self.settings.output_dir else Path()
        try:
            base_name = validate_base_name(self.settings.base_name)
        except InvalidBaseName:
            return
        if not self.settings.output_dir or not output_dir.is_dir():
            return
        folder_key, base_key = sequence_key(output_dir, base_name)
        stored = self.settings.next_index
        if folder_key != self.settings.sequence_folder or base_key != self.settings.sequence_base:
            stored = 1
        self.settings.next_index = find_next_index(output_dir, base_name, stored)
        self.settings.sequence_folder = folder_key
        self.settings.sequence_base = base_key
        self.next_file_label.setText(capture_filename(base_name, self.settings.next_index))

    def _validate_hotkey_display(self) -> bool:
        try:
            fixed_spec = parse_hotkey(self.settings.hotkey)
            free_spec = parse_hotkey(self.settings.free_hotkey)
            if fixed_spec.canonical == free_spec.canonical:
                raise InvalidHotkey("Les deux raccourcis doivent être différents.")
        except InvalidHotkey as error:
            self.hotkey_error.setText(str(error))
            self.hotkey_error.show()
            return False
        self.settings.hotkey = fixed_spec.canonical
        self.settings.free_hotkey = free_spec.canonical
        self.hotkey_error.hide()
        return True

    def _validation_errors(self) -> list[str]:
        errors: list[str] = []
        if not self.settings.region:
            errors.append("Définissez la zone de capture.")
        elif not self._topology_matches():
            errors.append("Redéfinissez la zone pour la configuration actuelle des écrans.")
        output_dir = Path(self.settings.output_dir) if self.settings.output_dir else None
        if not output_dir or not output_dir.is_dir():
            errors.append("Choisissez un dossier de destination existant.")
        elif not os.access(output_dir, os.W_OK):
            errors.append("Le dossier de destination n’est pas accessible en écriture.")
        try:
            validate_base_name(self.settings.base_name)
        except InvalidBaseName as error:
            errors.append(str(error))
        try:
            fixed_spec = parse_hotkey(self.settings.hotkey)
            free_spec = parse_hotkey(self.settings.free_hotkey)
            if fixed_spec.canonical == free_spec.canonical:
                errors.append("Les deux raccourcis doivent être différents.")
        except InvalidHotkey as error:
            errors.append(str(error))
        return errors

    def _update_configuration_state(self) -> None:
        self._update_region_label()
        self._refresh_next_index()
        errors = self._validation_errors()
        if self._armed:
            return
        if errors:
            self._set_status("Non configuré", "neutral", errors[0])
        else:
            self._set_status("Prêt", "ready", "La configuration est valide. Vous pouvez armer la capture.")
        self.arm_button.setEnabled(not errors)
        self._update_tray()

    def _toggle_armed(self) -> None:
        if self._armed:
            self._disarm()
        else:
            self._arm()

    def _arm(self) -> None:
        self._configuration_changed()
        if not self._refresh_topology():
            return
        errors = self._validation_errors()
        if errors:
            self._set_status("Erreur", "error", errors[0])
            self.toast.show_message(errors[0], False)
            return
        success, error = self.hotkey_manager.register_pair(self.settings.hotkey, self.settings.free_hotkey)
        if not success:
            self._set_status("Erreur", "error", error)
            self.hotkey_error.setText(error)
            self.hotkey_error.show()
            self.toast.show_message(error, False)
            return
        self._armed = True
        self._set_controls_enabled(False)
        self.arm_button.setEnabled(True)
        self.arm_button.setText("Désarmer la capture")
        self.arm_button.setObjectName("dangerButton")
        self._refresh_widget_style(self.arm_button)
        armed_details = self._armed_details()
        self._set_status("Armé", "armed", armed_details)
        self._save_settings()
        self._update_tray()
        self.toast.show_message(
            f"Mode armé — {self.hotkey_manager.current_hotkey} : zone fixe • "
            f"{self.hotkey_manager.current_free_hotkey} : libre",
            True,
        )

    def _disarm(self, silent: bool = False) -> None:
        self.hotkey_manager.unregister()
        was_armed = self._armed
        self._armed = False
        self._set_controls_enabled(True)
        self.arm_button.setText("Armer la capture")
        self.arm_button.setObjectName("primaryButton")
        self._refresh_widget_style(self.arm_button)
        self._update_configuration_state()
        if was_armed and not silent:
            self.toast.show_message("Capture désarmée", True)

    def _set_controls_enabled(self, enabled: bool) -> None:
        for widget in (
            self.region_button,
            self.output_edit,
            self.folder_button,
            self.base_name_edit,
            self.hotkey_edit,
            self.free_hotkey_edit,
        ):
            widget.setEnabled(enabled)

    def _armed_details(self) -> str:
        fixed = self.hotkey_manager.current_hotkey or self.settings.hotkey
        free = self.hotkey_manager.current_free_hotkey or self.settings.free_hotkey
        return f"{fixed} : zone prédéfinie  •  {free} : capture libre"

    def _capture_requested(self) -> None:
        if not self._armed:
            return
        if self._selector is not None:
            self.toast.show_message("Terminez d’abord la sélection en cours.", False, 1300)
            return
        if self._capture_in_progress:
            self.toast.show_message("Une capture est déjà en cours.", False, 1300)
            return
        if not self._refresh_topology() or not self._topology_matches():
            self._disarm(silent=True)
            message = "Écrans modifiés : redéfinissez la zone avant de continuer."
            self._set_status("Erreur", "error", message)
            self.toast.show_message(message, False)
            return

        settings_snapshot = CaptureSettings.from_dict(self.settings.to_dict())
        self._start_capture(settings_snapshot)

    def _free_capture_requested(self) -> None:
        if not self._armed:
            return
        if self._selector is not None:
            self.toast.show_message("Terminez d’abord la sélection en cours.", False, 1300)
            return
        if self._capture_in_progress:
            self.toast.show_message("Une capture est déjà en cours.", False, 1300)
            return
        if not self._refresh_topology() or not self._topology_matches():
            self._disarm(silent=True)
            message = "Écrans modifiés : redéfinissez la zone avant de continuer."
            self._set_status("Erreur", "error", message)
            self.toast.show_message(message, False)
            return

        self._selector_restore_window = self.isVisible()
        self.hide()
        self._selector = RegionSelectionController(
            self._monitors,
            None,
            self,
            single_click_to_confirm=True,
        )
        self._selector.selected.connect(self._free_region_selected)
        self._selector.cancelled.connect(self._free_region_cancelled)
        QTimer.singleShot(100, self._selector.begin)

    def _free_region_selected(self, region: CaptureRegion) -> None:
        self._selector = None
        self._restore_window_after_capture = self._selector_restore_window
        self._selector_restore_window = False
        settings_snapshot = CaptureSettings.from_dict(self.settings.to_dict())
        settings_snapshot.region = region
        self._set_status("Armé", "armed", "Capture libre en cours…")
        # Le bref délai garantit que les voiles de sélection ont disparu du bureau.
        self._capture_in_progress = True
        QTimer.singleShot(150, lambda: self._run_capture_task(settings_snapshot))

    def _free_region_cancelled(self) -> None:
        self._selector = None
        restore_window = self._selector_restore_window
        self._selector_restore_window = False
        if restore_window:
            self._show_window()
        if self._armed:
            self._set_status("Armé", "armed", self._armed_details())
        self.toast.show_message("Capture libre annulée", True, 1300)

    def _start_capture(self, settings_snapshot: CaptureSettings) -> None:
        self._capture_in_progress = True
        self._run_capture_task(settings_snapshot)

    def _run_capture_task(self, settings_snapshot: CaptureSettings) -> None:
        task = CaptureTask(self.capture_service, settings_snapshot)
        self._capture_tasks.add(task)
        task.signals.finished.connect(lambda result, current=task: self._capture_finished(result, current))
        self.thread_pool.start(task)

    def _capture_finished(self, result: CaptureResult, task: CaptureTask) -> None:
        self._capture_tasks.discard(task)
        self._capture_in_progress = False
        restore_window = self._restore_window_after_capture
        self._restore_window_after_capture = False
        if not result.success or not result.path:
            message = result.error or "La capture a échoué."
            self._disarm(silent=True)
            self._set_status("Erreur", "error", message)
            self.toast.show_message(message, False)
            LOGGER.error("Capture échouée : %s", message)
            if restore_window:
                self._show_window()
            return

        self.settings.next_index = result.next_index or self.settings.next_index
        self.settings.last_capture_path = str(result.path)
        self._save_settings()
        self.next_file_label.setText(capture_filename(self.settings.base_name, self.settings.next_index))
        self._load_last_preview(result)
        self._set_status("Capture réussie", "success", f"{result.path.name} a été enregistré.")
        self.success_sound.play()
        self.toast.show_message(f"Capture enregistrée — {result.path.name}", True)
        self._update_tray()
        LOGGER.info("Capture enregistrée : %s", result.path)
        if restore_window:
            self._show_window()

    def _load_last_preview(self, result: CaptureResult | None = None) -> None:
        path = Path(self.settings.last_capture_path) if self.settings.last_capture_path else None
        exists = bool(path and path.is_file())
        self.open_image_button.setEnabled(exists)
        self.tray_last_action.setEnabled(exists) if hasattr(self, "tray_last_action") else None
        if not exists or path is None:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("Aucune capture enregistrée")
            self.last_capture_details.setText("—")
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("Aperçu indisponible")
            self.last_capture_details.setText(str(path))
            return
        self.preview_label.setText("")
        target = QSize(max(100, self.preview_label.width() - 20), max(100, self.preview_label.height() - 20))
        self.preview_label.setPixmap(
            pixmap.scaled(target, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        )
        if result:
            details = (
                f"{path.name}  •  {result.width} × {result.height} px  •  "
                f"{result.timestamp.strftime('%d/%m/%Y à %H:%M:%S')}\n{path}"
            )
        else:
            details = f"{path.name}\n{path}"
        self.last_capture_details.setText(details)

    def _open_last_capture(self) -> None:
        path = Path(self.settings.last_capture_path) if self.settings.last_capture_path else None
        if path and path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            self.toast.show_message("La dernière capture n’existe plus.", False)
            self._load_last_preview()

    def _open_output_folder(self) -> None:
        path = Path(self.settings.output_dir) if self.settings.output_dir else None
        if path and path.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            self.toast.show_message("Le dossier de destination n’existe plus.", False)

    def _set_status(self, label: str, state: str, details: str = "") -> None:
        self.status_label.setText(label)
        colors = {
            "neutral": ("#3a3027", "#c8b79a"),
            "ready": ("#38331f", "#f4c873"),
            "armed": ("#2c351c", "#a3d12d"),
            "success": ("#263017", "#a3d12d"),
            "error": ("#3a1f1b", "#ef6655"),
        }
        background, border = colors.get(state, colors["neutral"])
        self.status_label.setStyleSheet(
            f"background: {background}; color: #f6f0e4; border: 2px solid {border}; "
            "border-radius: 12px; padding: 7px 12px; font-weight: 800;"
        )
        self.status_label.setToolTip(details)
        self.status_details.setText(details)

    def _update_tray(self) -> None:
        if not hasattr(self, "tray"):
            return
        state = "Armé" if self._armed else "Désarmé"
        self.tray.setToolTip(f"DRT Screen Creator — {state}")
        self.tray_arm_action.setText("Désarmer la capture" if self._armed else "Armer la capture")
        output_exists = bool(self.settings.output_dir) and Path(self.settings.output_dir).is_dir()
        self.tray_folder_action.setEnabled(output_exists)
        last_exists = self.settings.capture_path_exists()
        self.tray_last_action.setEnabled(last_exists)

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self._show_window()

    def _show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _schedule_save(self) -> None:
        self._save_timer.start(250)

    def _save_settings(self) -> None:
        try:
            self.settings_repository.save(self.settings)
        except OSError as error:
            LOGGER.exception("Impossible d’enregistrer la configuration")
            self._set_status("Erreur", "error", f"Configuration non enregistrée : {error}")

    @staticmethod
    def _refresh_widget_style(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def request_quit(self) -> None:
        self._quitting = True
        self._disarm(silent=True)
        self._save_settings()
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - API Qt
        if self._quitting or not self.tray.isVisible():
            event.accept()
            return
        event.ignore()
        self.hide()
        self.toast.show_message("DRT Screen Creator reste actif près de l’horloge.", True)

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802 - API Qt
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized() and self.tray.isVisible():
            QTimer.singleShot(0, self.hide)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - API Qt
        super().resizeEvent(event)
        if self.settings.capture_path_exists():
            self._load_last_preview()
