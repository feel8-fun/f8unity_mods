"""Unity exporter setup: paths responsibility."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Protocol, cast



EXIT_OK = 0


EXIT_DETECT_FAILED = 2


EXIT_DOWNLOAD_FAILED = 3


EXIT_INSTALL_FAILED = 4


EXIT_BEPINEX_MISMATCH = 5


USER_AGENT = "f8-skeleton-streamer-helper"


class _PyInstallerSys(Protocol):
    frozen: bool
    _MEIPASS: str


_PACKAGED_SYS = cast(_PyInstallerSys, sys)


try:
    _IS_FROZEN = bool(_PACKAGED_SYS.frozen)
except AttributeError:
    _IS_FROZEN = False


_PACKAGE_ROOT = Path(__file__).resolve().parent


_SOURCE_ROOT = _PACKAGE_ROOT.parent


_PACKAGED_RESOURCE_ROOT = _PACKAGE_ROOT / "resources"


def _detect_resource_root() -> Path:
    if _IS_FROZEN:
        return Path(_PACKAGED_SYS._MEIPASS).resolve()
    if (_PACKAGED_RESOURCE_ROOT / "configs").is_dir():
        return _PACKAGED_RESOURCE_ROOT
    return _SOURCE_ROOT


def _detect_runtime_root() -> Path:
    if _IS_FROZEN:
        return Path(sys.executable).resolve().parent
    if (_SOURCE_ROOT / "configs").is_dir():
        return _SOURCE_ROOT
    return Path.cwd().resolve()


ROOT = _detect_resource_root()


RUNTIME_ROOT = _detect_runtime_root()
