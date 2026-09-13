from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


def clean_build_path() -> None:
    """Évite d’embarquer les DLL privées d’un environnement hôte dans l’EXE."""
    python_root = Path(sys.base_prefix)
    virtual_environment = Path(sys.executable).parent
    windows_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    safe_entries = [
        virtual_environment,
        python_root,
        python_root / "DLLs",
        python_root / "Scripts",
        windows_root / "System32",
        windows_root,
        windows_root / "System32" / "Wbem",
    ]
    os.environ["PATH"] = os.pathsep.join(str(entry) for entry in safe_entries if entry.exists())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("onedir", "onefile"), default="onedir")
    arguments = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    resources = project_root / "drt_screen_creator" / "resources"
    output_dir = project_root / "dist"
    work_dir = project_root / "build"
    for resolved in (resources, output_dir, work_dir):
        resolved.resolve().relative_to(project_root.resolve())

    clean_build_path()
    import PyInstaller.__main__

    bundle_mode = "--onefile" if arguments.mode == "onefile" else "--onedir"
    PyInstaller.__main__.run(
        [
            "--noconfirm",
            "--clean",
            "--windowed",
            bundle_mode,
            "--name",
            "DRT-Screen-Creator",
            "--icon",
            str(resources / "drt-screen-creator.ico"),
            "--manifest",
            str(project_root / "packaging" / "app.manifest"),
            "--version-file",
            str(project_root / "packaging" / "version_info.txt"),
            "--add-data",
            f"{resources};drt_screen_creator\\resources",
            "--distpath",
            str(output_dir),
            "--workpath",
            str(work_dir),
            "--specpath",
            str(work_dir),
            str(project_root / "main.py"),
        ]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
