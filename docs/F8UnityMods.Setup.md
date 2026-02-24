# F8SkeletonStreamer Setup

## Overview

This repository now has a standalone toolchain for `F8SkeletonStreamer`:

- Independent solution: `F8UnityMods.sln`
- Build/package/install script: `tools/build.py`
- Game helper (detect/install/diagnose): `tools/game_setup.py`

`lovemachine_src/` is treated as legacy/reference source and is not part of the new solution.

## Root pixi environment for Game Setup UI

Use repository root as the single pixi project:

```bash
pixi install
```

Launch UI directly:

```bash
pixi run ui
```

Build onefile exe:

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File tools/ui/build_exe.ps1
```

## Build

```bash
pixi run build
```

Equivalent CLI:

```bash
python tools/build.py build --exporter both
```

## Package

```bash
pixi run package
```

Output zips:

- `dist/F8SkeletonStreamer/F8SkeletonStreamer.zip`
- `dist/F8Live2DStreamer/F8Live2DStreamer.zip`

Single-exporter examples:

```bash
python tools/build.py build --exporter skeleton
python tools/build.py build --exporter live2d
python tools/build.py package --exporter skeleton
python tools/build.py package --exporter live2d
```

## Local install into a game

```bash
pixi run install -- --game "C:\Games\MyUnityGame\MyUnityGame.exe"
```

## Detect game metadata

```bash
pixi run setup-detect -- --target "C:\Games\MyUnityGame"
```

Returns JSON fields:

- `game_root`
- `exe_path`
- `unity_version`
- `backend` (`mono|il2cpp|unknown`)
- `arch` (`x86|x64|unknown`)
- `process_name`
- `game_type` (auto-derived from `configs/*.json`, or `unknown`)
- `profile_id` (template `id` from matched config, or `""`)
- `streamer_type` (`skeleton|live2d|unknown`, from config `streamerType`)
- `exporter_key` (`default|live2d`, resolved install target)
- `has_bepinex`
- `bepinex_variant`
- `bepinex_version`

## Dry-run setup diagnosis

```bash
pixi run setup-diag -- --target "C:\Games\MyUnityGame" --offline
```

## Full setup

```bash
pixi run setup-install -- --target "C:\Games\MyUnityGame"
```

Behavior:

1. Detect backend/arch/unity version.
2. Detect supported game type/profile from process name (auto-loaded from `configs/*.json` templates).
3. Install matching BepInEx if missing.
4. Install exporter plugin from local build output, automatically selecting `Mono` or `IL2CPP` build.
5. Install exporter config at `BepInEx/config/com.feel8.f8-skeleton-streamer.cfg`
   with profile-aware hook defaults (unless a custom unmanaged config already exists).
6. Install single active profile at
   `BepInEx/plugins/F8SkeletonStreamer/profile.json`:
   - Known game: installs matching template from `configs/*.json`.
   - Unknown game: installs a minimal editable `CUSTOM` template.
7. Install RuntimeUnityEditor release matching BepInEx major line.
8. Install CinematicUnityExplorer release matching BepInEx variant.

Unified setup note:

- Legacy standalone Live2D setup script has been removed.
- Use `tools/game_setup.py` for both exporters.
- `--exporter auto|skeleton|live2d` is supported.
- In `configs/*.json`, `streamerType` controls auto routing (`skeleton` by default, set `live2d` when needed).

Live2D build/package shortcuts:

```bash
pixi run lbuild
pixi run lpackage
pixi run linstall -- --game "C:\Games\MyUnityGame\MyUnityGame.exe"
```

Renaming note:

- Current naming is `F8SkeletonStreamer` / `F8Live2DStreamer`.
- No automatic migration is performed from legacy plugin/config paths.
- If you previously used old names, remove old plugin folders/config files manually.

Runtime profile loading is single-file mode:

- Only `BepInEx/plugins/F8SkeletonStreamer/profile.json` is loaded.
- Legacy `profiles/*.json` files are ignored by runtime.

Runtime capture mode is hook-only:

- Streaming starts on configured `h_start` hooks and stops on `h_end`.
- No fallback discovery, metadata stream, sample stream, control UDP, or hotkey gating.
- Skeleton packets are emitted on the configured `SkeletonHost/SkeletonPort` only.
- Hook debug logs are written on `HStart/HEnd` hits (method + instance label) in `BepInEx/LogOutput.log`.

Full Hierarchy Debug Dump:

- Controlled by profile field `debugDumpFullHierarchy` (optional, default `false` when omitted).
- Recommended usage is in unknown/custom profile templates (`id = CUSTOM`) as a debug-only switch.
- While debug mode is ON, exporter sends both:
  - normal stream schema: `unity.keypoints.realtime.v1`
  - full hierarchy schema: `unity.transforms.fullhierarchy.v1`
- Full hierarchy names use root-relative transform paths and can include inactive nodes
  (`[Capture] DebugDumpIncludeInactive = true|false` in cfg).
- This mode can significantly increase UDP traffic due to larger bone counts/chunking.

Live profile editing (no game restart):

- Edit `BepInEx/plugins/F8SkeletonStreamer/profile.json` directly.
- Runtime polls config/profile changes and auto reloads hooks/profile.

2D / Spine / Animbone profile notes:

- No protocol change is needed; the exporter still streams standard transform skeleton packets.
- `femaleRootsExpr` must resolve to a valid root `Transform` for the 2D character/object.
- `maleRootsExpr` can be set independently; female/male are emitted as independent character packets.
- `maleControllerExpr` and `maxMaleCount` are optional controls for male-side state/count.
- `keypoints` can start with only `FemaleRoot`, then gradually add `Mouth/LeftHand/RightHand/LeftFoot/RightFoot`.
- `femaleControllerExpr` can be empty or unresolved; skeleton streaming still works.
- Without `Animator/Animation` controller state, packets keep streaming with `PoseKey = no_controller`.
- `hooksStart` and `hooksEnd` are the only runtime gate for starting/stopping stream.

Profile expression tips:

- `??` means fallback, only first non-empty branch is used.
  Example: `path exact A ?? path exact B`
- `||` means union, all branches are evaluated and merged.
  Example: `path exact CH_Prefub_A/CHbase || path exact CH_Prefub_B/CHbase`
- Union results are merged in order and deduplicated by Unity object instance.

Optional custom animation context fields:

- `customPoseExpr`
- `customNormalizedTimeExpr`
- `customSpeedExpr`
- `customLengthExpr`

When normal Animator/Animation state reading fails, runtime can fall back to these expressions
to emit animation context (`ANIM` trailer) instead of `no_controller`.

Optional auto-end field:

- `autoEndOnNoCharactersSeconds` (default `0` = disabled)

If set to `> 0`, hook session auto-ends after this many seconds with no active characters.

Useful options:

- `--force-reinstall`: replace mismatched existing BepInEx after backup.
- `--skip-rue`: skip RuntimeUnityEditor install.
- `--skip-cue`: skip CinematicUnityExplorer install.
- `--skip-exporter`: skip exporter install.
- `--offline`: use cached artifacts only.

## Common errors

- `backend is unknown`
  - Game directory did not match a standard Unity layout (`<GameName>_Data` + Mono/IL2CPP markers).
- `architecture is unknown`
  - PE header of exe was not x86/x64.
- `BepInEx variant mismatches backend`
  - Use `--force-reinstall` to backup and replace with correct variant.
- `offline mode but cache missing`
  - Run once without `--offline` to populate cache.
