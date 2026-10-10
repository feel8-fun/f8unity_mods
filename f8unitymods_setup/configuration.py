"""Unity exporter setup: configuration responsibility."""
from __future__ import annotations

import json
from pathlib import Path

from .paths import (
    ROOT,
    RUNTIME_ROOT,
    _SOURCE_ROOT,
)
from .models import (
    SetupConfig,
)


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
        cache_base = ROOT if ROOT == _SOURCE_ROOT else RUNTIME_ROOT
        cache_dir = cache_base / cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)

    remote_cache_dir = Path(defaults["remote_cache_dir"])
    if not remote_cache_dir.is_absolute():
        cache_base = ROOT if ROOT == _SOURCE_ROOT else RUNTIME_ROOT
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
