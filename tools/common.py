from __future__ import annotations

import dataclasses
import datetime as _dt
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


EXIT_OK = 0
EXIT_DETECT_FAILED = 2
EXIT_DOWNLOAD_FAILED = 3
EXIT_INSTALL_FAILED = 4
EXIT_BEPINEX_MISMATCH = 5

USER_AGENT = "f8-skeleton-streamer-helper"

_IS_FROZEN = bool(getattr(sys, "frozen", False))


def _detect_resource_root() -> Path:
    if _IS_FROZEN:
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            return Path(meipass).resolve()
    return Path(__file__).resolve().parents[1]


def _detect_runtime_root() -> Path:
    if _IS_FROZEN:
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


ROOT = _detect_resource_root()
RUNTIME_ROOT = _detect_runtime_root()
@dataclasses.dataclass(frozen=True)
class ExporterSpec:
    key: str
    project_name: str
    plugin_dir_name: str
    managed_by_value: str
    config_filename: str
    mono_dll_name: str
    il2cpp_dll_name: str

    @property
    def project_csproj(self) -> Path:
        return ROOT / "src" / self.project_name / f"{self.project_name}.csproj"

    @property
    def project_il2cpp_csproj(self) -> Path:
        return ROOT / "src" / f"{self.project_name}.IL2CPP" / f"{self.project_name}.IL2CPP.csproj"

    @property
    def artifact_mono_dir(self) -> Path:
        return ROOT / "src" / "bin" / self.project_name / "BepInEx" / "plugins" / self.plugin_dir_name

    @property
    def artifact_il2cpp_dir(self) -> Path:
        return ROOT / "src" / "bin" / f"{self.project_name}.IL2CPP" / "BepInEx" / "plugins" / self.plugin_dir_name

    @property
    def readme_path(self) -> Path:
        return ROOT / "src" / self.project_name / "README.md"


DEFAULT_EXPORTER_SPEC = ExporterSpec(
    key="default",
    project_name="F8SkeletonStreamer",
    plugin_dir_name="F8SkeletonStreamer",
    managed_by_value="tools/game_setup.py",
    config_filename="com.feel8.f8-skeleton-streamer.cfg",
    mono_dll_name="F8SkeletonStreamer.dll",
    il2cpp_dll_name="F8SkeletonStreamer.IL2CPP.dll",
)

LIVE2D_EXPORTER_SPEC = ExporterSpec(
    key="live2d",
    project_name="F8Live2DStreamer",
    plugin_dir_name="F8Live2DStreamer",
    managed_by_value="tools/game_setup.py",
    config_filename="com.feel8.f8-live2d-streamer.cfg",
    mono_dll_name="F8Live2DStreamer.dll",
    il2cpp_dll_name="F8Live2DStreamer.IL2CPP.dll",
)


def resolve_exporter_spec(spec: ExporterSpec | None = None) -> ExporterSpec:
    return spec if spec is not None else DEFAULT_EXPORTER_SPEC


def resolve_exporter_spec_by_key(exporter_key: str | None) -> ExporterSpec:
    return LIVE2D_EXPORTER_SPEC if str(exporter_key or "").lower() == "live2d" else DEFAULT_EXPORTER_SPEC


def infer_exporter_key_from_profile_payload(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return "default"

    raw = str(payload.get("streamerType", "") or payload.get("exporterType", "")).strip().lower()
    if raw in ("live2d", "f8live2dstreamer", "live2dstreamer"):
        return "live2d"
    if raw in ("default", "skeleton", "f8skeletonstreamer", "skeletonstreamer"):
        return "default"

    live2d_markers = (
        "live2dRootsExpr",
        "autoDiscoverCubism",
        "drawableNameIncludeRegex",
        "drawableNameExcludeRegex",
        "minBoundsExtent",
    )
    for key in live2d_markers:
        if key in payload:
            return "live2d"

    return "default"


# Backward-compatible constants for existing scripts.
PROJECT_CSPROJ = DEFAULT_EXPORTER_SPEC.project_csproj
PROJECT_IL2CPP_CSPROJ = DEFAULT_EXPORTER_SPEC.project_il2cpp_csproj
EXPORTER_DLL_DIR = DEFAULT_EXPORTER_SPEC.artifact_mono_dir
EXPORTER_DLL = EXPORTER_DLL_DIR / DEFAULT_EXPORTER_SPEC.mono_dll_name
EXPORTER_IL2CPP_DIR = DEFAULT_EXPORTER_SPEC.artifact_il2cpp_dir
EXPORTER_README = DEFAULT_EXPORTER_SPEC.readme_path


def _normalize_process_name(value: str) -> str:
    return re.sub(r"[\s_-]+", "", value or "").lower()


def _load_game_profile_catalog() -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    configs_dir = ROOT / "configs"
    if not configs_dir.is_dir():
        return catalog

    for path in sorted(configs_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue

        profile_id = str(payload.get("id", "") or "").strip()
        if not profile_id:
            continue

        raw_names = payload.get("processNames", [])
        aliases: list[str] = []
        if isinstance(raw_names, list):
            aliases = [str(item).strip() for item in raw_names if str(item).strip()]

        # Keep detection robust even when processNames is empty/incomplete.
        aliases.append(path.stem)
        aliases.append(profile_id)
        dedup_aliases = sorted({_normalize_process_name(name) for name in aliases if _normalize_process_name(name)})
        if not dedup_aliases:
            continue

        game_type = _normalize_process_name(path.stem)
        exporter_key = infer_exporter_key_from_profile_payload(payload)
        catalog[game_type] = {
            "profile_id": profile_id,
            "profile_template": path.name,
            "aliases": dedup_aliases,
            "exporter_key": exporter_key,
        }

    return catalog


GAME_PROFILE_CATALOG: dict[str, dict[str, Any]] = _load_game_profile_catalog()

PROFILE_MANAGED_BY_KEY = "_managed_by"
PROFILE_MANAGED_BY_VALUE = DEFAULT_EXPORTER_SPEC.managed_by_value
PROFILE_FILENAME = "profile.json"


@dataclasses.dataclass
class SetupConfig:
    self_release_repo: str
    self_release_tag: str
    self_release_channel: str
    config_manifest_url: str
    config_base_url: str
    prefer_local_configs: bool
    allow_remote_configs: bool
    bepinex_release_repo: str
    bepinex_be_index_url: str
    rue_release_repo: str
    cue_release_repo: str
    config_manager_release_repo: str
    universal_unity_demosaics_release_repo: str
    cache_dir: Path
    remote_cache_dir: Path
    timeout_sec: int
    remote_timeout_sec: int
    asset_regex_overrides: dict[str, str]


@dataclasses.dataclass
class DetectionResult:
    target_input: str
    game_root: Path
    exe_path: Path
    data_dir: Path
    process_name: str
    game_type: str
    profile_id: str
    exporter_key: str
    unity_version: str
    backend: str
    arch: str
    has_bepinex: bool
    bepinex_variant: str
    bepinex_version: str
    bepinex_major: int | None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "target_input": self.target_input,
            "game_root": str(self.game_root),
            "exe_path": str(self.exe_path),
            "process_name": self.process_name,
            "game_type": self.game_type,
            "profile_id": self.profile_id,
            "exporter_key": self.exporter_key,
            "unity_version": self.unity_version,
            "backend": self.backend,
            "arch": self.arch,
            "has_bepinex": self.has_bepinex,
            "bepinex_variant": self.bepinex_variant,
            "bepinex_version": self.bepinex_version,
            "bepinex_major": self.bepinex_major,
        }


class SetupError(RuntimeError):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def print_json(payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))


