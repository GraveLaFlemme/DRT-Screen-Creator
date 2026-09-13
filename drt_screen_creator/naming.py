from __future__ import annotations

import re
from pathlib import Path


INVALID_FILENAME_CHARS = set('<>:"/\\|?*')
RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}


class InvalidBaseName(ValueError):
    pass


def validate_base_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise InvalidBaseName("Saisissez un nom de fichier.")
    invalid = sorted({character for character in name if character in INVALID_FILENAME_CHARS or ord(character) < 32})
    if invalid:
        display = " ".join(repr(character) for character in invalid)
        raise InvalidBaseName(f"Caractères interdits dans le nom : {display}")
    if name.endswith((".", " ")):
        raise InvalidBaseName("Le nom ne peut pas finir par un point ou un espace.")
    if name.upper() in RESERVED_NAMES:
        raise InvalidBaseName("Ce nom est réservé par Windows.")
    if len(name) > 120:
        raise InvalidBaseName("Le nom est trop long (120 caractères maximum).")
    return name


def sequence_key(output_dir: Path, base_name: str) -> tuple[str, str]:
    try:
        folder = str(output_dir.resolve()).casefold()
    except OSError:
        folder = str(output_dir.absolute()).casefold()
    return folder, base_name.casefold()


def find_next_index(output_dir: Path, base_name: str, stored_next: int = 1) -> int:
    safe_name = validate_base_name(base_name)
    next_index = max(1, int(stored_next))
    if not output_dir.is_dir():
        return next_index
    pattern = re.compile(rf"^{re.escape(safe_name)}-(\d+)\.jpg$", re.IGNORECASE)
    highest = 0
    try:
        entries = output_dir.iterdir()
        for entry in entries:
            if not entry.is_file():
                continue
            match = pattern.match(entry.name)
            if match:
                highest = max(highest, int(match.group(1)))
    except OSError:
        return next_index
    return max(next_index, highest + 1)


def capture_filename(base_name: str, index: int) -> str:
    return f"{validate_base_name(base_name)}-{max(1, int(index))}.jpg"
