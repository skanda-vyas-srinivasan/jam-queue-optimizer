from __future__ import annotations

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent
ARTIFACT_DIR = REPO_ROOT / "artifacts"
SONGS_DIR = REPO_ROOT / "songs"
NOTEBOOKS_DIR = REPO_ROOT / "notebooks"
SCRIPTS_DIR = REPO_ROOT / "scripts"

