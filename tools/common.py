from __future__ import annotations

import dataclasses
import datetime as _dt
import json
import os
import re
import shutil
import struct
import subprocess
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

USER_AGENT = "f8-hscene-animator-streamer-helper"

ROOT = Path(__file__).resolve().parents[1]
PROJECT_CSPROJ = ROOT / "src" / "F8HSceneAnimatorStreamer" / "F8HSceneAnimatorStreamer.csproj"
PROJECT_IL2CPP_CSPROJ = (
    ROOT / "src" / "F8HSceneAnimatorStreamer.IL2CPP" / "F8HSceneAnimatorStreamer.IL2CPP.csproj"
)
EXPORTER_DLL_DIR = (
    ROOT / "src" / "bin" / "F8HSceneAnimatorStreamer" / "BepInEx" / "plugins" / "F8HSceneAnimatorStreamer"
)
EXPORTER_DLL = EXPORTER_DLL_DIR / "F8HSceneAnimatorStreamer.dll"
EXPORTER_IL2CPP_DIR = (
    ROOT
    / "src"
    / "bin"
    / "F8HSceneAnimatorStreamer.IL2CPP"
    / "BepInEx"
    / "plugins"
    / "F8HSceneAnimatorStreamer"
)
EXPORTER_README = ROOT / "src" / "F8HSceneAnimatorStreamer" / "README.md"


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
        catalog[game_type] = {
            "profile_id": profile_id,
            "profile_template": path.name,
            "aliases": dedup_aliases,
        }

    return catalog


GAME_PROFILE_CATALOG: dict[str, dict[str, Any]] = _load_game_profile_catalog()

PROFILE_MANAGED_BY_KEY = "_managed_by"
PROFILE_MANAGED_BY_VALUE = "tools/game_setup.py"
PROFILE_FILENAME = "profile.json"


@dataclasses.dataclass
class SetupConfig:
    bepinex_release_repo: str
    bepinex_be_index_url: str
    rue_release_repo: str
    cue_release_repo: str
    config_manager_release_repo: str
    universal_unity_demosaics_release_repo: str
    cache_dir: Path
    timeout_sec: int
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
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def log(message: str) -> None:
    print(f"[helper] {message}")


def load_setup_config(path: Path | None = None) -> SetupConfig:
    defaults = {
        "bepinex_release_repo": "BepInEx/BepInEx",
        "bepinex_be_index_url": "https://builds.bepinex.dev/projects/bepinex_be",
        "rue_release_repo": "ManlyMarco/RuntimeUnityEditor",
        "cue_release_repo": "originalnicodr/CinematicUnityExplorer",
        "config_manager_release_repo": "BepInEx/BepInEx.ConfigurationManager",
        "universal_unity_demosaics_release_repo": "ManlyMarco/UniversalUnityDemosaics",
        "cache_dir": ".cache/unity_exporter_helper",
        "timeout_sec": 30,
        "asset_regex_overrides": {},
    }

    config_path = path or (ROOT / "tools" / "game_setup_config.json")
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            custom = json.load(f)
        defaults.update(custom or {})

    cache_dir = Path(defaults["cache_dir"])
    if not cache_dir.is_absolute():
        cache_dir = ROOT / cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)

    return SetupConfig(
        bepinex_release_repo=str(defaults["bepinex_release_repo"]),
        bepinex_be_index_url=str(defaults["bepinex_be_index_url"]),
        rue_release_repo=str(defaults["rue_release_repo"]),
        cue_release_repo=str(defaults["cue_release_repo"]),
        config_manager_release_repo=str(defaults["config_manager_release_repo"]),
        universal_unity_demosaics_release_repo=str(defaults["universal_unity_demosaics_release_repo"]),
        cache_dir=cache_dir,
        timeout_sec=int(defaults["timeout_sec"]),
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

    data_dir = game_root / f"{exe_path.stem}_Data"
    if not data_dir.exists():
        possible = sorted(p for p in game_root.glob("*_Data") if p.is_dir())
        if len(possible) == 1:
            data_dir = possible[0]
        else:
            raise SetupError(
                EXIT_DETECT_FAILED,
                f"cannot resolve Unity data directory for {exe_path.name}; expected {data_dir.name}",
            )

    return game_root, exe_path, data_dir


def _find_primary_exe(game_root: Path) -> Path:
    exclusions = (
        "unitycrashhandler",
        "unitycrashhandler64",
        "doorstop",
        "bepinex.preloader",
    )
    candidates = []
    for exe in game_root.glob("*.exe"):
        lower = exe.name.lower()
        if any(lower.startswith(prefix) for prefix in exclusions):
            continue
        if lower == "winhttp.dll":
            continue
        has_data = (game_root / f"{exe.stem}_Data").is_dir()
        score = (100 if has_data else 0) + int(exe.stat().st_size / (1024 * 1024))
        candidates.append((score, exe.name.lower(), exe))
    if not candidates:
        raise SetupError(EXIT_DETECT_FAILED, f"no candidate game exe found in {game_root}")
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2]


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
    game_root, exe_path, data_dir = normalize_game_target(target)
    process_name = exe_path.stem
    game_type, profile_id = detect_game_profile(process_name)
    backend = detect_backend(game_root, data_dir)
    arch = detect_arch(exe_path)
    unity_version = detect_unity_version(data_dir)
    has_bep, bep_variant, bep_ver, bep_major = detect_bepinex(game_root)
    return DetectionResult(
        target_input=target,
        game_root=game_root,
        exe_path=exe_path,
        data_dir=data_dir,
        process_name=process_name,
        game_type=game_type,
        profile_id=profile_id,
        unity_version=unity_version,
        backend=backend,
        arch=arch,
        has_bepinex=has_bep,
        bepinex_variant=bep_variant,
        bepinex_version=bep_ver,
        bepinex_major=bep_major,
    )


