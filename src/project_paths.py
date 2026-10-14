"""Portable paths; existing D-drive users can configure environment overrides."""
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
WORK_DIR = Path(os.environ.get("AGENT_WORK_DIR", PROJECT_DIR / "work"))
OUTPUT_DIR = Path(os.environ.get("AGENT_OUTPUT_DIR", PROJECT_DIR / "outputs"))