def log(message: str) -> None:
    print(f"[helper] {message}")


def load_setup_config(path: Path | None = None) -> SetupConfig:
    defaults = {
        "self_release_repo": "feel8-fun/f8unity_mods",
        "self_release_tag": "",
        "self_release_channel": "latest",
        "config_manifest_url": "https://github.com/feel8-fun/f8unity_mods/releases/latest/download/configs-manifest.json",
        "config_base_url": "https://raw.githubusercontent.com/feel8-fun/f8unity_mods/main/configs",
        "prefer_local_configs": True,
        "allow_remote_configs": True,
        "bepinex_release_repo": "BepInEx/BepInEx",
        "bepinex_be_index_url": "https://builds.bepinex.dev/projects/bepinex_be",
        "rue_release_repo": "ManlyMarco/RuntimeUnityEditor",
        "cue_release_repo": "originalnicodr/CinematicUnityExplorer",
        "config_manager_release_repo": "BepInEx/BepInEx.ConfigurationManager",
        "universal_unity_demosaics_release_repo": "ManlyMarco/UniversalUnityDemosaics",
        "cache_dir": ".cache/unity_exporter_helper",
        "remote_cache_dir": ".cache/f8unitymods_remote",
        "timeout_sec": 30,
        "remote_timeout_sec": 30,
        "asset_regex_overrides": {},
    }

    config_candidates: list[Path] = []
    if path is not None:
        config_candidates = [path]
    else:
        config_candidates = [
            RUNTIME_ROOT / "game_setup_config.json",
            ROOT / "tools" / "game_setup_config.json",
            RUNTIME_ROOT / "tools" / "game_setup_config.json",
        ]

    seen_candidates: set[Path] = set()
    for candidate in config_candidates:
        resolved = candidate.expanduser().resolve()
        if resolved in seen_candidates:
            continue
        seen_candidates.add(resolved)
        if not resolved.exists():
            continue
        with resolved.open("r", encoding="utf-8") as f:
            custom = json.load(f)
        defaults.update(custom or {})
        break

    cache_dir = Path(defaults["cache_dir"])
    if not cache_dir.is_absolute():
        cache_base = RUNTIME_ROOT if _IS_FROZEN else ROOT
        cache_dir = cache_base / cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)

    remote_cache_dir = Path(defaults["remote_cache_dir"])
    if not remote_cache_dir.is_absolute():
        cache_base = RUNTIME_ROOT if _IS_FROZEN else ROOT
        remote_cache_dir = cache_base / remote_cache_dir
    remote_cache_dir.mkdir(parents=True, exist_ok=True)

    return SetupConfig(
        self_release_repo=str(defaults["self_release_repo"]),
        self_release_tag=str(defaults.get("self_release_tag", "") or ""),
        self_release_channel=str(defaults.get("self_release_channel", "latest") or "latest"),
        config_manifest_url=str(defaults.get("config_manifest_url", "") or ""),
        config_base_url=str(defaults.get("config_base_url", "") or ""),
        prefer_local_configs=bool(defaults.get("prefer_local_configs", True)),
        allow_remote_configs=bool(defaults.get("allow_remote_configs", True)),
        bepinex_release_repo=str(defaults["bepinex_release_repo"]),
        bepinex_be_index_url=str(defaults["bepinex_be_index_url"]),
        rue_release_repo=str(defaults["rue_release_repo"]),
        cue_release_repo=str(defaults["cue_release_repo"]),
        config_manager_release_repo=str(defaults["config_manager_release_repo"]),
        universal_unity_demosaics_release_repo=str(defaults["universal_unity_demosaics_release_repo"]),
        cache_dir=cache_dir,
        remote_cache_dir=remote_cache_dir,
        timeout_sec=int(defaults["timeout_sec"]),
        remote_timeout_sec=int(defaults.get("remote_timeout_sec", defaults["timeout_sec"])),
        asset_regex_overrides=dict(defaults.get("asset_regex_overrides", {})),
    )