def detect_game_profile(process_name: str) -> tuple[str, str]:
    normalized = _normalize_process_name(process_name)
    for game_type, spec in GAME_PROFILE_CATALOG.items():
        aliases = [_normalize_process_name(alias) for alias in spec.get("aliases", [])]
        if normalized in aliases:
            return game_type, str(spec.get("profile_id", "") or "")
    return "unknown", ""


def github_latest_release(repo: str, timeout_sec: int) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        return json.loads(resp.read().decode("utf-8"))


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


def download_with_retries(url: str, dst: Path, timeout_sec: int, retries: int = 3, offline: bool = False) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if offline:
        if dst.exists() and dst.stat().st_size > 0:
            log(f"offline mode: using cached file {dst}")
            return dst
        raise SetupError(EXIT_DOWNLOAD_FAILED, f"offline mode but cache missing: {dst}")

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


def find_exporter_artifact_dir(backend: str = "mono") -> Path | None:
    search_root = EXPORTER_IL2CPP_DIR if backend == "il2cpp" else EXPORTER_DLL_DIR
    if not search_root.exists():
        return None

    expected_name = "F8HSceneAnimatorStreamer.IL2CPP.dll" if backend == "il2cpp" else "F8HSceneAnimatorStreamer.dll"
    direct = search_root / expected_name
    if direct.exists():
        return direct.parent

    candidates = sorted(search_root.glob(f"**/{expected_name}"))
    if candidates:
        return candidates[0].parent
    return None


def ensure_exporter_artifacts(backend: str = "mono") -> Path:
    existing = find_exporter_artifact_dir(backend)
    if existing is not None:
        return existing

    if backend == "il2cpp":
        run_command(["dotnet", "build", str(PROJECT_IL2CPP_CSPROJ), "-c", "Release"], cwd=ROOT)
    else:
        run_command(["dotnet", "build", str(PROJECT_CSPROJ), "-c", "Release"], cwd=ROOT)

    built = find_exporter_artifact_dir(backend)
    if built is None:
        expected = EXPORTER_IL2CPP_DIR if backend == "il2cpp" else EXPORTER_DLL_DIR
        raise SetupError(EXIT_INSTALL_FAILED, f"exporter artifacts not found after build under: {expected}")
    return built


def ensure_exporter_dll() -> Path:
    artifact_dir = ensure_exporter_artifacts("mono")
    candidates = sorted(artifact_dir.glob("F8HSceneAnimatorStreamer*.dll"))
    if not candidates:
        raise SetupError(EXIT_INSTALL_FAILED, f"exporter dll not found in: {artifact_dir}")
    return candidates[0]


