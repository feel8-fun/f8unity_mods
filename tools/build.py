from __future__ import annotations

import argparse
import shutil
import traceback
import zipfile
from pathlib import Path

from f8unitymods_setup.common import (
    DEFAULT_EXPORTER_SPEC,
    EXIT_INSTALL_FAILED,
    LIVE2D_EXPORTER_SPEC,
    ROOT,
    ExporterSpec,
    SetupError,
    copy_exporter_plugin,
    detect_game,
    ensure_exporter_artifacts,
    find_exporter_dll,
    print_json,
    run_command,
)


def _normalize_exporter_key(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if raw in ("default", "skeleton", "f8skeletonstreamer", "skeletonstreamer"):
        return "skeleton"
    if raw in ("live2d", "f8live2dstreamer", "live2dstreamer"):
        return "live2d"
    if raw in ("both", "all"):
        return "both"
    return "skeleton"


def _resolve_specs(exporter_key: str) -> list[ExporterSpec]:
    key = _normalize_exporter_key(exporter_key)
    if key == "both":
        return [DEFAULT_EXPORTER_SPEC, LIVE2D_EXPORTER_SPEC]
    if key == "live2d":
        return [LIVE2D_EXPORTER_SPEC]
    return [DEFAULT_EXPORTER_SPEC]


def _resolve_backends(backend_key: str) -> list[str]:
    raw = str(backend_key or "").strip().lower()
    if raw == "both":
        return ["mono", "il2cpp"]
    if raw == "il2cpp":
        return ["il2cpp"]
    return ["mono"]


def cmd_build(args: argparse.Namespace) -> None:
    rows: list[dict[str, object]] = []
    for spec in _resolve_specs(args.exporter):
        for backend in _resolve_backends(args.backend):
            project = spec.project_il2cpp_csproj if backend == "il2cpp" else spec.project_csproj
            run_command(["dotnet", "build", str(project), "-c", "Release"], cwd=ROOT)
            artifact_dir = ensure_exporter_artifacts(backend, spec=spec)
            dll = find_exporter_dll(spec=spec) if backend == "mono" else artifact_dir / spec.il2cpp_dll_name
            rows.append(
                {
                    "exporter": spec.key,
                    "project": spec.project_name,
                    "backend": backend,
                    "artifact_dir": str(artifact_dir),
                    "dll": str(dll) if dll else None,
                    "exists": dll is not None and dll.exists(),
                }
            )

    print_json({"action": "build", "status": "ok", "results": rows})


def cmd_package(args: argparse.Namespace) -> None:
    rows: list[dict[str, object]] = []
    for spec in _resolve_specs(args.exporter):
        if args.build_first:
            run_command(["dotnet", "build", str(spec.project_csproj), "-c", "Release"], cwd=ROOT)
        artifact_dir = ensure_exporter_artifacts("mono", spec=spec)

        dist_dir = ROOT / "dist" / spec.project_name
        staging = dist_dir / "_staging"
        zip_path = dist_dir / f"{spec.project_name}.zip"

        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True, exist_ok=True)

        copy_exporter_plugin(staging, backend="mono", source_artifact_dir=artifact_dir, spec=spec)
        if spec.readme_path.exists():
            shutil.copy2(spec.readme_path, staging / f"README.{spec.project_name}.md")

        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in staging.rglob("*"):
                if path.is_file():
                    zf.write(path, path.relative_to(staging))

        rows.append(
            {
                "exporter": spec.key,
                "project": spec.project_name,
                "zip": str(zip_path),
                "bytes": zip_path.stat().st_size,
            }
        )

    print_json({"action": "package", "status": "ok", "results": rows})


