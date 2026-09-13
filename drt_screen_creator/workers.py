from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from .capture import CaptureService
from .models import CaptureResult, CaptureSettings


class CaptureTaskSignals(QObject):
    finished = Signal(object)


class CaptureTask(QRunnable):
    def __init__(self, service: CaptureService, settings: CaptureSettings) -> None:
        super().__init__()
        self.service = service
        self.settings = settings
        self.signals = CaptureTaskSignals()

    @Slot()
    def run(self) -> None:
        result: CaptureResult = self.service.capture(self.settings)
        self.signals.finished.emit(result)
