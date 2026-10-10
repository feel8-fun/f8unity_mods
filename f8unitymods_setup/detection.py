"""Unity exporter setup: detection responsibility."""
from __future__ import annotations

import re
import struct
import subprocess
from pathlib import Path

from .paths import (
    EXIT_DETECT_FAILED,
)
from .models import (
    BepInExInstallState,
    DetectionResult,
    SetupError,
)
from .commands import (
    log,
)
from .profiles import (
    detect_game_profile,
)


def normalize_game_target(target: str) -> tuple[Path, Path, Path]:
    target_path = Path(target).expanduser().resolve()
    if not target_path.exists():
        raise SetupError(EXIT_DETECT_FAILED, f"target does not exist: {target_path}")

    if target_path.is_file():
        if target_path.suffix.lower() != ".exe":
            raise SetupError(EXIT_DETECT_FAILED, f"target file is not an exe: {target_path}")
        exe_path = target_path
        game_root = exe_path.parent
    else:
        game_root = target_path
        exe_path = _find_primary_exe(game_root)

    data_dir = _resolve_data_dir_for_exe(game_root, exe_path)
    return game_root, exe_path, data_dir


def _iter_candidate_exes(game_root: Path) -> list[Path]:
    exclusions = (
        "unitycrashhandler",
        "unitycrashhandler64",
        "doorstop",
        "bepinex.preloader",
    )
    candidates: list[Path] = []
    for exe in game_root.glob("*.exe"):
        lower = exe.name.lower()
        if any(lower.startswith(prefix) for prefix in exclusions):
            continue
        if lower == "winhttp.dll":
            continue
        candidates.append(exe)
    return sorted(candidates, key=lambda p: p.name.lower())


def _resolve_data_dir_for_exe(game_root: Path, exe_path: Path) -> Path:
    data_dir = game_root / f"{exe_path.stem}_Data"
    if data_dir.exists():
        return data_dir

    possible = sorted(p for p in game_root.glob("*_Data") if p.is_dir())
    if len(possible) == 1:
        return possible[0]

    raise SetupError(
        EXIT_DETECT_FAILED,
        f"cannot resolve Unity data directory for {exe_path.name}; expected {data_dir.name}",
    )


def _build_detection_result_for_exe(target_input: str, game_root: Path, exe_path: Path) -> DetectionResult:
    data_dir = _resolve_data_dir_for_exe(game_root, exe_path)
    process_name = exe_path.stem
    game_type, profile_id, exporter_key = detect_game_profile(process_name)
    backend = detect_backend(game_root, data_dir)
    arch = detect_arch(exe_path)
    unity_version = detect_unity_version(data_dir)
    bepinex = inspect_bepinex(game_root)
    return DetectionResult(
        target_input=target_input,
        game_root=game_root,
        exe_path=exe_path,
        data_dir=data_dir,
        process_name=process_name,
        game_type=game_type,
        profile_id=profile_id,
        exporter_key=exporter_key,
        unity_version=unity_version,
        backend=backend,
        arch=arch,
        has_bepinex=bepinex.installed,
        bepinex_variant=bepinex.variant,
        bepinex_version=bepinex.version,
        bepinex_major=bepinex.major,
        bepinex_partial=bepinex.partial,
        bepinex_core_present=bepinex.core_present,
        bepinex_bootstrap_present=bepinex.bootstrap_present,
        bepinex_core_files=bepinex.core_files,
        bepinex_bootstrap_files=bepinex.bootstrap_files,
        bepinex_missing_components=bepinex.missing_components,
    )


def _score_detection_result(result: DetectionResult) -> tuple[int, int, int, int, int, int, str]:
    profile_match = 1 if result.game_type != "unknown" and bool(result.profile_id) else 0
    exact_data_dir = 1 if result.data_dir.name.lower() == f"{result.exe_path.stem}_data".lower() else 0
    backend_known = 1 if result.backend != "unknown" else 0
    arch_known = 1 if result.arch != "unknown" else 0
    unity_known = 1 if result.unity_version != "unknown" else 0
    size_mb = int(result.exe_path.stat().st_size / (1024 * 1024))
    return (
        profile_match,
        exact_data_dir,
        backend_known,
        arch_known,
        unity_known,
        size_mb,
        result.exe_path.name.lower(),
    )


def _find_primary_exe(game_root: Path) -> Path:
    candidates = _iter_candidate_exes(game_root)
    if not candidates:
        raise SetupError(EXIT_DETECT_FAILED, f"no candidate game exe found in {game_root}")
    best: Path | None = None
    best_score: tuple[int, int, int, int, int, int, str] | None = None
    for exe in candidates:
        try:
            result = _build_detection_result_for_exe(str(game_root), game_root, exe)
        except SetupError:
            continue
        score = _score_detection_result(result)
        if best is None or best_score is None or score > best_score:
            best = exe
            best_score = score
    if best is not None:
        return best
    # Fallback to deterministic first candidate if every candidate failed deep detection.
    return candidates[0]


def detect_backend(game_root: Path, data_dir: Path) -> str:
    il2cpp = (game_root / "GameAssembly.dll").exists() and (data_dir / "il2cpp_data").exists()
    mono = (data_dir / "Managed").exists()
    if il2cpp and not mono:
        return "il2cpp"
    if mono and not il2cpp:
        return "mono"
    return "unknown"