def copy_exporter_plugin(
    game_root: Path,
    source_dll: Path | None = None,
    backend: str = "mono",
    source_artifact_dir: Path | None = None,
) -> Path:
    plugin_dir = game_root / "BepInEx" / "plugins" / "F8HSceneAnimatorStreamer"
    plugin_dir.mkdir(parents=True, exist_ok=True)

    if source_artifact_dir is not None:
        _copy_tree_contents(source_artifact_dir, plugin_dir)
        _remove_legacy_profile_dirs(plugin_dir)
        return plugin_dir

    if source_dll is not None:
        shutil.copy2(source_dll, plugin_dir / source_dll.name)
        _remove_legacy_profile_dirs(plugin_dir)
        return plugin_dir

    artifact_dir = ensure_exporter_artifacts(backend)
    _copy_tree_contents(artifact_dir, plugin_dir)
    _remove_legacy_profile_dirs(plugin_dir)
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


def resolve_profile_template_path(profile_template_name: str) -> Path:
    name = profile_template_name.strip()
    if not name:
        raise SetupError(EXIT_INSTALL_FAILED, "profile template name is empty")
    candidates = [ROOT / "configs" / name]
    for path in candidates:
        if path.exists():
            return path
    raise SetupError(EXIT_INSTALL_FAILED, f"profile template not found: {candidates[0]}")


def _build_unknown_profile_template() -> dict[str, Any]:
    return {
        PROFILE_MANAGED_BY_KEY: PROFILE_MANAGED_BY_VALUE,
        "id": "CUSTOM",
        "fullName": "Custom Profile",
        "version": "1.0",
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
    }


def _is_managed_profile(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return False
    return (
        isinstance(payload, dict)
        and str(payload.get(PROFILE_MANAGED_BY_KEY, "")) == PROFILE_MANAGED_BY_VALUE
    )


def install_single_profile(game_root: Path, detection: DetectionResult) -> tuple[Path, str, str]:
    plugin_dir = game_root / "BepInEx" / "plugins" / "F8HSceneAnimatorStreamer"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    profile_path = plugin_dir / PROFILE_FILENAME

    # For unknown games, never overwrite an existing profile.json.
    if detection.game_type == "unknown" and profile_path.exists():
        return profile_path, "skipped_existing_custom", "existing"

    existing_managed = profile_path.exists() and _is_managed_profile(profile_path)
    if profile_path.exists() and not existing_managed:
        return profile_path, "skipped_existing_custom", "existing"

    game_spec = GAME_PROFILE_CATALOG.get(detection.game_type, {})
    template_name = str(game_spec.get("profile_template", "") or "").strip()
    if template_name:
        template_path = resolve_profile_template_path(template_name)
        payload = json.loads(template_path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            raise SetupError(EXIT_INSTALL_FAILED, f"profile template is not an object: {template_path}")
        payload[PROFILE_MANAGED_BY_KEY] = PROFILE_MANAGED_BY_VALUE
        status = "updated_managed" if existing_managed else "installed_known"
        source = template_name
    else:
        payload = _build_unknown_profile_template()
        status = "updated_managed" if existing_managed else "installed_unknown_template"
        source = "generated"

    profile_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return profile_path, status, source


def install_exporter_config(game_root: Path, detection: DetectionResult) -> tuple[Path, str]:
    config_dir = game_root / "BepInEx" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = config_dir / "com.feel8.f8-hscene-animator-streamer.cfg"

    marker = "# Managed by tools/game_setup.py"
    if cfg_path.exists():
        existing = cfg_path.read_text(encoding="utf-8", errors="ignore")
        if marker not in existing:
            return cfg_path, "skipped_existing_custom"

    profile_id = detection.profile_id or "unknown"

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


def find_exporter_dll() -> Path | None:
    artifact_dir = find_exporter_artifact_dir("mono")
    if artifact_dir is None:
        return None
    candidates = sorted(artifact_dir.glob("F8HSceneAnimatorStreamer*.dll"))
    return candidates[0] if candidates else None