def run_command(args: list[str], cwd: Path | None = None) -> None:
    log("running: " + " ".join(args))
    result = subprocess.run(args, cwd=str(cwd) if cwd else None)
    if result.returncode != 0:
        raise SetupError(EXIT_INSTALL_FAILED, f"command failed ({result.returncode}): {' '.join(args)}")


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
    has_bep, bep_variant, bep_ver, bep_major = detect_bepinex(game_root)
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
        has_bepinex=has_bep,
        bepinex_variant=bep_variant,
        bepinex_version=bep_ver,
        bepinex_major=bep_major,
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


def detect_bepinex(game_root: Path) -> tuple[bool, str, str, int | None]:
    core_dir = game_root / "BepInEx" / "core"
    has_core = core_dir.is_dir() and any(core_dir.glob("BepInEx*.dll"))
    has_doorstop = (game_root / "doorstop_config.ini").exists() or (game_root / "winhttp.dll").exists()
    has_bepinex = has_core or has_doorstop
    if not has_bepinex:
        return False, "none", "none", None

    variant = "unknown"
    if (core_dir / "BepInEx.Unity.IL2CPP.dll").exists():
        variant = "il2cpp"
    elif (core_dir / "BepInEx.Unity.Mono.dll").exists() or (core_dir / "BepInEx.dll").exists():
        variant = "mono"

    version = "unknown"
    version_source = (
        core_dir / "BepInEx.Unity.IL2CPP.dll"
        if (core_dir / "BepInEx.Unity.IL2CPP.dll").exists()
        else core_dir / "BepInEx.dll"
    )
    if version_source.exists():
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

    return True, variant, version, major


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
    except Exception:
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


def detect_game_profile(process_name: str) -> tuple[str, str, str]:
    normalized = _normalize_process_name(process_name)
    for game_type, spec in GAME_PROFILE_CATALOG.items():
        aliases = [_normalize_process_name(alias) for alias in spec.get("aliases", [])]
        if normalized in aliases:
            return (
                game_type,
                str(spec.get("profile_id", "") or ""),
                str(spec.get("exporter_key", "default") or "default"),
            )
    return "unknown", "", "auto"


def github_latest_release(repo: str, timeout_sec: int) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        return json.loads(resp.read().decode("utf-8"))


def github_release(repo: str, timeout_sec: int, *, tag: str = "", channel: str = "latest") -> dict[str, Any]:
    selected_tag = str(tag or "").strip()
    if selected_tag:
        url = f"https://api.github.com/repos/{repo}/releases/tags/{urllib.parse.quote(selected_tag)}"
    elif str(channel or "").strip().lower() == "latest":
        url = f"https://api.github.com/repos/{repo}/releases/latest"
    else:
        url = f"https://api.github.com/repos/{repo}/releases/{urllib.parse.quote(str(channel).strip())}"

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        return json.loads(resp.read().decode("utf-8"))


