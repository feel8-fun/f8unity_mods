from __future__ import annotations

from .models import (
    DetectionResult,
    SetupConfig,
    SetupError,
)
from .configuration import (
    load_setup_config,
)
from .game_setup import run_detect, run_diagnose, run_install

__version__ = "0.2.0"

__all__ = [
    "DetectionResult",
    "SetupConfig",
    "SetupError",
    "load_setup_config",
    "run_detect",
    "run_diagnose",
    "run_install",
    "__version__",
]