def detect_unity_version(data_dir: Path) -> str:
    for name in ("globalgamemanagers", "data.unity3d"):
        path = data_dir / name
        if not path.exists():
            continue
        version = _extract_unity_version_from_binary(path)
        if version:
            return version
    return "unknown"


def _extract_unity_version_from_binary(path: Path) -> str | None:
    max_bytes = 8 * 1024 * 1024
    with path.open("rb") as f:
        blob = f.read(max_bytes)
    text = blob.decode("latin1", errors="ignore")

    patterns = [
        r"m_EditorVersion(?:WithRevision)?[^0-9]{0,32}([0-9]+\.[0-9]+\.[0-9]+[a-z][0-9]+)",
        r"([0-9]+\.[0-9]+\.[0-9]+[a-z][0-9]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(1)
    return None


def detect_arch(exe_path: Path) -> str:
    with exe_path.open("rb") as f:
        f.seek(0x3C)
        pe_offset = struct.unpack("<I", f.read(4))[0]
        f.seek(pe_offset + 4)
        machine = struct.unpack("<H", f.read(2))[0]
    if machine == 0x014C:
        return "x86"
    if machine == 0x8664:
        return "x64"
    return "unknown"


def inspect_bepinex(game_root: Path) -> BepInExInstallState:
    core_dir = game_root / "BepInEx" / "core"
    core_paths = tuple(sorted(path for path in core_dir.glob("BepInEx*.dll") if path.is_file()))
    mono_v5_core = core_dir / "BepInEx.dll"
    mono_v6_core = core_dir / "BepInEx.Unity.Mono.dll"
    il2cpp_core = core_dir / "BepInEx.Unity.IL2CPP.dll"
    doorstop_config = game_root / "doorstop_config.ini"
    winhttp_proxy = game_root / "winhttp.dll"
    bootstrap_paths = tuple(path for path in (doorstop_config, winhttp_proxy) if path.is_file())
    core_present = mono_v5_core.is_file() or mono_v6_core.is_file() or il2cpp_core.is_file()
    bootstrap_present = doorstop_config.is_file() and winhttp_proxy.is_file()
    has_evidence = (game_root / "BepInEx").exists() or bool(bootstrap_paths)
    installed = core_present and bootstrap_present
    partial = has_evidence and not installed

    variant = "unknown"
    if il2cpp_core.is_file():
        variant = "il2cpp"
    elif mono_v6_core.is_file() or mono_v5_core.is_file():
        variant = "mono"

    version = "unknown"
    if il2cpp_core.is_file():
        version_source = il2cpp_core
    elif mono_v6_core.is_file():
        version_source = mono_v6_core
    else:
        version_source = mono_v5_core
    if version_source.is_file():
        version = _read_windows_file_version(version_source)

    major = None
    if version and version != "unknown":
        try:
            major = int(version.split(".", 1)[0])
        except ValueError:
            major = None
    if major is None:
        if variant == "il2cpp":
            major = 6
        elif variant == "mono":
            major = 5

    missing_components: list[str] = []
    if not core_present:
        missing_components.append("BepInEx/core/BepInEx*.dll")
    if not doorstop_config.is_file():
        missing_components.append("doorstop_config.ini")
    if not winhttp_proxy.is_file():
        missing_components.append("winhttp.dll")

    if not has_evidence:
        variant = "none"
        version = "none"
        major = None

    return BepInExInstallState(
        installed=installed,
        partial=partial,
        variant=variant,
        version=version,
        major=major,
        core_present=core_present,
        bootstrap_present=bootstrap_present,
        core_files=tuple(str(path) for path in core_paths),
        bootstrap_files=tuple(str(path) for path in bootstrap_paths),
        missing_components=tuple(missing_components),
    )


def detect_bepinex(game_root: Path) -> tuple[bool, str, str, int | None]:
    state = inspect_bepinex(game_root)
    return state.installed, state.variant, state.version, state.major


def _read_windows_file_version(path: Path) -> str:
    escaped = str(path).replace("'", "''")
    cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        f"(Get-Item '{escaped}').VersionInfo.FileVersion",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        out = (result.stdout or "").strip()
        return out if out else "unknown"
    except OSError as exc:
        log(f"warning: failed to read Windows file version for {path}: {exc}")
        return "unknown"


def detect_game(target: str) -> DetectionResult:
    target_path = Path(target).expanduser().resolve()
    if not target_path.exists():
        raise SetupError(EXIT_DETECT_FAILED, f"target does not exist: {target_path}")

    if target_path.is_file():
        if target_path.suffix.lower() != ".exe":
            raise SetupError(EXIT_DETECT_FAILED, f"target file is not an exe: {target_path}")
        return _build_detection_result_for_exe(target, target_path.parent, target_path)

    game_root = target_path
    exes = _iter_candidate_exes(game_root)
    if not exes:
        raise SetupError(EXIT_DETECT_FAILED, f"no candidate game exe found in {game_root}")

    best_result: DetectionResult | None = None
    best_score: tuple[int, int, int, int, int, int, str] | None = None
    first_error: SetupError | None = None
    for exe in exes:
        try:
            result = _build_detection_result_for_exe(target, game_root, exe)
        except SetupError as e:
            if first_error is None:
                first_error = e
            continue
        score = _score_detection_result(result)
        if best_result is None or best_score is None or score > best_score:
            best_result = result
            best_score = score

    if best_result is not None:
        return best_result
    if first_error is not None:
        raise first_error
    raise SetupError(EXIT_DETECT_FAILED, f"cannot detect Unity game from {game_root}")
