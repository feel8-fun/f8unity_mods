"""Unity exporter setup: profiles responsibility."""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .paths import (
    EXIT_DOWNLOAD_FAILED,
    EXIT_INSTALL_FAILED,
    ROOT,
    RUNTIME_ROOT,
)
from .models import (
    DetectionResult,
    GameProfile,
    SetupConfig,
    SetupError,
    infer_exporter_key_from_profile_payload,
)
from .commands import (
    log,
)
from .artifacts import (
    download_with_retries,
    safe_filename,
    sha256_file,
)


def _normalize_process_name(value: str) -> str:
    return re.sub(r"[\s_-]+", "", value or "").lower()


def _load_game_profile_catalog() -> dict[str, GameProfile]:
    catalog: dict[str, GameProfile] = {}
    configs_dir = ROOT / "configs"
    if not configs_dir.is_dir():
        return catalog

    for path in sorted(configs_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid bundled game profile {path}: {exc}") from exc
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
        catalog[game_type] = GameProfile(profile_id=profile_id, profile_template=path.name,
                                         aliases=tuple(dedup_aliases), exporter_key=exporter_key)

    return catalog


GAME_PROFILE_CATALOG: dict[str, GameProfile] = _load_game_profile_catalog()


def detect_game_profile(process_name: str) -> tuple[str, str, str]:
    normalized = _normalize_process_name(process_name)
    for game_type, spec in GAME_PROFILE_CATALOG.items():
        aliases = [_normalize_process_name(alias) for alias in spec.aliases]
        if normalized in aliases:
            return (
                game_type,
                spec.profile_id,
                spec.exporter_key,
            )
    return "unknown", "", "auto"


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
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        log(f"warning: failed to read JSON file {path}: {exc}")
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
        except (OSError, RuntimeError) as exc:
            log(f"warning: failed to resolve config directory {candidate}: {exc}")
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