def cmd_package_release(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir).expanduser()
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    for spec in _resolve_specs(args.exporter):
        for backend in _resolve_backends(args.backend):
            if args.build_first:
                project = spec.project_il2cpp_csproj if backend == "il2cpp" else spec.project_csproj
                run_command(["dotnet", "build", str(project), "-c", "Release"], cwd=ROOT)

            artifact_dir = ensure_exporter_artifacts(backend, spec=spec)
            staging = output_dir / f"_{spec.project_name}_{backend}"
            zip_path = output_dir / f"{spec.project_name}-{backend}.zip"

            if staging.exists():
                shutil.rmtree(staging)
            staging.mkdir(parents=True, exist_ok=True)

            copy_exporter_plugin(staging, backend=backend, source_artifact_dir=artifact_dir, spec=spec)
            if spec.readme_path.exists():
                shutil.copy2(spec.readme_path, staging / f"README.{spec.project_name}.md")

            if zip_path.exists():
                zip_path.unlink()
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for path in staging.rglob("*"):
                    if path.is_file():
                        zf.write(path, path.relative_to(staging))

            rows.append(
                {
                    "exporter": spec.key,
                    "project": spec.project_name,
                    "backend": backend,
                    "zip": str(zip_path),
                    "bytes": zip_path.stat().st_size,
                }
            )

    print_json({"action": "package-release", "status": "ok", "results": rows})


def cmd_install_local(args: argparse.Namespace) -> None:
    detection = detect_game(args.game)
    if detection.backend == "unknown":
        raise SetupError(EXIT_INSTALL_FAILED, "target is not a recognized Unity game directory")

    rows: list[dict[str, object]] = []
    for spec in _resolve_specs(args.exporter):
        artifact_dir = ensure_exporter_artifacts(detection.backend, spec=spec)
        installed = copy_exporter_plugin(
            detection.game_root,
            backend=detection.backend,
            source_artifact_dir=artifact_dir,
            spec=spec,
        )
        rows.append(
            {
                "exporter": spec.key,
                "project": spec.project_name,
                "installed_plugin_dir": str(installed),
            }
        )

    print_json(
        {
            "action": "install-local",
            "status": "ok",
            "game_root": str(detection.game_root),
            "backend": detection.backend,
            "results": rows,
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and package F8 exporters")
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="Build exporter in Release mode")
    p_build.add_argument(
        "--exporter",
        default="skeleton",
        choices=("skeleton", "default", "live2d", "both"),
        help="Select build target exporter.",
    )
    p_build.add_argument(
        "--backend",
        default="mono",
        choices=("mono", "il2cpp", "both"),
        help="Select build target backend.",
    )
    p_build.set_defaults(func=cmd_build)

    p_package = sub.add_parser("package", help="Create distributable zip")
    p_package.add_argument("--no-build-first", dest="build_first", action="store_false")
    p_package.add_argument(
        "--exporter",
        default="skeleton",
        choices=("skeleton", "default", "live2d", "both"),
        help="Select package target exporter.",
    )
    p_package.set_defaults(build_first=True)
    p_package.set_defaults(func=cmd_package)

    p_release = sub.add_parser("package-release", help="Create GitHub release plugin zips")
    p_release.add_argument("--no-build-first", dest="build_first", action="store_false")
    p_release.add_argument(
        "--exporter",
        default="both",
        choices=("skeleton", "default", "live2d", "both"),
        help="Select package target exporter.",
    )
    p_release.add_argument(
        "--backend",
        default="both",
        choices=("mono", "il2cpp", "both"),
        help="Select package target backend.",
    )
    p_release.add_argument(
        "--output-dir",
        default="dist/release",
        help="Output directory for release zips.",
    )
    p_release.set_defaults(build_first=True)
    p_release.set_defaults(func=cmd_package_release)

    p_install = sub.add_parser("install-local", help="Install plugin into a local game directory")
    p_install.add_argument("--game", required=True, help="Path to game folder or game exe")
    p_install.add_argument(
        "--exporter",
        default="skeleton",
        choices=("skeleton", "default", "live2d", "both"),
        help="Select install target exporter.",
    )
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
    except Exception as e:  # pragma: no cover - CLI safety boundary
        print_json(
            {
                "status": "error",
                "code": EXIT_INSTALL_FAILED,
                "exceptionType": type(e).__name__,
                "message": str(e),
                "traceback": traceback.format_exc(),
            }
        )
        return EXIT_INSTALL_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
