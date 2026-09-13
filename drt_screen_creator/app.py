from __future__ import annotations

import ctypes
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys

from PySide6.QtCore import QLockFile
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from .config import SettingsRepository, app_data_dir
from .hotkey import GlobalHotkeyManager
from .sound import SuccessSound
from .window import MainWindow


def resource_path(name: str) -> Path:
    package_path = Path(__file__).resolve().parent / "resources" / name
    if package_path.exists():
        return package_path
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return bundle_root / "drt_screen_creator" / "resources" / name


def configure_logging() -> None:
    log_dir = app_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def load_stylesheet() -> str:
    try:
        return resource_path("style.qss").read_text(encoding="utf-8")
    except OSError:
        return ""


def main() -> int:
    if sys.platform != "win32":
        print("DRT Screen Creator nécessite Windows.", file=sys.stderr)
        return 1

    configure_logging()
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DofusRetroTools.ScreenCreator.1")
    except (AttributeError, OSError):
        pass

    application = QApplication(sys.argv)
    application.setApplicationName("DRT Screen Creator")
    application.setApplicationVersion("1.2.1")
    application.setOrganizationName("Dofus Retro Tools")
    application.setQuitOnLastWindowClosed(False)
    application.setStyleSheet(load_stylesheet())

    icon = QIcon(str(resource_path("drt-screen-creator.ico")))
    if icon.isNull():
        icon = QIcon(str(resource_path("logo-drt.png")))
    application.setWindowIcon(icon)

    lock_path = app_data_dir() / "instance.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    instance_lock = QLockFile(str(lock_path))
    instance_lock.setStaleLockTime(30_000)
    if not instance_lock.tryLock(100):
        QMessageBox.information(None, "DRT Screen Creator", "L’application est déjà ouverte.")
        return 0

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(
            None,
            "DRT Screen Creator",
            "La zone de notification Windows est indisponible. L’application ne peut pas démarrer.",
        )
        instance_lock.unlock()
        return 1

    hotkey_manager = GlobalHotkeyManager(application)
    success_sound = SuccessSound(resource_path("steam-screenshot.mp3"))
    window = MainWindow(
        SettingsRepository(),
        hotkey_manager,
        icon,
        resource_path("logo-drt.png"),
        success_sound,
    )

    def handle_exception(exception_type, exception, traceback) -> None:
        logging.getLogger(__name__).critical(
            "Erreur non gérée",
            exc_info=(exception_type, exception, traceback),
        )
        QMessageBox.critical(
            window,
            "Erreur inattendue",
            "Une erreur inattendue est survenue. Consultez le journal dans LocalAppData.",
        )

    sys.excepthook = handle_exception
    application.aboutToQuit.connect(hotkey_manager.close)
    application.aboutToQuit.connect(success_sound.close)
    window.show()
    exit_code = application.exec()
    hotkey_manager.close()
    instance_lock.unlock()
    return exit_code
