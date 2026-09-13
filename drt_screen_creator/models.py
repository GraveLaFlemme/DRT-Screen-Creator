from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


SETTINGS_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class CaptureRegion:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def is_valid(self) -> bool:
        return self.width > 0 and self.height > 0

    def contains(self, x: int, y: int) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom

    def intersects(self, other: "CaptureRegion") -> bool:
        return not (
            self.right <= other.left
            or other.right <= self.left
            or self.bottom <= other.top
            or other.bottom <= self.top
        )

    def intersection(self, other: "CaptureRegion") -> "CaptureRegion | None":
        left = max(self.left, other.left)
        top = max(self.top, other.top)
        right = min(self.right, other.right)
        bottom = min(self.bottom, other.bottom)
        if right <= left or bottom <= top:
            return None
        return CaptureRegion(left, top, right - left, bottom - top)

    def to_dict(self) -> dict[str, int]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> "CaptureRegion | None":
        if not isinstance(data, dict):
            return None
        try:
            region = cls(
                left=int(data["left"]),
                top=int(data["top"]),
                width=int(data["width"]),
                height=int(data["height"]),
            )
        except (KeyError, TypeError, ValueError):
            return None
        return region if region.is_valid else None


@dataclass(frozen=True, slots=True)
class MonitorInfo:
    name: str
    left: int
    top: int
    width: int
    height: int
    dpi_x: int = 96
    dpi_y: int = 96
    primary: bool = False

    @property
    def region(self) -> CaptureRegion:
        return CaptureRegion(self.left, self.top, self.width, self.height)

    def fingerprint_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
            "dpi_x": self.dpi_x,
            "dpi_y": self.dpi_y,
            "primary": self.primary,
        }


@dataclass(slots=True)
class CaptureSettings:
    schema_version: int = SETTINGS_SCHEMA_VERSION
    region: CaptureRegion | None = None
    topology_fingerprint: str = ""
    output_dir: str = ""
    base_name: str = ""
    hotkey: str = "Ctrl+Shift+F10"
    free_hotkey: str = "F2"
    next_index: int = 1
    jpeg_quality: int = 95
    sequence_folder: str = ""
    sequence_base: str = ""
    last_capture_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SETTINGS_SCHEMA_VERSION,
            "region": self.region.to_dict() if self.region else None,
            "topology_fingerprint": self.topology_fingerprint,
            "output_dir": self.output_dir,
            "base_name": self.base_name,
            "hotkey": self.hotkey,
            "free_hotkey": self.free_hotkey,
            "next_index": max(1, int(self.next_index)),
            "jpeg_quality": 95,
            "sequence_folder": self.sequence_folder,
            "sequence_base": self.sequence_base,
            "last_capture_path": self.last_capture_path,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "CaptureSettings":
        if not isinstance(data, dict):
            return cls()
        try:
            next_index = max(1, int(data.get("next_index", 1)))
        except (TypeError, ValueError):
            next_index = 1
        hotkey = str(data.get("hotkey", "Ctrl+Shift+F10"))
        free_hotkey = str(data.get("free_hotkey", "")).strip()
        if not free_hotkey:
            free_hotkey = next(
                candidate
                for candidate in ("F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12", "F1")
                if candidate.casefold() != hotkey.replace(" ", "").casefold()
            )
        return cls(
            schema_version=SETTINGS_SCHEMA_VERSION,
            region=CaptureRegion.from_dict(data.get("region")),
            topology_fingerprint=str(data.get("topology_fingerprint", "")),
            output_dir=str(data.get("output_dir", "")),
            base_name=str(data.get("base_name", "")),
            hotkey=hotkey,
            free_hotkey=free_hotkey,
            next_index=next_index,
            jpeg_quality=95,
            sequence_folder=str(data.get("sequence_folder", "")),
            sequence_base=str(data.get("sequence_base", "")),
            last_capture_path=str(data.get("last_capture_path", "")),
        )

    def capture_path_exists(self) -> bool:
        return bool(self.last_capture_path) and Path(self.last_capture_path).is_file()


@dataclass(frozen=True, slots=True)
class CaptureResult:
    success: bool
    timestamp: datetime = field(default_factory=datetime.now)
    path: Path | None = None
    index: int | None = None
    next_index: int | None = None
    width: int = 0
    height: int = 0
    error: str = ""
