from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from f8unitymods_setup.common import ROOT, _normalize_process_name, infer_exporter_key_from_profile_payload, print_json


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_profile(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"profile is not an object: {path}")
    return payload


def _profile_aliases(path: Path, payload: dict[str, Any]) -> list[str]:
    aliases: list[str] = []
    raw_names = payload.get("processNames", [])
    if isinstance(raw_names, list):
        aliases.extend(str(item).strip() for item in raw_names if str(item).strip())
    aliases.append(path.stem)
    aliases.append(str(payload.get("id", "")).strip())
    return sorted({_normalize_process_name(item) for item in aliases if _normalize_process_name(item)})


def build_config_manifest(configs_dir: Path, *, commit: str, config_base_url: str) -> dict[str, Any]:
    profiles: list[dict[str, Any]] = []
    for path in sorted(configs_dir.glob("*.json")):
        payload = _load_profile(path)
        profiles.append(
            {
                "id": str(payload.get("id", "")).strip(),
                "file": path.name,
                "sha256": _sha256_file(path),
                "streamerType": str(payload.get("streamerType", infer_exporter_key_from_profile_payload(payload))).strip(),
                "processNames": payload.get("processNames", []),
                "version": str(payload.get("version", "")).strip(),
                "fullName": str(payload.get("fullName", "")).strip(),
                "gameType": _normalize_process_name(path.stem),
                "aliases": _profile_aliases(path, payload),
            }
        )

    return {
        "manifestVersion": 1,
        "publishedAt": datetime.now(timezone.utc).isoformat(),
        "commitSha": commit,
        "baseUrl": config_base_url,
        "profiles": profiles,
    }


def build_release_manifest(
    release_dir: Path,
    *,
    commit: str,
    release_repo: str,
    release_tag: str,
    config_manifest: dict[str, Any],
) -> dict[str, Any]:
    assets: list[dict[str, Any]] = []
    base_url = f"https://github.com/{release_repo}/releases/download/{release_tag}".rstrip("/")

    for path in sorted(release_dir.glob("*")):
        if not path.is_file():
            continue
        assets.append(
            {
                "name": path.name,
                "sha256": _sha256_file(path),
                "size": path.stat().st_size,
                "downloadUrl": f"{base_url}/{path.name}",
            }
        )

    plugins: list[dict[str, Any]] = []
    for path in sorted(release_dir.glob("F8*-*.zip")):
        if not path.is_file():
            continue
        stem = path.stem
        if "-" not in stem:
            continue
        project_name, backend = stem.rsplit("-", 1)
        exporter_key = "live2d" if "Live2D" in project_name else "default"
        plugins.append(
            {
                "exporterKey": exporter_key,
                "projectName": project_name,
                "backend": backend,
                "assetName": path.name,
                "version": release_tag,
                "sha256": _sha256_file(path),
                "downloadUrl": f"{base_url}/{path.name}",
            }
        )

    return {
        "manifestVersion": 1,
        "publishedAt": datetime.now(timezone.utc).isoformat(),
        "commitSha": commit,
        "releaseRepo": release_repo,
        "releaseTag": release_tag,
        "assets": assets,
        "plugins": plugins,
        "configs": {
            "manifestAssetName": "configs-manifest.json",
            "manifestUrl": f"{base_url}/configs-manifest.json",
            "baseUrl": str(config_manifest.get("baseUrl", "") or ""),
            "count": len(config_manifest.get("profiles", [])),
        },
    }


def validate_configs(configs_dir: Path) -> dict[str, Any]:
    duplicate_ids: dict[str, list[str]] = {}
    duplicate_aliases: dict[str, list[str]] = {}
    seen_ids: dict[str, list[str]] = {}
    seen_aliases: dict[str, list[str]] = {}
    rows: list[dict[str, Any]] = []

    for path in sorted(configs_dir.glob("*.json")):
        payload = _load_profile(path)
        profile_id = str(payload.get("id", "")).strip()
        aliases = _profile_aliases(path, payload)
        rows.append({"file": path.name, "id": profile_id, "aliases": aliases})
        seen_ids.setdefault(profile_id, []).append(path.name)
        for alias in aliases:
            seen_aliases.setdefault(alias, []).append(path.name)

    for profile_id, files in seen_ids.items():
        if profile_id and len(files) > 1:
            duplicate_ids[profile_id] = sorted(files)
    for alias, files in seen_aliases.items():
        if alias and len(files) > 1:
            duplicate_aliases[alias] = sorted(files)

    errors: list[str] = []
    if duplicate_ids:
        errors.append("duplicate profile ids detected")
    if duplicate_aliases:
        errors.append("duplicate normalized process aliases detected")

    return {
        "status": "ok" if not errors else "error",
        "configs_dir": str(configs_dir),
        "count": len(rows),
        "duplicate_ids": duplicate_ids,
        "duplicate_aliases": duplicate_aliases,
        "errors": errors,
        "profiles": rows,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_configs_pack(configs_dir: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(configs_dir.glob("*.json")):
            archive.write(path, path.name)


def cmd_validate(args: argparse.Namespace) -> None:
    payload = validate_configs(Path(args.configs_dir).expanduser().resolve())
    print_json(payload)
    if payload["status"] != "ok":
        raise SystemExit(1)


def cmd_generate(args: argparse.Namespace) -> None:
    configs_dir = Path(args.configs_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser()
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    validation = validate_configs(configs_dir)
    if validation["status"] != "ok":
        print_json(validation)
        raise SystemExit(1)

    config_manifest = build_config_manifest(
        configs_dir,
        commit=args.commit,
        config_base_url=args.config_base_url,
    )
    config_manifest_path = output_dir / "configs-manifest.json"
    _write_json(config_manifest_path, config_manifest)

    if args.include_config_pack:
        _write_configs_pack(configs_dir, output_dir / "configs-pack.zip")

    release_manifest = build_release_manifest(
        output_dir,
        commit=args.commit,
        release_repo=args.release_repo,
        release_tag=args.release_tag,
        config_manifest=config_manifest,
    )
    release_manifest_path = output_dir / "release-manifest.json"
    _write_json(release_manifest_path, release_manifest)

    print_json(
        {
            "status": "ok",
            "configs_manifest": str(config_manifest_path),
            "release_manifest": str(release_manifest_path),
            "output_dir": str(output_dir),
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate release/config manifests for F8UnityMods")
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="Validate configs directory")
    p_validate.add_argument("--configs-dir", default="configs")
    p_validate.set_defaults(func=cmd_validate)

    p_generate = sub.add_parser("generate", help="Generate config and release manifests")
    p_generate.add_argument("--configs-dir", default="configs")
    p_generate.add_argument("--output-dir", default="dist/release")
    p_generate.add_argument("--release-repo", required=True)
    p_generate.add_argument("--release-tag", required=True)
    p_generate.add_argument("--commit", required=True)
    p_generate.add_argument("--config-base-url", required=True)
    p_generate.add_argument("--include-config-pack", action="store_true")
    p_generate.set_defaults(func=cmd_generate)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
