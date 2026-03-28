# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path


spec_dir = Path(SPECPATH).resolve()
project_root = spec_dir.parents[1]
tools_dir = project_root / "tools"
entry_script = tools_dir / "game_setup_ui.py"


def _require_path(path: Path) -> Path:
    if not path.exists():
        raise SystemExit(f"missing required path for packaging: {path}")
    return path


datas = [
    (str(_require_path(project_root / "configs")), "configs"),
    (str(_require_path(project_root / "tools" / "game_setup_config.json")), "tools"),
    (str(_require_path(project_root / "tools" / "ui" / "i18n")), "tools/ui/i18n"),
]

a = Analysis(
    [str(entry_script)],
    pathex=[str(project_root), str(tools_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="GameSetupUI",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
