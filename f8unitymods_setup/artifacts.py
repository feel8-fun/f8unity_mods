"""Unity exporter setup: artifacts responsibility."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from .paths import (
    EXIT_DOWNLOAD_FAILED,
    EXIT_INSTALL_FAILED,
    ROOT,
    USER_AGENT,
    _IS_FROZEN,
)
from .models import (
    ExporterSpec,
    SetupConfig,
    SetupError,
    resolve_exporter_spec,
)
from .commands import (
    log,
    run_command,
)


def github_latest_release(repo: str, timeout_sec: int) -> dict[str, Any]:
    return github_release(repo, timeout_sec)


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
        except (OSError, ValueError, SetupError) as e:
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


def _remove_stale_il2cpp_subdir(plugin_dir: Path) -> None:
    # Previous IL2CPP builds emitted files under a nested `net6.0` directory.
    # Keep only the flattened output to avoid duplicate plugin discovery.
    stale = plugin_dir / "net6.0"
    if stale.is_dir():
        shutil.rmtree(stale, ignore_errors=True)


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
