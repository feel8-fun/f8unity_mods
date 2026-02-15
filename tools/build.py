from __future__ import annotations

import argparse
import shutil
import zipfile

from common import (
    EXIT_INSTALL_FAILED,
    EXPORTER_README,
    PROJECT_CSPROJ,
    ROOT,
    SetupError,
    copy_exporter_plugin,
    detect_game,
    ensure_exporter_artifacts,
    find_exporter_dll,
    print_json,
    run_command,
)


def cmd_build(_: argparse.Namespace) -> None:
    run_command(["dotnet", "build", str(PROJECT_CSPROJ), "-c", "Release"], cwd=ROOT)
    dll = find_exporter_dll()
    print_json(
        {
            "action": "build",
            "status": "ok",
            "dll": str(dll) if dll else None,
            "exists": dll is not None and dll.exists(),
        }
    )


def cmd_package(args: argparse.Namespace) -> None:
    if args.build_first:
        run_command(["dotnet", "build", str(PROJECT_CSPROJ), "-c", "Release"], cwd=ROOT)
    artifact_dir = ensure_exporter_artifacts("mono")

    dist_dir = ROOT / "dist" / "F8HSceneAnimatorStreamer"
    staging = dist_dir / "_staging"
    zip_path = dist_dir / "F8HSceneAnimatorStreamer.zip"

    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    copy_exporter_plugin(staging, backend="mono", source_artifact_dir=artifact_dir)
    if EXPORTER_README.exists():
        shutil.copy2(EXPORTER_README, staging / "README.F8HSceneAnimatorStreamer.md")

    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in staging.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(staging))

    print_json(
        {
            "action": "package",
            "status": "ok",
            "zip": str(zip_path),
            "bytes": zip_path.stat().st_size,
        }
    )


def cmd_install_local(args: argparse.Namespace) -> None:
    detection = detect_game(args.game)
    if detection.backend == "unknown":
        raise SetupError(EXIT_INSTALL_FAILED, "target is not a recognized Unity game directory")
    artifact_dir = ensure_exporter_artifacts(detection.backend)
    installed = copy_exporter_plugin(
        detection.game_root,
        backend=detection.backend,
        source_artifact_dir=artifact_dir,
    )
    print_json(
        {
            "action": "install-local",
            "status": "ok",
            "game_root": str(detection.game_root),
            "backend": detection.backend,
            "installed_plugin_dir": str(installed),
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and package F8HSceneAnimatorStreamer")
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="Build exporter in Release mode")
    p_build.set_defaults(func=cmd_build)

    p_package = sub.add_parser("package", help="Create distributable zip")
    p_package.add_argument("--no-build-first", dest="build_first", action="store_false")
    p_package.set_defaults(build_first=True)
    p_package.set_defaults(func=cmd_package)

    p_install = sub.add_parser("install-local", help="Install plugin into a local game directory")
    p_install.add_argument("--game", required=True, help="Path to game folder or game exe")
    p_install.set_defaults(func=cmd_install_local)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
        return 0
    except SetupError as e:
        print_json({"status": "error", "code": e.code, "message": e.message})
        return e.code
    except Exception as e:  # pragma: no cover - defensive catch for CLI
        print_json({"status": "error", "code": EXIT_INSTALL_FAILED, "message": str(e)})
        return EXIT_INSTALL_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