def github_asset_by_name(release: dict[str, Any], asset_name: str) -> dict[str, Any]:
    expected = str(asset_name or "").strip()
    for asset in release.get("assets", []):
        if str(asset.get("name", "")).strip() == expected:
            return asset
    raise SetupError(EXIT_DOWNLOAD_FAILED, f"release asset not found: {expected}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    raw = str(value).strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


def _read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _local_config_dirs() -> list[Path]:
    candidates = [
        RUNTIME_ROOT / "configs",
        ROOT / "configs",
    ]
    result: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        if resolved in seen or not candidate.is_dir():
            continue
        seen.add(resolved)
        result.append(candidate)
    return result


def _iter_local_profile_candidates(template_name: str) -> list[Path]:
    clean_name = str(template_name or "").strip()
    if not clean_name:
        return []
    return [config_dir / clean_name for config_dir in _local_config_dirs()]


def load_local_profile_template(template_name: str) -> tuple[dict[str, Any], str] | None:
    for candidate in _iter_local_profile_candidates(template_name):
        payload = _read_json_file(candidate)
        if payload is not None:
            return payload, str(candidate)
    return None


def resolve_local_profile_for_detection(detection: DetectionResult) -> tuple[dict[str, Any], str] | None:
    normalized = _normalize_process_name(detection.process_name)
    fallback_match: tuple[dict[str, Any], str] | None = None
    for config_dir in _local_config_dirs():
        for candidate in sorted(config_dir.glob("*.json")):
            payload = _read_json_file(candidate)
            if payload is None:
                continue
            aliases = _profile_aliases_from_payload(candidate, payload)
            if normalized in aliases:
                return payload, str(candidate)
            detection_game_type = _normalize_process_name(detection.game_type)
            if detection_game_type and detection_game_type in aliases and fallback_match is None:
                fallback_match = (payload, str(candidate))
    return fallback_match


def _profile_aliases_from_payload(path: Path, payload: dict[str, Any]) -> set[str]:
    raw_names = payload.get("processNames", [])
    aliases: list[str] = []
    if isinstance(raw_names, list):
        aliases.extend(str(item).strip() for item in raw_names if str(item).strip())
    aliases.append(path.stem)
    aliases.append(str(payload.get("id", "")).strip())
    return {_normalize_process_name(item) for item in aliases if _normalize_process_name(item)}


def resolve_profile_template_path(profile_template_name: str) -> Path:
    name = profile_template_name.strip()
    if not name:
        raise SetupError(EXIT_INSTALL_FAILED, "profile template name is empty")
    candidates = _iter_local_profile_candidates(name)
    for path in candidates:
        if path.exists():
            return path
    fallback = (ROOT / "configs" / name) if not candidates else candidates[0]
    raise SetupError(EXIT_INSTALL_FAILED, f"profile template not found: {fallback}")


def load_remote_config_manifest(
    config: SetupConfig,
    *,
    offline: bool = False,
    refresh: bool = False,
) -> dict[str, Any] | None:
    manifest_url = str(config.config_manifest_url or "").strip()
    if not manifest_url:
        return None

    cache_path = config.remote_cache_dir / "manifests" / "configs-manifest.json"
    try:
        manifest_path = download_with_retries(
            manifest_url,
            cache_path,
            timeout_sec=config.remote_timeout_sec,
            offline=offline,
            refresh=refresh,
        )
    except SetupError:
        if cache_path.exists():
            payload = _read_json_file(cache_path)
            return payload if isinstance(payload, dict) else None
        return None

    payload = _read_json_file(manifest_path)
    return payload if isinstance(payload, dict) else None


def _remote_profile_matches_entry(entry: dict[str, Any], detection: DetectionResult) -> bool:
    process_normalized = _normalize_process_name(detection.process_name)
    candidates = [str(entry.get("id", "")), str(entry.get("gameType", "")), Path(str(entry.get("file", ""))).stem]
    raw_names = entry.get("processNames", [])
    if isinstance(raw_names, list):
        candidates.extend(str(item) for item in raw_names)
    aliases = entry.get("aliases", [])
    if isinstance(aliases, list):
        candidates.extend(str(item) for item in aliases)
    normalized = {_normalize_process_name(item) for item in candidates if _normalize_process_name(item)}
    if process_normalized in normalized:
        return True
    detection_game_type = _normalize_process_name(detection.game_type)
    return bool(detection_game_type and detection_game_type in normalized)


def resolve_remote_profile_entry(manifest: dict[str, Any] | None, detection: DetectionResult) -> dict[str, Any] | None:
    if not isinstance(manifest, dict):
        return None
    profiles = manifest.get("profiles", [])
    if not isinstance(profiles, list):
        return None
    for entry in profiles:
        if isinstance(entry, dict) and _remote_profile_matches_entry(entry, detection):
            return entry
    return None


def _remote_profile_url(entry: dict[str, Any], config: SetupConfig, manifest: dict[str, Any] | None) -> str:
    explicit = str(entry.get("downloadUrl", "") or entry.get("url", "")).strip()
    if explicit:
        return explicit
    base_url = ""
    if isinstance(manifest, dict):
        base_url = str(manifest.get("baseUrl", "") or "").strip()
    if not base_url:
        base_url = str(config.config_base_url or "").strip()
    rel = str(entry.get("file", "")).strip()
    if not rel or not base_url:
        return ""
    return urllib.parse.urljoin(base_url.rstrip("/") + "/", rel)


def download_remote_profile_payload(
    entry: dict[str, Any],
    manifest: dict[str, Any] | None,
    config: SetupConfig,
    *,
    offline: bool = False,
    refresh: bool = False,
) -> tuple[dict[str, Any], str]:
    rel_name = str(entry.get("file", "") or "").strip()
    expected_sha = str(entry.get("sha256", "") or "").strip().lower()
    if not rel_name:
        raise SetupError(EXIT_INSTALL_FAILED, "remote config manifest entry is missing file")

    url = _remote_profile_url(entry, config, manifest)
    if not url:
        raise SetupError(EXIT_INSTALL_FAILED, f"remote config manifest entry has no download url: {rel_name}")

    cache_name = f"{expected_sha}_{safe_filename(Path(rel_name).name)}" if expected_sha else safe_filename(Path(rel_name).name)
    cache_path = config.remote_cache_dir / "configs" / cache_name
    path = download_with_retries(
        url,
        cache_path,
        timeout_sec=config.remote_timeout_sec,
        offline=offline,
        refresh=refresh,
    )

    if expected_sha:
        actual_sha = sha256_file(path)
        if actual_sha.lower() != expected_sha:
            raise SetupError(
                EXIT_DOWNLOAD_FAILED,
                f"remote config checksum mismatch for {rel_name}: expected {expected_sha}, got {actual_sha}",
            )

    payload = _read_json_file(path)
    if payload is None:
        raise SetupError(EXIT_INSTALL_FAILED, f"remote config is not a valid object: {path}")
    return payload, str(path)


def select_self_release_asset(spec: ExporterSpec, backend: str) -> str:
    normalized_backend = "il2cpp" if str(backend or "").strip().lower() == "il2cpp" else "mono"
    return f"{spec.project_name}-{normalized_backend}.zip"


def download_self_release_asset(
    spec: ExporterSpec,
    backend: str,
    config: SetupConfig,
    *,
    release_tag: str = "",
    offline: bool = False,
    refresh: bool = False,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    if not str(config.self_release_repo or "").strip():
        raise SetupError(EXIT_DOWNLOAD_FAILED, "self_release_repo is not configured")

    release = github_release(
        config.self_release_repo,
        config.remote_timeout_sec,
        tag=release_tag or config.self_release_tag,
        channel=config.self_release_channel,
    )
    asset_name = select_self_release_asset(spec, backend)
    asset = github_asset_by_name(release, asset_name)
    tag_name = str(release.get("tag_name", "") or release_tag or config.self_release_tag or config.self_release_channel or "latest")
    cache_path = build_cached_asset_path(config.remote_cache_dir, f"self-release/{safe_filename(tag_name)}", asset_name)
    zip_path = download_with_retries(
        str(asset["browser_download_url"]),
        cache_path,
        timeout_sec=config.remote_timeout_sec,
        offline=offline,
        refresh=refresh,
    )
    return zip_path, release, asset


def select_bepinex_mono_asset(
    release: dict[str, Any],
    arch: str,
    overrides: dict[str, str],
) -> dict[str, Any]:
    assets = release.get("assets", [])
    pattern_key = f"bepinex_mono_win_{arch}"
    pattern = overrides.get(pattern_key)
    if not pattern:
        pattern = rf"BepInEx_win_{arch}_.+\.zip$"
    regex = re.compile(pattern, re.IGNORECASE)
    for asset in assets:
        name = str(asset.get("name", ""))
        if regex.search(name):
            return asset
    raise SetupError(EXIT_DOWNLOAD_FAILED, f"no mono BepInEx asset matched pattern: {pattern}")


def select_bepinex_be_il2cpp_asset(be_index_url: str, arch: str, overrides: dict[str, str], timeout_sec: int) -> dict[str, str]:
    req = urllib.request.Request(be_index_url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        html = resp.read().decode("utf-8", errors="ignore")

    hrefs = re.findall(r'href="([^"]+\.zip)"', html, re.IGNORECASE)
    if not hrefs:
        raise SetupError(EXIT_DOWNLOAD_FAILED, "no zip assets found on BepInEx BE index page")

    default_pattern = rf"BepInEx-Unity\.IL2CPP-win-{arch}-.+\.zip$|BepInEx_UnityIL2CPP_{arch}_.+\.zip$"
    pattern = overrides.get(f"bepinex_be_il2cpp_win_{arch}", default_pattern)
    regex = re.compile(pattern, re.IGNORECASE)

    matches: list[tuple[int, str, str]] = []
    for href in hrefs:
        absolute = urllib.parse.urljoin(be_index_url, href)
        decoded = urllib.parse.unquote(absolute)
        name = Path(decoded).name
        if not regex.search(name):
            continue
        build = 0
        m = re.search(r"/projects/bepinex_be/(\d+)/", decoded)
        if m:
            build = int(m.group(1))
        matches.append((build, name, absolute))

    if not matches:
        raise SetupError(EXIT_DOWNLOAD_FAILED, f"no IL2CPP BE asset matched pattern: {pattern}")

    matches.sort(key=lambda item: (item[0], item[1]), reverse=True)
    _, name, url = matches[0]
    return {"name": name, "browser_download_url": url}


def select_rue_asset(release: dict[str, Any], bepinex_major: int | None, variant: str, overrides: dict[str, str]) -> dict[str, Any]:
    assets = release.get("assets", [])
    is_v6 = (bepinex_major or 0) >= 6 or variant == "il2cpp"

    if is_v6:
        patterns = [
            overrides.get("rue_bepin6_il2cpp", r"RuntimeUnityEditor\.Bepin6\.IL2CPP_.+\.zip$"),
            overrides.get("rue_bepin6_any", r"RuntimeUnityEditor\.Bepin6.+\.zip$"),
        ]
    else:
        patterns = [overrides.get("rue_bepin5", r"RuntimeUnityEditor\.Bepin5_.+\.zip$")]

    for pattern in patterns:
        regex = re.compile(pattern, re.IGNORECASE)
        for asset in assets:
            name = str(asset.get("name", ""))
            if regex.search(name):
                return asset
    raise SetupError(EXIT_DOWNLOAD_FAILED, "no RuntimeUnityEditor asset matched current BepInEx major")


def select_cue_asset(release: dict[str, Any], bepinex_major: int | None, variant: str, overrides: dict[str, str]) -> dict[str, Any]:
    assets = release.get("assets", [])
    is_v6 = (bepinex_major or 0) >= 6 or variant == "il2cpp"

    if variant == "il2cpp":
        patterns = [
            overrides.get(
                "cue_bepin6_unity_il2cpp",
                r"CinematicUnityExplorer\.BepInEx\.Unity\.IL2CPP(?:\.CoreCLR)?\.zip$",
            ),
            overrides.get(
                "cue_bepin6_il2cpp",
                r"CinematicUnityExplorer\.BepInEx\.IL2CPP(?:\.CoreCLR)?\.zip$",
            ),
        ]
    elif is_v6:
        patterns = [
            overrides.get("cue_bepin6_unity_mono", r"CinematicUnityExplorer\.BepInEx6\.Unity\.Mono\.zip$"),
            overrides.get("cue_bepin6_mono", r"CinematicUnityExplorer\.BepInEx6\.Mono\.zip$"),
            overrides.get("cue_bepin5_mono_fallback", r"CinematicUnityExplorer\.BepInEx5\.Mono\.zip$"),
        ]
    else:
        patterns = [overrides.get("cue_bepin5_mono", r"CinematicUnityExplorer\.BepInEx5\.Mono\.zip$")]

    for pattern in patterns:
        regex = re.compile(pattern, re.IGNORECASE)
        for asset in assets:
            name = str(asset.get("name", ""))
            if regex.search(name):
                return asset
    raise SetupError(EXIT_DOWNLOAD_FAILED, "no CinematicUnityExplorer asset matched current BepInEx variant")


def select_config_manager_asset(
    release: dict[str, Any],
    bepinex_major: int | None,
    variant: str,
    overrides: dict[str, str],
) -> dict[str, Any]:
    assets = release.get("assets", [])
    is_v6 = (bepinex_major or 0) >= 6 or variant == "il2cpp"

    if variant == "il2cpp" or is_v6:
        patterns = [
            overrides.get("config_manager_il2cpp", r"BepInEx\.ConfigurationManager_IL2CPP_.+\.zip$"),
            overrides.get("config_manager_bepin5_fallback", r"BepInEx\.ConfigurationManager_BepInEx5_.+\.zip$"),
        ]
    else:
        patterns = [overrides.get("config_manager_bepin5", r"BepInEx\.ConfigurationManager_BepInEx5_.+\.zip$")]

    for pattern in patterns:
        regex = re.compile(pattern, re.IGNORECASE)
        for asset in assets:
            name = str(asset.get("name", ""))
            if regex.search(name):
                return asset
    raise SetupError(EXIT_DOWNLOAD_FAILED, "no BepInEx.ConfigurationManager asset matched current BepInEx variant")


def select_universal_unity_demosaics_asset(
    release: dict[str, Any],
    bepinex_major: int | None,
    variant: str,
    overrides: dict[str, str],
) -> dict[str, Any]:
    assets = release.get("assets", [])
    is_v6 = (bepinex_major or 0) >= 6 or variant == "il2cpp"

    if variant == "il2cpp" or is_v6:
        patterns = [
            overrides.get(
                "universal_unity_demosaics_bepin6_il2cpp_net6",
                r"UniversalUnityDemosaics_BepInEx6_IL2CPP_net6_.+\.zip$",
            ),
            overrides.get(
                "universal_unity_demosaics_bepin6_il2cpp_pre1",
                r"UniversalUnityDemosaics_BepInEx6_IL2CPP_pre1_.+\.zip$",
            ),
            overrides.get(
                "universal_unity_demosaics_bepin5_fallback",
                r"UniversalUnityDemosaics_BepInEx5_.+\.zip$",
            ),
        ]
    else:
        patterns = [
            overrides.get("universal_unity_demosaics_bepin5", r"UniversalUnityDemosaics_BepInEx5_.+\.zip$")
        ]

    for pattern in patterns:
        regex = re.compile(pattern, re.IGNORECASE)
        for asset in assets:
            name = str(asset.get("name", ""))
            if regex.search(name):
                return asset
    raise SetupError(EXIT_DOWNLOAD_FAILED, "no UniversalUnityDemosaics asset matched current BepInEx variant")


def safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._+-]", "_", name)


def download_with_retries(
    url: str,
    dst: Path,
    timeout_sec: int,
    retries: int = 3,
    offline: bool = False,
    refresh: bool = False,
) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if offline:
        if dst.exists() and dst.stat().st_size > 0:
            log(f"offline mode: using cached file {dst}")
            return dst
        raise SetupError(EXIT_DOWNLOAD_FAILED, f"offline mode but cache missing: {dst}")

    if dst.exists() and dst.stat().st_size > 0 and not refresh:
        log(f"using cached file {dst}")
        return dst

    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            tmp = dst.with_suffix(dst.suffix + ".tmp")
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp, tmp.open("wb") as f:
                shutil.copyfileobj(resp, f)
            if tmp.stat().st_size <= 0:
                raise SetupError(EXIT_DOWNLOAD_FAILED, f"downloaded empty file: {url}")
            tmp.replace(dst)
            return dst
        except Exception as e:
            last_error = e
            delay = 2**attempt
            log(f"download failed ({attempt + 1}/{retries}): {e}; retrying in {delay}s")
            time.sleep(delay)
    raise SetupError(EXIT_DOWNLOAD_FAILED, f"failed to download {url}: {last_error}")


def extract_zip(zip_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(destination)


def find_exporter_artifact_dir(backend: str = "mono", spec: ExporterSpec | None = None) -> Path | None:
    exporter = resolve_exporter_spec(spec)
    search_root = exporter.artifact_il2cpp_dir if backend == "il2cpp" else exporter.artifact_mono_dir
    if not search_root.exists():
        return None

    expected_name = exporter.il2cpp_dll_name if backend == "il2cpp" else exporter.mono_dll_name
    direct = search_root / expected_name
    if direct.exists():
        return direct.parent

    candidates = sorted(search_root.glob(f"**/{expected_name}"))
    if candidates:
        return candidates[0].parent
    return None


def ensure_exporter_artifacts(backend: str = "mono", spec: ExporterSpec | None = None) -> Path:
    exporter = resolve_exporter_spec(spec)
    existing = find_exporter_artifact_dir(backend, spec=exporter)
    if existing is not None:
        if backend == "il2cpp":
            _remove_stale_il2cpp_subdir(existing)
        return existing

    if _IS_FROZEN:
        expected = exporter.artifact_il2cpp_dir if backend == "il2cpp" else exporter.artifact_mono_dir
        raise SetupError(
            EXIT_INSTALL_FAILED,
            f"exporter artifacts were not bundled in executable runtime: {expected}",
        )

    if backend == "il2cpp":
        run_command(["dotnet", "build", str(exporter.project_il2cpp_csproj), "-c", "Release"], cwd=ROOT)
    else:
        run_command(["dotnet", "build", str(exporter.project_csproj), "-c", "Release"], cwd=ROOT)

    built = find_exporter_artifact_dir(backend, spec=exporter)
    if built is None:
        expected = exporter.artifact_il2cpp_dir if backend == "il2cpp" else exporter.artifact_mono_dir
        raise SetupError(EXIT_INSTALL_FAILED, f"exporter artifacts not found after build under: {expected}")
    if backend == "il2cpp":
        _remove_stale_il2cpp_subdir(built)
    return built


def ensure_exporter_dll(spec: ExporterSpec | None = None) -> Path:
    exporter = resolve_exporter_spec(spec)
    artifact_dir = ensure_exporter_artifacts("mono", spec=exporter)
    candidates = sorted(artifact_dir.glob(f"{exporter.project_name}*.dll"))
    if not candidates:
        raise SetupError(EXIT_INSTALL_FAILED, f"exporter dll not found in: {artifact_dir}")
    return candidates[0]


def copy_exporter_plugin(
    game_root: Path,
    source_dll: Path | None = None,
    backend: str = "mono",
    source_artifact_dir: Path | None = None,
    spec: ExporterSpec | None = None,
) -> Path:
    exporter = resolve_exporter_spec(spec)
    plugin_dir = game_root / "BepInEx" / "plugins" / exporter.plugin_dir_name
    plugin_dir.mkdir(parents=True, exist_ok=True)

    if source_artifact_dir is not None:
        if backend == "il2cpp":
            _remove_stale_il2cpp_subdir(source_artifact_dir)
        _copy_tree_contents(source_artifact_dir, plugin_dir)
        _remove_legacy_profile_dirs(plugin_dir)
        if backend == "il2cpp":
            _remove_stale_il2cpp_subdir(plugin_dir)
        return plugin_dir

    if source_dll is not None:
        shutil.copy2(source_dll, plugin_dir / source_dll.name)
        _remove_legacy_profile_dirs(plugin_dir)
        return plugin_dir

    artifact_dir = ensure_exporter_artifacts(backend, spec=exporter)
    _copy_tree_contents(artifact_dir, plugin_dir)
    _remove_legacy_profile_dirs(plugin_dir)
    if backend == "il2cpp":
        _remove_stale_il2cpp_subdir(plugin_dir)
    return plugin_dir


def _copy_tree_contents(source_dir: Path, destination_dir: Path) -> None:
    for path in source_dir.rglob("*"):
        rel = path.relative_to(source_dir)
        if any(part.lower() == "profiles" for part in rel.parts):
            continue
        dst = destination_dir / rel
        if path.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)


def _remove_legacy_profile_dirs(plugin_dir: Path) -> None:
    # Legacy layout copied `profiles/*.json` into plugin directory. The runtime
    # is now single-file profile (`profile.json`), so these directories must be removed.
    for path in plugin_dir.rglob("*"):
        if not path.is_dir():
            continue
        if path.name.lower() != "profiles":
            continue
        shutil.rmtree(path, ignore_errors=True)


def _remove_stale_il2cpp_subdir(plugin_dir: Path) -> None:
    # Previous IL2CPP builds emitted files under a nested `net6.0` directory.
    # Keep only the flattened output to avoid duplicate plugin discovery.
    stale = plugin_dir / "net6.0"
    if stale.is_dir():
        shutil.rmtree(stale, ignore_errors=True)


def _build_unknown_profile_template(spec: ExporterSpec | None = None) -> dict[str, Any]:
    exporter = resolve_exporter_spec(spec)
    return {
        PROFILE_MANAGED_BY_KEY: PROFILE_MANAGED_BY_VALUE,
        "id": "CUSTOM",
        "fullName": "Custom Profile",
        "version": "1.0",
        "streamerType": "skeleton",
        "processNames": [],
        "hooksStart": [],
        "hooksEnd": [],
        "hooksObserve": [],
        "controllerType": "Animator",
        "femaleControllerExpr": "",
        "maleControllerExpr": "",
        "femaleRootsExpr": "",
        "maleRootsExpr": "",
        "maxFemaleCount": 1,
        "maxMaleCount": 1,
        "useRegex": True,
        "poseLayer": 0,
        "poseLayerName": "",
        "rewindUnloop": True,
        "customPoseExpr": "",
        "customNormalizedTimeExpr": "",
        "customSpeedExpr": "",
        "customLengthExpr": "",
        "debugDumpFullHierarchy": False,
        "autoEndOnNoCharactersSeconds": 0,
        "keypoints": [
            {"kind": "FemaleRoot", "pathOrName": "", "required": True},
            {"kind": "MaleRoot", "pathOrName": "", "required": False},
            {"kind": "MalePenisBase", "pathOrName": "", "required": False},
            {"kind": "Vagina", "pathOrName": "", "required": False},
            {"kind": "Anus", "pathOrName": "", "required": False},
            {"kind": "Mouth", "pathOrName": "", "required": False},
            {"kind": "LeftHand", "pathOrName": "", "required": False},
            {"kind": "RightHand", "pathOrName": "", "required": False},
            {"kind": "LeftFoot", "pathOrName": "", "required": False},
            {"kind": "RightFoot", "pathOrName": "", "required": False},
        ],
    } if exporter.key == "default" else {
        PROFILE_MANAGED_BY_KEY: exporter.managed_by_value,
        "id": "CUSTOM_LIVE2D",
        "fullName": "Custom Live2D Profile",
        "version": "1.0",
        "streamerType": "live2d",
        "processNames": [],
        "hooksStart": [],
        "hooksEnd": [],
        "hooksObserve": [],
        "captureMode": "Auto",
        "live2dRootsExpr": "",
        "autoDiscoverCubism": True,
        "maxModelCount": 0,
        "activeOnly": True,
        "drawableNameIncludeRegex": "",
        "drawableNameExcludeRegex": "",
        "minBoundsExtent": 0.0001,
        "emitDrawablesBbox": True,
        "emitKeypointsFromDrawables": False,
        "keypointSchema": "unity.keypoints.realtime.v1",
        "keypoints": [],
    }


def _is_managed_profile(path: Path, spec: ExporterSpec | None = None) -> bool:
    exporter = resolve_exporter_spec(spec)
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return False
    return (
        isinstance(payload, dict)
        and str(payload.get(PROFILE_MANAGED_BY_KEY, "")) == exporter.managed_by_value
    )


def install_single_profile(
    game_root: Path,
    detection: DetectionResult,
    config: SetupConfig | None = None,
    spec: ExporterSpec | None = None,
    *,
    prefer_local_configs: bool | None = None,
    allow_remote_configs: bool | None = None,
    refresh_remote_cache: bool = False,
    offline: bool = False,
) -> tuple[Path, str, str]:
    exporter = resolve_exporter_spec(spec)
    plugin_dir = game_root / "BepInEx" / "plugins" / exporter.plugin_dir_name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    profile_path = plugin_dir / PROFILE_FILENAME

    # For unknown games, never overwrite an existing profile.json.
    if detection.game_type == "unknown" and profile_path.exists():
        return profile_path, "skipped_existing_custom", "existing"

    existing_managed = profile_path.exists() and _is_managed_profile(profile_path, spec=exporter)
    if profile_path.exists() and not existing_managed:
        return profile_path, "skipped_existing_custom", "existing"

    runtime_config = config or load_setup_config()
    prefer_local = _normalize_bool(prefer_local_configs, runtime_config.prefer_local_configs)
    allow_remote = _normalize_bool(allow_remote_configs, runtime_config.allow_remote_configs)

    game_spec = GAME_PROFILE_CATALOG.get(detection.game_type, {})
    template_name = str(game_spec.get("profile_template", "") or "").strip()
    payload: dict[str, Any] | None = None
    status = "updated_managed" if existing_managed else "installed_known"
    source = template_name

    if prefer_local:
        if template_name:
            local_match = load_local_profile_template(template_name)
        else:
            local_match = resolve_local_profile_for_detection(detection)
        if local_match is not None:
            payload, source = local_match
            status = "updated_managed" if existing_managed else "installed_known_local"

    manifest: dict[str, Any] | None = None
    if payload is None and allow_remote:
        manifest = load_remote_config_manifest(
            runtime_config,
            offline=offline,
            refresh=refresh_remote_cache,
        )
        entry = resolve_remote_profile_entry(manifest, detection)
        if entry is not None:
            payload, source = download_remote_profile_payload(
                entry,
                manifest,
                runtime_config,
                offline=offline,
                refresh=refresh_remote_cache,
            )
            status = "updated_managed" if existing_managed else "installed_known_remote"

    if payload is None:
        local_match = load_local_profile_template(template_name) if template_name else resolve_local_profile_for_detection(detection)
        if local_match is not None:
            payload, source = local_match
            status = "updated_managed" if existing_managed else "installed_known_local"

    if payload is None:
        payload = _build_unknown_profile_template(spec=exporter)
        status = "updated_managed" if existing_managed else "installed_unknown_template"
        source = "generated"
    elif not isinstance(payload, dict):
        raise SetupError(EXIT_INSTALL_FAILED, f"profile template is not an object: {source}")

    payload["streamerType"] = "live2d" if exporter.key == "live2d" else "skeleton"
    payload[PROFILE_MANAGED_BY_KEY] = exporter.managed_by_value
    profile_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return profile_path, status, source


def install_exporter_config(
    game_root: Path,
    detection: DetectionResult,
    spec: ExporterSpec | None = None,
) -> tuple[Path, str]:
    exporter = resolve_exporter_spec(spec)
    config_dir = game_root / "BepInEx" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = config_dir / exporter.config_filename

    marker = f"# Managed by {exporter.managed_by_value}"
    if cfg_path.exists():
        existing = cfg_path.read_text(encoding="utf-8", errors="ignore")
        if marker not in existing:
            return cfg_path, "skipped_existing_custom"

    profile_id = detection.profile_id or "unknown"

    if exporter.key == "default":
        text = "\n".join(
            [
                marker,
                f"# Auto profile: {profile_id}",
                f"# Process name: {detection.process_name}",
                "",
                "[Network]",
                "SkeletonHost = 127.0.0.1",
                "SkeletonPort = 39540",
                "MaxUdpPayloadBytes = 1200",
                "",
                "[Capture]",
                "TargetFps = 60",
                "PoseKeyStrategy = clip_then_statehash",
                "DebugDumpIncludeInactive = true",
                "",
            ]
        )
    else:
        text = "\n".join(
            [
                marker,
                f"# Auto profile: {profile_id}",
                f"# Process name: {detection.process_name}",
                "",
                "[Network]",
                "Live2DHost = 127.0.0.1",
                "Live2DPort = 39550",
                "MaxUdpPayloadBytes = 1200",
                "",
                "[Capture]",
                "TargetFps = 60",
                "CaptureMode = Auto",
                "DiscoveryIntervalMs = 1000",
                "DebugLogDiscovery = false",
                "",
            ]
        )
    cfg_path.write_text(text, encoding="utf-8")
    return cfg_path, "installed"


def backup_existing_install(game_root: Path) -> Path:
    timestamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = game_root / "backup" / timestamp
    backup_root.mkdir(parents=True, exist_ok=True)

    items = [
        "BepInEx",
        "doorstop_config.ini",
        "winhttp.dll",
    ]
    for name in items:
        src = game_root / name
        if not src.exists():
            continue
        dst = backup_root / name
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    return backup_root


def remove_existing_install(game_root: Path) -> None:
    for name in ("BepInEx",):
        path = game_root / name
        if path.exists():
            shutil.rmtree(path)
    for name in ("doorstop_config.ini", "winhttp.dll"):
        path = game_root / name
        if path.exists():
            path.unlink()


def bepinex_variant_matches_backend(backend: str, variant: str) -> bool:
    if backend not in ("mono", "il2cpp"):
        return True
    if variant in ("unknown", "none"):
        return True
    return backend == variant


def build_cached_asset_path(cache_dir: Path, category: str, name: str) -> Path:
    return cache_dir / category / safe_filename(name)


def find_exporter_dll(spec: ExporterSpec | None = None) -> Path | None:
    exporter = resolve_exporter_spec(spec)
    artifact_dir = find_exporter_artifact_dir("mono", spec=exporter)
    if artifact_dir is None:
        return None
    candidates = sorted(artifact_dir.glob(f"{exporter.project_name}*.dll"))
    return candidates[0] if candidates else None
