"""Unity exporter setup: commands responsibility."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .paths import (
    EXIT_INSTALL_FAILED,
)
from .models import (
    SetupError,
)


def print_json(payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))


def log(message: str) -> None:
    print(f"[helper] {message}")


def run_command(args: list[str], cwd: Path | None = None) -> None:
    log("running: " + " ".join(args))
    result = subprocess.run(args, cwd=str(cwd) if cwd else None)
    if result.returncode != 0:
        raise SetupError(EXIT_INSTALL_FAILED, f"command failed ({result.returncode}): {' '.join(args)}")
