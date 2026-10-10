"""Unity exporter setup: installation responsibility."""
from __future__ import annotations

import datetime as _dt
import json
import shutil
from pathlib import Path
from typing import Any

from .paths import (
    EXIT_INSTALL_FAILED,
)
from .models import (
    DetectionResult,
    ExporterSpec,
    PROFILE_FILENAME,
    PROFILE_MANAGED_BY_KEY,
    PROFILE_MANAGED_BY_VALUE,
    SetupConfig,
    SetupError,
    resolve_exporter_spec,
)
from .commands import (
    log,
)
from .configuration import (
    load_setup_config,
)
from .profiles import (
    GAME_PROFILE_CATALOG,
    _normalize_bool,
    download_remote_profile_payload,
    load_local_profile_template,
    load_remote_config_manifest,
    resolve_local_profile_for_detection,
    resolve_remote_profile_entry,
)
from .artifacts import (
    _remove_stale_il2cpp_subdir,
    ensure_exporter_artifacts,
)


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
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        log(f"warning: preserving unreadable profile {path}: {exc}")
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

    game_spec = GAME_PROFILE_CATALOG.get(detection.game_type)
    template_name = game_spec.profile_template.strip() if game_spec is not None else ""
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
