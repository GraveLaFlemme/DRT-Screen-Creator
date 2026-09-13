from __future__ import annotations

import io
import os
import uuid
from pathlib import Path
from typing import Protocol

import mss
from PIL import Image

from .models import CaptureRegion, CaptureResult, CaptureSettings
from .naming import capture_filename, find_next_index, validate_base_name


class CaptureBackend(Protocol):
    def grab(self, region: CaptureRegion) -> Image.Image:
        ...


class MssCaptureBackend:
    def grab(self, region: CaptureRegion) -> Image.Image:
        monitor = {
            "left": region.left,
            "top": region.top,
            "width": region.width,
            "height": region.height,
        }
        with mss.mss() as screenshotter:
            screenshot = screenshotter.grab(monitor)
        return Image.frombytes("RGB", screenshot.size, screenshot.rgb)


class CaptureService:
    def __init__(self, backend: CaptureBackend | None = None) -> None:
        self.backend = backend or MssCaptureBackend()

    def capture(self, settings: CaptureSettings) -> CaptureResult:
        region = settings.region
        if region is None or not region.is_valid:
            return CaptureResult(False, error="La zone de capture n’est pas définie.")

        output_dir = Path(settings.output_dir)
        if not output_dir.is_dir():
            return CaptureResult(False, error="Le dossier de destination n’existe plus.")

        try:
            base_name = validate_base_name(settings.base_name)
            index = find_next_index(output_dir, base_name, settings.next_index)
            image = self.backend.grab(region)
            if image.size != (region.width, region.height):
                return CaptureResult(False, error="La capture reçue n’a pas les dimensions attendues.")
            if image.mode != "RGB":
                image = image.convert("RGB")

            encoded = io.BytesIO()
            image.save(
                encoded,
                format="JPEG",
                quality=95,
                subsampling=0,
                optimize=True,
            )
            payload = encoded.getvalue()
            temp_path = output_dir / f".drt-capture-{uuid.uuid4().hex}.tmp"
            try:
                with temp_path.open("xb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())

                while True:
                    final_path = output_dir / capture_filename(base_name, index)
                    try:
                        # Sous Windows, os.rename ne remplace pas une destination existante.
                        os.rename(temp_path, final_path)
                        break
                    except FileExistsError:
                        index += 1
            finally:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass

            return CaptureResult(
                True,
                path=final_path,
                index=index,
                next_index=index + 1,
                width=region.width,
                height=region.height,
            )
        except (OSError, ValueError, mss.exception.ScreenShotError) as error:
            return CaptureResult(False, error=f"Capture impossible : {error}")
