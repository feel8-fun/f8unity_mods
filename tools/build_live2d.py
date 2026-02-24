from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _has_exporter_flag(argv: list[str]) -> bool:
    return any(arg == "--exporter" or arg.startswith("--exporter=") for arg in argv)


def main() -> int:
    build_script = Path(__file__).resolve().with_name("build.py")
    forward = list(sys.argv[1:])
    if not _has_exporter_flag(forward):
        forward.extend(["--exporter", "live2d"])

    cmd = [sys.executable, str(build_script), *forward]
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
