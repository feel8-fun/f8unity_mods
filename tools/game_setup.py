from __future__ import annotations

import argparse
import shutil
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
    ensure_exporter_artifacts,
    extract_zip,
    github_latest_release,
    install_single_profile,
    install_exporter_config,
    load_setup_config,
    log,
    print_json,
    remove_existing_install,
    select_cue_asset,
    select_config_manager_asset,
    select_bepinex_be_il2cpp_asset,
    select_bepinex_mono_asset,
    select_rue_asset,
    select_universal_unity_demosaics_asset,
    download_with_retries,
)


def _build_install_plan(
    detection: DetectionResult,
    force_reinstall: bool,
    skip_exporter: bool,
    skip_rue: bool,
    skip_cue: bool,
    skip_config_manager: bool,
    install_uud: bool,
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
    if not skip_rue:
        actions.append("install_runtime_unity_editor")
    if not skip_cue:
        actions.append("install_cinematic_unity_explorer")
    if not skip_config_manager:
        actions.append("install_configuration_manager")
    if install_uud:
        actions.append("install_universal_unity_demosaics")

    return {"actions": actions, "blocking_errors": blocking}


def cmd_detect(args: argparse.Namespace, config: SetupConfig) -> None:
    _ = config
    detection = detect_game(args.target)
    print_json(detection.to_public_dict())


def cmd_diagnose(args: argparse.Namespace, config: SetupConfig) -> None:
    _ = config
    detection = detect_game(args.target)
    plan = _build_install_plan(
        detection,
        args.force_reinstall,
        args.skip_exporter,
        args.skip_rue,
        args.skip_cue,
        args.skip_config_manager,
        args.uud,
    )
    print_json(
        {
            "detection": detection.to_public_dict(),
            "plan": plan,
            "offline": args.offline,
        }
    )


def cmd_install(args: argparse.Namespace, config: SetupConfig) -> None:
    detection = detect_game(args.target)
    if detection.backend == "unknown":
        raise SetupError(EXIT_DETECT_FAILED, "cannot install: backend is unknown")
    if detection.arch == "unknown":
        raise SetupError(EXIT_DETECT_FAILED, "cannot install: architecture is unknown")

    summary: dict[str, Any] = {
        "game_root": str(detection.game_root),
        "process_name": detection.process_name,
        "game_type": detection.game_type,
        "profile_id": detection.profile_id,
        "backend": detection.backend,
        "arch": detection.arch,
        "actions": [],
    }

    if detection.has_bepinex and not bepinex_variant_matches_backend(detection.backend, detection.bepinex_variant):
        if not args.force_reinstall:
            raise SetupError(
                EXIT_BEPINEX_MISMATCH,
                f"existing BepInEx variant '{detection.bepinex_variant}' mismatches backend '{detection.backend}', "
                "rerun with --force-reinstall to replace it",
            )
        backup_dir = backup_existing_install(detection.game_root)
        remove_existing_install(detection.game_root)
        summary["actions"].append({"backup_existing_bepinex": str(backup_dir)})
        detection = _install_bepinex(detection, config, offline=args.offline)
        summary["actions"].append({"install_bepinex": "reinstalled"})
    elif not detection.has_bepinex:
        detection = _install_bepinex(detection, config, offline=args.offline)
        summary["actions"].append({"install_bepinex": "installed"})
    else:
        summary["actions"].append({"install_bepinex": "skipped_existing"})

    if not args.skip_exporter:
        artifact_dir = ensure_exporter_artifacts(detection.backend)
        installed = copy_exporter_plugin(
            detection.game_root,
            backend=detection.backend,
            source_artifact_dir=artifact_dir,
        )
        config_path, config_status = install_exporter_config(detection.game_root, detection)
        profile_path, profile_status, profile_source = install_single_profile(detection.game_root, detection)
        summary["actions"].append(
            {
                "install_exporter": {
                    "plugin_dir": str(installed),
                    "backend": detection.backend,
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

    if not args.skip_rue:
        rue_path = _install_runtime_unity_editor(detection, config, offline=args.offline)
        summary["actions"].append({"install_runtime_unity_editor": str(rue_path)})
    else:
        summary["actions"].append({"install_runtime_unity_editor": "skipped"})

    if not args.skip_cue:
        cue_path = _install_cinematic_unity_explorer(detection, config, offline=args.offline)
        summary["actions"].append({"install_cinematic_unity_explorer": str(cue_path)})
    else:
        summary["actions"].append({"install_cinematic_unity_explorer": "skipped"})

    if not args.skip_config_manager:
        config_manager_path = _install_configuration_manager(detection, config, offline=args.offline)
        summary["actions"].append({"install_configuration_manager": str(config_manager_path)})
    else:
        summary["actions"].append({"install_configuration_manager": "skipped"})

    if args.uud:
        uud_path = _install_universal_unity_demosaics(detection, config, offline=args.offline)
        summary["actions"].append({"install_universal_unity_demosaics": str(uud_path)})
    else:
        summary["actions"].append({"install_universal_unity_demosaics": "skipped"})

    print_json(summary)


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


def _install_cinematic_unity_explorer(detection: DetectionResult, config: SetupConfig, offline: bool) -> Path:
    release = github_latest_release(config.cue_release_repo, config.timeout_sec)
    asset = select_cue_asset(
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
        category="cinematic-unity-explorer",
    )


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
    _post_extract_fixups(game_root, category)
    return zip_path


def _post_extract_fixups(game_root: Path, category: str) -> None:
    # Some third-party plugin zips put `plugins/*` at root instead of `BepInEx/plugins/*`.
    # Normalize them so installers always land under BepInEx.
    if category not in (
        "runtime-unity-editor",
        "cinematic-unity-explorer",
        "configuration-manager",
        "universal-unity-demosaics",
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
    p_diag.add_argument("--force-reinstall", action="store_true", help="Assume force reinstall behavior in plan")
    p_diag.add_argument("--skip-rue", action="store_true")
    p_diag.add_argument("--skip-cue", action="store_true")
    p_diag.add_argument("--skip-exporter", action="store_true")
    p_diag.add_argument("--skip-config-manager", action="store_true")
    p_diag.add_argument("--uud", action="store_true", help="Also install UniversalUnityDemosaics")
    p_diag.add_argument("--offline", action="store_true")
    p_diag.set_defaults(func=cmd_diagnose)

    p_install = sub.add_parser(
        "install",
        help=(
            "Install BepInEx, exporter, RuntimeUnityEditor, "
            "CinematicUnityExplorer and ConfigurationManager "
            "(use --uud to also install UniversalUnityDemosaics)"
        ),
    )
    p_install.add_argument("--target", required=True, help="Path to game exe or game folder")
    p_install.add_argument("--force-reinstall", action="store_true", help="Replace existing mismatched BepInEx")
    p_install.add_argument("--skip-rue", action="store_true", help="Do not install RuntimeUnityEditor")
    p_install.add_argument("--skip-cue", action="store_true", help="Do not install CinematicUnityExplorer")
    p_install.add_argument("--skip-config-manager", action="store_true", help="Do not install ConfigurationManager")
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
