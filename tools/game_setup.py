from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any

from common import (
    EXIT_BEPINEX_MISMATCH,
    EXIT_DETECT_FAILED,
    EXIT_DOWNLOAD_FAILED,
    EXIT_INSTALL_FAILED,
    DetectionResult,
    SetupConfig,
    SetupError,
    backup_existing_install,
    bepinex_variant_matches_backend,
    build_cached_asset_path,
    copy_exporter_plugin,
    detect_bepinex,
    detect_game,
    download_self_release_asset,
    github_release,
    ensure_exporter_artifacts,
    extract_zip,
    github_latest_release,
    infer_exporter_key_from_profile_payload,
    install_single_profile,
    install_exporter_config,
    load_setup_config,
    log,
    print_json,
    remove_existing_install,
    resolve_exporter_spec_by_key,
    select_cue_asset,
    select_config_manager_asset,
    select_bepinex_be_il2cpp_asset,
    select_bepinex_mono_asset,
    select_rue_asset,
    select_universal_unity_demosaics_asset,
    download_with_retries,
)


def _normalize_exporter_flag(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if raw in ("live2d", "f8live2dstreamer", "live2dstreamer"):
        return "live2d"
    if raw in ("skeleton", "default", "f8skeletonstreamer", "skeletonstreamer"):
        return "default"
    return "auto"


def _resolve_install_exporter_key(
    detection: DetectionResult,
    forced: str | None,
    game_root: Path | None = None,
) -> str:
    selected = _normalize_exporter_flag(forced)
    if selected in ("default", "live2d"):
        return selected
    if detection.exporter_key in ("default", "live2d"):
        return detection.exporter_key

    if game_root is not None:
        inferred = _infer_exporter_from_existing_profiles(game_root)
        if inferred in ("default", "live2d"):
            return inferred

    return "default"


def _infer_exporter_from_existing_profiles(game_root: Path) -> str:
    candidates = [
        ("live2d", game_root / "BepInEx" / "plugins" / "F8Live2DStreamer" / "profile.json"),
        ("default", game_root / "BepInEx" / "plugins" / "F8SkeletonStreamer" / "profile.json"),
    ]
    for fallback_key, path in candidates:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        inferred = infer_exporter_key_from_profile_payload(payload)
        if inferred in ("default", "live2d"):
            return inferred
        return fallback_key
    return ""


_PROMPT_ABORT_WORDS = {"q", "quit", "exit"}


def _is_interactive_session(args: argparse.Namespace) -> bool:
    if bool(getattr(args, "non_interactive", False)):
        return False
    if bool(getattr(args, "interactive", False)):
        return True
    return bool(getattr(sys.stdin, "isatty", lambda: False)())


def _prompt_target_path() -> str:
    while True:
        try:
            raw = input("Enter game path (.exe or game folder), or 'q' to abort: ").strip().strip('"')
        except EOFError as e:
            raise SetupError(EXIT_DETECT_FAILED, "interactive input unavailable while reading game path") from e
        if raw.lower() in _PROMPT_ABORT_WORDS:
            raise SetupError(EXIT_DETECT_FAILED, "install aborted by user")
        if not raw:
            print("Path is empty. Please try again.")
            continue
        candidate = Path(raw).expanduser()
        if candidate.exists():
            return raw
        print(f"Path does not exist: {candidate}")


def _prompt_exporter_choice() -> str:
    while True:
        try:
            raw = input("Unknown game. Install which exporter? [1] skeleton [2] live2d (or q): ").strip().lower()
        except EOFError as e:
            raise SetupError(EXIT_DETECT_FAILED, "interactive input unavailable while reading exporter choice") from e
        if raw in _PROMPT_ABORT_WORDS:
            raise SetupError(EXIT_DETECT_FAILED, "install aborted by user")
        if raw in ("1", "s", "skeleton", "default"):
            return "default"
        if raw in ("2", "l", "live2d"):
            return "live2d"
        print("Invalid choice. Enter 1 for skeleton or 2 for live2d.")


def _build_install_plan(
    detection: DetectionResult,
    force_reinstall: bool,
    skip_exporter: bool,
    install_rue: bool,
    install_cue: bool,
    install_config_manager: bool,
    install_uud: bool,
    prefer_local_configs: bool,
    allow_remote_configs: bool,
    refresh_remote_cache: bool,
    release_tag: str,
) -> dict[str, Any]:
    actions: list[str] = []
    blocking: list[str] = []

    if detection.backend == "unknown":
        blocking.append("Unity backend is unknown (expected mono or il2cpp).")
    if detection.arch == "unknown":
        blocking.append("Game architecture is unknown (expected x86 or x64).")

    if detection.has_bepinex:
        if not bepinex_variant_matches_backend(detection.backend, detection.bepinex_variant):
            if force_reinstall:
                actions.append("backup_and_reinstall_bepinex")
            else:
                blocking.append("Existing BepInEx variant mismatches game backend; use --force-reinstall.")
        else:
            actions.append("keep_existing_bepinex")
    else:
        actions.append("install_bepinex")

    if not skip_exporter:
        actions.append("install_exporter")
        actions.append("install_exporter_config")
        actions.append("install_profile")
    if install_rue:
        actions.append("install_runtime_unity_editor")
    if install_cue:
        actions.append("install_cinematic_unity_explorer")
    if install_config_manager:
        actions.append("install_configuration_manager")
    if install_uud:
        actions.append("install_universal_unity_demosaics")

    config_mode = "local_first" if prefer_local_configs else "remote_then_local"
    if not allow_remote_configs:
        config_mode = "local_only"

    actions.append(f"profile_resolution:{config_mode}")
    if refresh_remote_cache:
        actions.append("refresh_remote_config_cache")
    if str(release_tag or "").strip():
        actions.append(f"pin_self_release:{release_tag}")

    return {"actions": actions, "blocking_errors": blocking}


def run_detect(target: str, config: SetupConfig) -> dict[str, Any]:
    _ = config
    detection = detect_game(target)
    return detection.to_public_dict()


def run_diagnose(
    target: str,
    config: SetupConfig,
    *,
    exporter: str = "auto",
    prefer_local_configs: bool | None = None,
    allow_remote_configs: bool | None = None,
    refresh_remote_cache: bool = False,
    release_tag: str = "",
    force_reinstall: bool = False,
    skip_exporter: bool = False,
    rue: bool = False,
    cue: bool = False,
    config_manager: bool = False,
    uud: bool = False,
    offline: bool = False,
) -> dict[str, Any]:
    _ = config
    detection = detect_game(target)
    selected_exporter_key = _resolve_install_exporter_key(detection, exporter, detection.game_root)
    selected_spec = resolve_exporter_spec_by_key(selected_exporter_key)
    prefer_local = config.prefer_local_configs if prefer_local_configs is None else bool(prefer_local_configs)
    allow_remote = config.allow_remote_configs if allow_remote_configs is None else bool(allow_remote_configs)
    plan = _build_install_plan(
        detection,
        force_reinstall,
        skip_exporter,
        rue,
        cue,
        config_manager,
        uud,
        prefer_local,
        allow_remote,
        refresh_remote_cache,
        release_tag,
    )
    return {
        "detection": detection.to_public_dict(),
        "selected_exporter": {
            "key": selected_exporter_key,
            "project_name": selected_spec.project_name,
            "plugin_dir": selected_spec.plugin_dir_name,
            "config_filename": selected_spec.config_filename,
        },
        "installer_options": {
            "prefer_local_configs": prefer_local,
            "allow_remote_configs": allow_remote,
            "refresh_remote_cache": bool(refresh_remote_cache),
            "release_tag": str(release_tag or ""),
        },
        "plan": plan,
        "offline": offline,
    }


def _install_exporter_plugin(
    detection: DetectionResult,
    config: SetupConfig,
    exporter_key: str,
    *,
    release_tag: str = "",
    offline: bool = False,
    refresh_remote_cache: bool = False,
) -> tuple[Path, dict[str, Any]]:
    exporter_spec = resolve_exporter_spec_by_key(exporter_key)

    try:
        zip_path, release, asset = download_self_release_asset(
            exporter_spec,
            detection.backend,
            config,
            release_tag=release_tag,
            offline=offline,
            refresh=refresh_remote_cache,
        )
        extract_zip(zip_path, detection.game_root)
        metadata = {
            "source": "remote_release",
            "zip_path": str(zip_path),
            "asset_name": str(asset.get("name", "")),
            "release_tag": str(release.get("tag_name", "") or release_tag),
        }
        return detection.game_root / "BepInEx" / "plugins" / exporter_spec.plugin_dir_name, metadata
    except Exception as e:
        artifact_dir = ensure_exporter_artifacts(detection.backend, spec=exporter_spec)
        installed = copy_exporter_plugin(
            detection.game_root,
            backend=detection.backend,
            source_artifact_dir=artifact_dir,
            spec=exporter_spec,
        )
        metadata = {
            "source": "local_artifact",
            "artifact_dir": str(artifact_dir),
            "fallback_reason": str(e),
        }
        return installed, metadata


def run_install(
    target: str,
    config: SetupConfig,
    *,
    exporter: str = "auto",
    prefer_local_configs: bool | None = None,
    allow_remote_configs: bool | None = None,
    refresh_remote_cache: bool = False,
    release_tag: str = "",
    force_reinstall: bool = False,
    rue: bool = False,
    cue: bool = False,
    config_manager: bool = False,
    uud: bool = False,
    skip_exporter: bool = False,
    offline: bool = False,
    interaction_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    detection = detect_game(target)
    if detection.backend == "unknown":
        raise SetupError(EXIT_DETECT_FAILED, "cannot install: backend is unknown")
    if detection.arch == "unknown":
        raise SetupError(EXIT_DETECT_FAILED, "cannot install: architecture is unknown")

    summary: dict[str, Any] = {
        "game_root": str(detection.game_root),
        "process_name": detection.process_name,
        "game_type": detection.game_type,
        "profile_id": detection.profile_id,
        "detected_exporter_key": detection.exporter_key,
        "backend": detection.backend,
        "arch": detection.arch,
        "actions": [],
        "interaction_used": False,
        "interactive_decisions": {
            "target_prompted": False,
            "exporter_prompted": False,
            "exporter_selected": None,
        },
    }
    if isinstance(interaction_meta, dict):
        summary["interaction_used"] = bool(interaction_meta.get("interaction_used", False))
        summary["interactive_decisions"] = {
            "target_prompted": bool(interaction_meta.get("target_prompted", False)),
            "exporter_prompted": bool(interaction_meta.get("exporter_prompted", False)),
            "exporter_selected": interaction_meta.get("exporter_selected"),
        }

    selected_exporter_key = _resolve_install_exporter_key(detection, exporter, detection.game_root)
    exporter_spec = resolve_exporter_spec_by_key(selected_exporter_key)
    prefer_local = config.prefer_local_configs if prefer_local_configs is None else bool(prefer_local_configs)
    allow_remote = config.allow_remote_configs if allow_remote_configs is None else bool(allow_remote_configs)
    summary["selected_exporter"] = {
        "key": selected_exporter_key,
        "project_name": exporter_spec.project_name,
        "plugin_dir": exporter_spec.plugin_dir_name,
        "config_filename": exporter_spec.config_filename,
    }
    summary["installer_options"] = {
        "prefer_local_configs": prefer_local,
        "allow_remote_configs": allow_remote,
        "refresh_remote_cache": bool(refresh_remote_cache),
        "release_tag": str(release_tag or ""),
    }

    if detection.has_bepinex and not bepinex_variant_matches_backend(detection.backend, detection.bepinex_variant):
        if not force_reinstall:
            raise SetupError(
                EXIT_BEPINEX_MISMATCH,
                f"existing BepInEx variant '{detection.bepinex_variant}' mismatches backend '{detection.backend}', "
                "rerun with --force-reinstall to replace it",
            )
        backup_dir = backup_existing_install(detection.game_root)
        remove_existing_install(detection.game_root)
        summary["actions"].append({"backup_existing_bepinex": str(backup_dir)})
        detection = _install_bepinex(detection, config, offline=offline)
        summary["actions"].append({"install_bepinex": "reinstalled"})
    elif not detection.has_bepinex:
        detection = _install_bepinex(detection, config, offline=offline)
        summary["actions"].append({"install_bepinex": "installed"})
    else:
        summary["actions"].append({"install_bepinex": "skipped_existing"})

    if not skip_exporter:
        installed, exporter_install_meta = _install_exporter_plugin(
            detection,
            config,
            selected_exporter_key,
            release_tag=release_tag,
            offline=offline,
            refresh_remote_cache=refresh_remote_cache,
        )
        config_path, config_status = install_exporter_config(
            detection.game_root,
            detection,
            spec=exporter_spec,
        )
        profile_path, profile_status, profile_source = install_single_profile(
            detection.game_root,
            detection,
            config=config,
            spec=exporter_spec,
            prefer_local_configs=prefer_local,
            allow_remote_configs=allow_remote,
            refresh_remote_cache=refresh_remote_cache,
            offline=offline,
        )
        summary["actions"].append(
            {
                "install_exporter": {
                    "plugin_dir": str(installed),
                    "backend": detection.backend,
                    "source": exporter_install_meta.get("source"),
                    "release_tag": exporter_install_meta.get("release_tag"),
                    "asset_name": exporter_install_meta.get("asset_name"),
                    "artifact_dir": exporter_install_meta.get("artifact_dir"),
                    "fallback_reason": exporter_install_meta.get("fallback_reason"),
                    "config_path": str(config_path),
                    "config_status": config_status,
                }
            }
        )
        summary["actions"].append(
            {
                "install_profile": {
                    "path": str(profile_path),
                    "status": profile_status,
                    "source": profile_source,
                }
            }
        )
        summary["exporter_plugin_dir"] = str(installed)
        summary["exporter_config"] = {"path": str(config_path), "status": config_status}
        summary["profile"] = {"path": str(profile_path), "status": profile_status, "source": profile_source}
    else:
        summary["actions"].append({"install_exporter": "skipped"})
        summary["actions"].append({"install_profile": "skipped"})

    if rue:
        rue_path = _install_runtime_unity_editor(detection, config, offline=offline)
        summary["actions"].append({"install_runtime_unity_editor": str(rue_path)})
    else:
        summary["actions"].append({"install_runtime_unity_editor": "skipped"})

    if cue:
        cue_path, cue_config_path, cue_config_status = _install_cinematic_unity_explorer(
            detection, config, offline=offline
        )
        summary["actions"].append({"install_cinematic_unity_explorer": str(cue_path)})
        summary["actions"].append(
            {
                "install_cinematic_unity_explorer_config": {
                    "path": str(cue_config_path),
                    "status": cue_config_status,
                }
            }
        )
    else:
        summary["actions"].append({"install_cinematic_unity_explorer": "skipped"})
        summary["actions"].append({"install_cinematic_unity_explorer_config": "skipped"})

    if config_manager:
        config_manager_path = _install_configuration_manager(detection, config, offline=offline)
        summary["actions"].append({"install_configuration_manager": str(config_manager_path)})
    else:
        summary["actions"].append({"install_configuration_manager": "skipped"})

    if uud:
        uud_path = _install_universal_unity_demosaics(detection, config, offline=offline)
        summary["actions"].append({"install_universal_unity_demosaics": str(uud_path)})
    else:
        summary["actions"].append({"install_universal_unity_demosaics": "skipped"})

    return summary


def cmd_detect(args: argparse.Namespace, config: SetupConfig) -> None:
    print_json(run_detect(args.target, config))


def cmd_diagnose(args: argparse.Namespace, config: SetupConfig) -> None:
    print_json(
        run_diagnose(
            target=args.target,
            config=config,
            exporter=args.exporter,
            prefer_local_configs=args.prefer_local_configs,
            allow_remote_configs=not args.no_remote_configs,
            refresh_remote_cache=args.refresh_config_cache,
            release_tag=args.release_tag,
            force_reinstall=args.force_reinstall,
            skip_exporter=args.skip_exporter,
            rue=args.rue,
            cue=args.cue,
            config_manager=args.config_manager,
            uud=args.uud,
            offline=args.offline,
        )
    )


def cmd_install(args: argparse.Namespace, config: SetupConfig) -> None:
    interactive_enabled = _is_interactive_session(args)
    interaction_meta: dict[str, Any] = {
        "interaction_used": False,
        "target_prompted": False,
        "exporter_prompted": False,
        "exporter_selected": None,
    }

    target = str(args.target or "").strip()
    if not target:
        if not interactive_enabled:
            raise SetupError(
                EXIT_DETECT_FAILED,
                "missing --target in non-interactive mode; pass --target <game exe or folder>",
            )
        log("interactive: --target not provided, prompting for game path")
        target = _prompt_target_path()
        interaction_meta["interaction_used"] = True
        interaction_meta["target_prompted"] = True

    exporter = args.exporter
    if exporter == "auto":
        detection = detect_game(target)
        needs_choice = detection.game_type == "unknown" or not str(detection.profile_id or "").strip()
        if needs_choice:
            if not interactive_enabled:
                raise SetupError(
                    EXIT_DETECT_FAILED,
                    "unknown game profile in non-interactive mode; pass --exporter skeleton or --exporter live2d",
                )
            log("interactive: game profile unknown, prompting for exporter choice")
            exporter = _prompt_exporter_choice()
            interaction_meta["interaction_used"] = True
            interaction_meta["exporter_prompted"] = True
            interaction_meta["exporter_selected"] = exporter
            log(f"interactive: selected exporter '{exporter}'")

    print_json(
        run_install(
            target=target,
            config=config,
            exporter=exporter,
            prefer_local_configs=args.prefer_local_configs,
            allow_remote_configs=not args.no_remote_configs,
            refresh_remote_cache=args.refresh_config_cache,
            release_tag=args.release_tag,
            force_reinstall=args.force_reinstall,
            rue=args.rue,
            cue=args.cue,
            config_manager=args.config_manager,
            uud=args.uud,
            skip_exporter=args.skip_exporter,
            offline=args.offline,
            interaction_meta=interaction_meta,
        )
    )


def _install_bepinex(detection: DetectionResult, config: SetupConfig, offline: bool) -> DetectionResult:
    if detection.backend == "mono":
        _install_bepinex_mono(detection, config, offline)
    elif detection.backend == "il2cpp":
        _install_bepinex_il2cpp(detection, config, offline)
    else:
        raise SetupError(EXIT_DETECT_FAILED, f"unsupported backend: {detection.backend}")

    refreshed = detect_game(str(detection.exe_path))
    if not refreshed.has_bepinex:
        raise SetupError(EXIT_INSTALL_FAILED, "BepInEx install finished but detection still reports missing")
    return refreshed


def _install_bepinex_mono(detection: DetectionResult, config: SetupConfig, offline: bool) -> None:
    release = github_latest_release(config.bepinex_release_repo, config.timeout_sec)
    asset = select_bepinex_mono_asset(release, detection.arch, config.asset_regex_overrides)
    _download_and_extract_asset(
        detection.game_root,
        asset_name=str(asset["name"]),
        asset_url=str(asset["browser_download_url"]),
        cache_dir=config.cache_dir,
        timeout_sec=config.timeout_sec,
        offline=offline,
        category="bepinex-mono",
    )


def _install_bepinex_il2cpp(detection: DetectionResult, config: SetupConfig, offline: bool) -> None:
    asset = select_bepinex_be_il2cpp_asset(
        config.bepinex_be_index_url,
        detection.arch,
        config.asset_regex_overrides,
        config.timeout_sec,
    )
    _download_and_extract_asset(
        detection.game_root,
        asset_name=asset["name"],
        asset_url=asset["browser_download_url"],
        cache_dir=config.cache_dir,
        timeout_sec=config.timeout_sec,
        offline=offline,
        category="bepinex-il2cpp",
    )


def _install_runtime_unity_editor(detection: DetectionResult, config: SetupConfig, offline: bool) -> Path:
    release = github_latest_release(config.rue_release_repo, config.timeout_sec)
    asset = select_rue_asset(
        release=release,
        bepinex_major=detection.bepinex_major,
        variant=detection.bepinex_variant,
        overrides=config.asset_regex_overrides,
    )
    return _download_and_extract_asset(
        detection.game_root,
        asset_name=str(asset["name"]),
        asset_url=str(asset["browser_download_url"]),
        cache_dir=config.cache_dir,
        timeout_sec=config.timeout_sec,
        offline=offline,
        category="runtime-unity-editor",
    )


def _install_cinematic_unity_explorer(
    detection: DetectionResult, config: SetupConfig, offline: bool
) -> tuple[Path, Path, str]:
    release = github_latest_release(config.cue_release_repo, config.timeout_sec)
    asset = select_cue_asset(
        release=release,
        bepinex_major=detection.bepinex_major,
        variant=detection.bepinex_variant,
        overrides=config.asset_regex_overrides,
    )
    zip_path = _download_and_extract_asset(
        detection.game_root,
        asset_name=str(asset["name"]),
        asset_url=str(asset["browser_download_url"]),
        cache_dir=config.cache_dir,
        timeout_sec=config.timeout_sec,
        offline=offline,
        category="cinematic-unity-explorer",
    )
    cue_config_path, cue_config_status = _install_cue_config(detection.game_root)
    return zip_path, cue_config_path, cue_config_status


def _install_configuration_manager(detection: DetectionResult, config: SetupConfig, offline: bool) -> Path:
    release = github_latest_release(config.config_manager_release_repo, config.timeout_sec)
    asset = select_config_manager_asset(
        release=release,
        bepinex_major=detection.bepinex_major,
        variant=detection.bepinex_variant,
        overrides=config.asset_regex_overrides,
    )
    return _download_and_extract_asset(
        detection.game_root,
        asset_name=str(asset["name"]),
        asset_url=str(asset["browser_download_url"]),
        cache_dir=config.cache_dir,
        timeout_sec=config.timeout_sec,
        offline=offline,
        category="configuration-manager",
    )


def _install_universal_unity_demosaics(detection: DetectionResult, config: SetupConfig, offline: bool) -> Path:
    release = github_latest_release(config.universal_unity_demosaics_release_repo, config.timeout_sec)
    asset = select_universal_unity_demosaics_asset(
        release=release,
        bepinex_major=detection.bepinex_major,
        variant=detection.bepinex_variant,
        overrides=config.asset_regex_overrides,
    )
    return _download_and_extract_asset(
        detection.game_root,
        asset_name=str(asset["name"]),
        asset_url=str(asset["browser_download_url"]),
        cache_dir=config.cache_dir,
        timeout_sec=config.timeout_sec,
        offline=offline,
        category="universal-unity-demosaics",
    )


def _download_and_extract_asset(
    game_root: Path,
    asset_name: str,
    asset_url: str,
    cache_dir: Path,
    timeout_sec: int,
    offline: bool,
    category: str,
) -> Path:
    cache_path = build_cached_asset_path(cache_dir, category, asset_name)
    log(f"asset: {asset_name}")
    zip_path = download_with_retries(asset_url, cache_path, timeout_sec=timeout_sec, offline=offline)
    extract_zip(zip_path, game_root)
    _post_extract_fixups(game_root, category, zip_path)
    return zip_path


def _install_cue_config(game_root: Path) -> tuple[Path, str]:
    config_dir = game_root / "BepInEx" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    output_dir = game_root / "BepInEx" / "plugins" / "CinematicUnityExplorer" / "Output"
    output_dir.mkdir(parents=True, exist_ok=True)

    cfg_path = config_dir / "com.originalnicodr.cinematicunityexplorer.cfg"
    default_output_path = str(output_dir)
    dnspy_path = _find_dnspy_path()

    marker = "# Managed by tools/game_setup.py"
    default_body = "\n".join(
        [
            marker,
            "## Plugin GUID: com.originalnicodr.cinematicunityexplorer",
            "",
            "[UnityExplorer]",
            "CinematicUnityExplorer Toggle = F7",
            "Hide On Startup = true",
            "Startup Delay Time = 1",
            "Target Display = 0",
            "Force Unlock Mouse = true",
            "Force Unlock Toggle Key = None",
            "Disable EventSystem override = false",
            f"Default Output Path = {default_output_path}",
            f"dnSpy Path = {dnspy_path}",
            "Main Navbar Anchor = Top",
            "Log Unity Debug = false",
            "Log To Disk = true",
            "",
        ]
    )

    if not cfg_path.exists():
        cfg_path.write_text(default_body, encoding="utf-8")
        return cfg_path, "installed"

    existing = cfg_path.read_text(encoding="utf-8", errors="ignore")
    if marker in existing:
        cfg_path.write_text(default_body, encoding="utf-8")
        return cfg_path, "updated_managed"

    updated = existing
    updated = _upsert_cfg_kv(updated, "Hide On Startup", "true")
    updated = _upsert_cfg_kv(updated, "Default Output Path", default_output_path)
    updated = _upsert_cfg_kv(updated, "dnSpy Path", dnspy_path)
    cfg_path.write_text(updated, encoding="utf-8")
    return cfg_path, "updated_existing"


def _upsert_cfg_kv(text: str, key: str, value: str) -> str:
    line = f"{key} = {value}"
    pattern = re.compile(rf"(?m)^{re.escape(key)}\s*=.*$")
    if pattern.search(text):
        return pattern.sub(lambda _match: line, text, count=1)

    if "[UnityExplorer]" in text:
        section_pattern = re.compile(r"(?ms)^\[UnityExplorer\]\s*\n")
        match = section_pattern.search(text)
        if match is not None:
            insert_at = match.end()
            return text[:insert_at] + line + "\n" + text[insert_at:]

    if text and not text.endswith("\n"):
        text += "\n"
    return text + "[UnityExplorer]\n" + line + "\n"


def _find_dnspy_path() -> str:
    candidates = [
        Path("C:/Program Files/dnspy/dnSpy.exe"),
        Path("C:/Program Files (x86)/dnspy/dnSpy.exe"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.as_posix()
    return ""


def _post_extract_fixups(game_root: Path, category: str, zip_path: Path) -> None:
    if category == "universal-unity-demosaics":
        _normalize_uud_install_layout(game_root, zip_path)
        return

    # Some third-party plugin zips put `plugins/*` at root instead of `BepInEx/plugins/*`.
    # Normalize them so installers always land under BepInEx.
    if category not in (
        "runtime-unity-editor",
        "cinematic-unity-explorer",
        "configuration-manager",
    ):
        return

    root_plugins = game_root / "plugins"
    if not root_plugins.is_dir():
        return

    bepinex_plugins = game_root / "BepInEx" / "plugins"
    bepinex_plugins.mkdir(parents=True, exist_ok=True)
    _merge_tree_into(root_plugins, bepinex_plugins)
    try:
        root_plugins.rmdir()
    except OSError:
        pass


def _normalize_uud_install_layout(game_root: Path, zip_path: Path) -> None:
    target_root = game_root / "BepInEx" / "plugins" / "UniversalUnityDemosaics"
    target_root.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            archive_files = [
                entry.filename.replace("\\", "/").strip("/")
                for entry in zf.infolist()
                if entry.filename
                and not entry.is_dir()
            ]
    except Exception as e:
        log(f"warning: cannot inspect UUD zip entries: {e}")
        return

    moved = 0
    for entry in archive_files:
        parts = [p for p in entry.split("/") if p]
        if not parts:
            continue

        rel_parts = parts
        if len(parts) >= 3 and parts[0].lower() == "bepinex" and parts[1].lower() == "plugins":
            rel_parts = parts[2:]
        elif len(parts) >= 2 and parts[0].lower() == "plugins":
            rel_parts = parts[1:]

        if not rel_parts:
            continue

        rel_path = Path(*rel_parts)
        src_candidates = [
            game_root / Path(*parts),
            game_root / rel_path,
            game_root / "plugins" / rel_path,
            game_root / "BepInEx" / "plugins" / rel_path,
        ]

        src = next((candidate for candidate in src_candidates if candidate.is_file()), None)
        if src is None:
            continue

        dst = target_root / rel_path
        try:
            if src.resolve() == dst.resolve():
                continue
        except Exception:
            pass

        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            if dst.is_dir():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        shutil.move(str(src), str(dst))
        moved += 1

    if moved > 0:
        log(f"normalized UUD into BepInEx/plugins/UniversalUnityDemosaics: moved={moved}")

    root_plugins = game_root / "plugins"
    if root_plugins.is_dir():
        dirs = [p for p in root_plugins.rglob("*") if p.is_dir()]
        dirs.sort(key=lambda p: len(p.parts), reverse=True)
        for d in dirs:
            try:
                d.rmdir()
            except OSError:
                pass
        try:
            root_plugins.rmdir()
        except OSError:
            pass


def _merge_tree_into(source_dir: Path, destination_dir: Path) -> None:
    for src in source_dir.rglob("*"):
        rel = src.relative_to(source_dir)
        dst = destination_dir / rel
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
            continue

        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            if dst.is_dir():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        shutil.move(str(src), str(dst))

    # Remove empty source directories left after moves.
    dirs = [p for p in source_dir.rglob("*") if p.is_dir()]
    dirs.sort(key=lambda p: len(p.parts), reverse=True)
    for d in dirs:
        try:
            d.rmdir()
        except OSError:
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect and setup Unity game environment for exporter")
    sub = parser.add_subparsers(dest="command", required=True)

    p_detect = sub.add_parser("detect", help="Detect Unity game metadata")
    p_detect.add_argument("--target", required=True, help="Path to game exe or game folder")
    p_detect.set_defaults(func=cmd_detect)

    p_diag = sub.add_parser("diagnose", help="Show what install would do without mutating files")
    p_diag.add_argument("--target", required=True, help="Path to game exe or game folder")
    p_diag.add_argument(
        "--exporter",
        default="auto",
        choices=["auto", "skeleton", "live2d"],
        help="Exporter selection strategy. auto = infer from profile template.",
    )
    p_diag.add_argument(
        "--prefer-local-configs",
        action="store_true",
        default=None,
        help="Prefer bundled/local configs before cached or remote configs.",
    )
    p_diag.add_argument(
        "--no-remote-configs",
        action="store_true",
        help="Disable remote config manifest/profile fetch and use local configs only.",
    )
    p_diag.add_argument(
        "--refresh-config-cache",
        action="store_true",
        help="Force refresh of cached remote config manifest/profile files.",
    )
    p_diag.add_argument(
        "--release-tag",
        default="",
        help="Pin self-hosted exporter downloads to a specific GitHub release tag.",
    )
    p_diag.add_argument("--force-reinstall", action="store_true", help="Assume force reinstall behavior in plan")
    p_diag.add_argument("--rue", action="store_true", help="Also install RuntimeUnityEditor")
    p_diag.add_argument("--cue", action="store_true", help="Also install CinematicUnityExplorer")
    p_diag.add_argument("--skip-exporter", action="store_true")
    p_diag.add_argument("--config-manager", action="store_true", help="Also install ConfigurationManager")
    p_diag.add_argument("--uud", action="store_true", help="Also install UniversalUnityDemosaics")
    p_diag.add_argument("--offline", action="store_true")
    p_diag.set_defaults(func=cmd_diagnose)

    p_install = sub.add_parser(
        "install",
        help=(
            "Install BepInEx and exporter "
            "(use --rue/--cue/--config-manager/--uud for optional plugins)"
        ),
    )
    p_install.add_argument("--target", help="Path to game exe or game folder")
    p_install.add_argument(
        "--exporter",
        default="auto",
        choices=["auto", "skeleton", "live2d"],
        help="Exporter selection strategy. auto = infer from profile template.",
    )
    p_install.add_argument(
        "--prefer-local-configs",
        action="store_true",
        default=None,
        help="Prefer bundled/local configs before cached or remote configs.",
    )
    p_install.add_argument(
        "--no-remote-configs",
        action="store_true",
        help="Disable remote config manifest/profile fetch and use local configs only.",
    )
    p_install.add_argument(
        "--refresh-config-cache",
        action="store_true",
        help="Force refresh of cached remote config manifest/profile files.",
    )
    p_install.add_argument(
        "--release-tag",
        default="",
        help="Pin self-hosted exporter downloads to a specific GitHub release tag.",
    )
    interactive_group = p_install.add_mutually_exclusive_group()
    interactive_group.add_argument(
        "--interactive",
        action="store_true",
        help="Force interactive prompts for missing install inputs.",
    )
    interactive_group.add_argument(
        "--non-interactive",
        action="store_true",
        help="Disable prompts and fail fast when required inputs are missing.",
    )
    p_install.add_argument("--force-reinstall", action="store_true", help="Replace existing mismatched BepInEx")
    p_install.add_argument("--rue", action="store_true", help="Also install RuntimeUnityEditor")
    p_install.add_argument("--cue", action="store_true", help="Also install CinematicUnityExplorer")
    p_install.add_argument("--config-manager", action="store_true", help="Also install ConfigurationManager")
    p_install.add_argument("--uud", action="store_true", help="Also install UniversalUnityDemosaics")
    p_install.add_argument("--skip-exporter", action="store_true", help="Do not install exporter plugin")
    p_install.add_argument("--offline", action="store_true", help="Use only cached download artifacts")
    p_install.set_defaults(func=cmd_install)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config = load_setup_config()
    try:
        args.func(args, config)
        return 0
    except SetupError as e:
        print_json({"status": "error", "code": e.code, "message": e.message})
        return e.code
    except Exception as e:  # pragma: no cover - CLI guard
        print_json({"status": "error", "code": EXIT_INSTALL_FAILED, "message": str(e)})
        return EXIT_INSTALL_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
