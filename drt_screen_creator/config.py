from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from .models import CaptureSettings


APP_DATA_PARTS = ("DofusRetroTools", "ScreenCreator")


def app_data_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    root = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return root.joinpath(*APP_DATA_PARTS)


class SettingsRepository:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_data_dir() / "settings.json"

    def load(self) -> CaptureSettings:
        if not self.path.exists():
            return CaptureSettings()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return CaptureSettings.from_dict(data)
        except (OSError, UnicodeError, json.JSONDecodeError):
            self._preserve_corrupt_file()
            return CaptureSettings()

    def save(self, settings: CaptureSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(".json.tmp")
        payload = json.dumps(settings.to_dict(), ensure_ascii=False, indent=2)
        temp_path.write_text(payload + "\n", encoding="utf-8")
        os.replace(temp_path, self.path)

    def _preserve_corrupt_file(self) -> None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        preserved = self.path.with_name(f"settings.corrupt-{stamp}.json")
        try:
            os.replace(self.path, preserved)
        except OSError:
            pass
