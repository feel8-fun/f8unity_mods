"""Unity exporter setup: models responsibility."""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from .paths import (
    ROOT,
)


@dataclasses.dataclass(frozen=True)
class GameProfile:
    profile_id: str
    profile_template: str
    aliases: tuple[str, ...]
    exporter_key: str


@dataclasses.dataclass(frozen=True)
class ExporterSpec:
    key: str
    project_name: str
    plugin_dir_name: str
    managed_by_value: str
    config_filename: str
    mono_dll_name: str
    il2cpp_dll_name: str

    @property
    def project_csproj(self) -> Path:
        return ROOT / "src" / self.project_name / f"{self.project_name}.csproj"

    @property
    def project_il2cpp_csproj(self) -> Path:
        return ROOT / "src" / f"{self.project_name}.IL2CPP" / f"{self.project_name}.IL2CPP.csproj"

    @property
    def artifact_mono_dir(self) -> Path:
        return ROOT / "src" / "bin" / self.project_name / "BepInEx" / "plugins" / self.plugin_dir_name

    @property
    def artifact_il2cpp_dir(self) -> Path:
        return ROOT / "src" / "bin" / f"{self.project_name}.IL2CPP" / "BepInEx" / "plugins" / self.plugin_dir_name

    @property
    def readme_path(self) -> Path:
        return ROOT / "src" / self.project_name / "README.md"


DEFAULT_EXPORTER_SPEC = ExporterSpec(
    key="default",
    project_name="F8SkeletonStreamer",
    plugin_dir_name="F8SkeletonStreamer",
    managed_by_value="tools/game_setup.py",
    config_filename="com.feel8.f8-skeleton-streamer.cfg",
    mono_dll_name="F8SkeletonStreamer.dll",
    il2cpp_dll_name="F8SkeletonStreamer.IL2CPP.dll",
)


LIVE2D_EXPORTER_SPEC = ExporterSpec(
    key="live2d",
    project_name="F8Live2DStreamer",
    plugin_dir_name="F8Live2DStreamer",
    managed_by_value="tools/game_setup.py",
    config_filename="com.feel8.f8-live2d-streamer.cfg",
    mono_dll_name="F8Live2DStreamer.dll",
    il2cpp_dll_name="F8Live2DStreamer.IL2CPP.dll",
)


def resolve_exporter_spec(spec: ExporterSpec | None = None) -> ExporterSpec:
    return spec if spec is not None else DEFAULT_EXPORTER_SPEC


def resolve_exporter_spec_by_key(exporter_key: str | None) -> ExporterSpec:
    return LIVE2D_EXPORTER_SPEC if str(exporter_key or "").lower() == "live2d" else DEFAULT_EXPORTER_SPEC


def infer_exporter_key_from_profile_payload(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return "default"

    raw = str(payload.get("streamerType", "") or payload.get("exporterType", "")).strip().lower()
    if raw in ("live2d", "f8live2dstreamer", "live2dstreamer"):
        return "live2d"
    if raw in ("default", "skeleton", "f8skeletonstreamer", "skeletonstreamer"):
        return "default"

    live2d_markers = (
        "live2dRootsExpr",
        "autoDiscoverCubism",
        "drawableNameIncludeRegex",
        "drawableNameExcludeRegex",
        "minBoundsExtent",
    )
    for key in live2d_markers:
        if key in payload:
            return "live2d"

    return "default"


PROFILE_MANAGED_BY_KEY = "_managed_by"


PROFILE_MANAGED_BY_VALUE = DEFAULT_EXPORTER_SPEC.managed_by_value


PROFILE_FILENAME = "profile.json"


@dataclasses.dataclass
class SetupConfig:
    self_release_repo: str
    self_release_tag: str
    self_release_channel: str
    config_manifest_url: str
    config_base_url: str
    prefer_local_configs: bool
    allow_remote_configs: bool
    bepinex_release_repo: str
    bepinex_be_index_url: str
    rue_release_repo: str
    cue_release_repo: str
    config_manager_release_repo: str
    universal_unity_demosaics_release_repo: str
    cache_dir: Path
    remote_cache_dir: Path
    timeout_sec: int
    remote_timeout_sec: int
    asset_regex_overrides: dict[str, str]


@dataclasses.dataclass(frozen=True)
class BepInExInstallState:
    installed: bool
    partial: bool
    variant: str
    version: str
    major: int | None
    core_present: bool
    bootstrap_present: bool
    core_files: tuple[str, ...]
    bootstrap_files: tuple[str, ...]
    missing_components: tuple[str, ...]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "installed": self.installed,
            "partial": self.partial,
            "variant": self.variant,
            "version": self.version,
            "major": self.major,
            "corePresent": self.core_present,
            "bootstrapPresent": self.bootstrap_present,
            "coreFiles": list(self.core_files),
            "bootstrapFiles": list(self.bootstrap_files),
            "missingComponents": list(self.missing_components),
        }


@dataclasses.dataclass
class DetectionResult:
    target_input: str
    game_root: Path
    exe_path: Path
    data_dir: Path
    process_name: str
    game_type: str
    profile_id: str
    exporter_key: str
    unity_version: str
    backend: str
    arch: str
    has_bepinex: bool
    bepinex_variant: str
    bepinex_version: str
    bepinex_major: int | None
    bepinex_partial: bool
    bepinex_core_present: bool
    bepinex_bootstrap_present: bool
    bepinex_core_files: tuple[str, ...]
    bepinex_bootstrap_files: tuple[str, ...]
    bepinex_missing_components: tuple[str, ...]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "target_input": self.target_input,
            "game_root": str(self.game_root),
            "exe_path": str(self.exe_path),
            "process_name": self.process_name,
            "game_type": self.game_type,
            "profile_id": self.profile_id,
            "exporter_key": self.exporter_key,
            "unity_version": self.unity_version,
            "backend": self.backend,
            "arch": self.arch,
            "has_bepinex": self.has_bepinex,
            "bepinex_variant": self.bepinex_variant,
            "bepinex_version": self.bepinex_version,
            "bepinex_major": self.bepinex_major,
            "bepinex_status": {
                "installed": self.has_bepinex,
                "partial": self.bepinex_partial,
                "variant": self.bepinex_variant,
                "version": self.bepinex_version,
                "major": self.bepinex_major,
                "corePresent": self.bepinex_core_present,
                "bootstrapPresent": self.bepinex_bootstrap_present,
                "coreFiles": list(self.bepinex_core_files),
                "bootstrapFiles": list(self.bepinex_bootstrap_files),
                "missingComponents": list(self.bepinex_missing_components),
            },
        }


class SetupError(RuntimeError):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
