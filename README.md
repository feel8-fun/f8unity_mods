# F8UnityMods

F8UnityMods is a Unity modding toolkit for scene-aware capture and streamlined game setup.

The project is inspired by [LoveMachine](https://codeberg.org/Sauceke/LoveMachine) and follows a similar scene-start hook idea for identifying when capture should begin or end. From there, it applies keyword/profile rules to find relevant bones or Live2D drawables, samples transforms, and streams data over UDP to downstream tools.

## Components

- `F8SkeletonStreamer`
  Mono and IL2CPP BepInEx plugin for scene-hook driven skeleton capture and UDP streaming.
- `F8Live2DStreamer`
  Mono and IL2CPP BepInEx plugin for Live2D / drawable discovery and UDP streaming.
- `f8unitymods_setup`
  Typed detection and installation core used by Feel8 Web Studio and the command line.
- `configs/`
  Game profile templates used for process detection, hook rules, capture expressions, and keypoint binding defaults.

## Supported Workflow

The setup tool can:

1. Detect a Unity game from an `.exe` or game folder.
2. Detect backend and architecture (`Mono` / `IL2CPP`, `x86` / `x64`).
3. Match a known profile from `configs/*.json`.
4. Install the correct BepInEx flavor if it is missing.
5. Install the correct exporter build for the detected backend.
6. Optionally install RuntimeUnityEditor, CinematicUnityExplorer, ConfigurationManager, and UniversalUnityDemosaics.

The runtime plugins currently keep UDP protocol behavior unchanged. This release work only changes distribution, setup, and profile delivery.

## Config Model

- Source profile templates live in `configs/*.json`.
- The setup tool installs one active editable profile into the game directory:
  `BepInEx/plugins/F8SkeletonStreamer/profile.json` or
  `BepInEx/plugins/F8Live2DStreamer/profile.json`
- Existing custom `profile.json` files are preserved and never overwritten.
- The installer is local-first:
  it prefers bundled/local configs for debugging, then cached remote configs, then remote manifest downloads when enabled.

## Build And Local Development

Install the workspace environment:

```bash
pixi install
```

Build both exporters:

```bash
pixi run build
```

Package local plugin zips:

```bash
pixi run package
```

Build release-shaped plugin assets:

```bash
pixi run release-package
```

Detect and inspect a game installation:

```bash
pixi run setup-detect -- <game-path>
pixi run setup-diag -- <game-path>
```

Validate config templates:

```bash
pixi run config-validate
```

## Release Model

GitHub Releases are the main distribution channel.

Published release assets are split by responsibility:

- `f8unitymods_setup` Python wheel
- `F8SkeletonStreamer-mono.zip`
- `F8SkeletonStreamer-il2cpp.zip`
- `F8Live2DStreamer-mono.zip`
- `F8Live2DStreamer-il2cpp.zip`
- `configs-manifest.json`
- `release-manifest.json`
- optional `configs-pack.zip`

Feel8 Web Studio provides the end-user detect, preview, and confirmed-install workflow. The setup package remains usable as a headless CLI and resolves config profiles through the same manifest and raw JSON files.

## CI / Automation

GitHub Actions workflows are included for:

- CI builds on push and pull request
- tagged release publishing
- config validation and preview manifest generation for pull requests

See [docs/release.md](docs/release.md) for the release flow and asset layout.

## Acknowledgement

This project borrows core inspiration from LoveMachine's scene-hook workflow and overall modding approach:
[https://codeberg.org/Sauceke/LoveMachine](https://codeberg.org/Sauceke/LoveMachine)

## License

GPLv3. See `LICENSE.txt`.
