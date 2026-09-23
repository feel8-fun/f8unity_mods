# Release Notes

## Tagging Convention

- Create a Git tag such as `v0.1.0`.
- Pushing a `v*` tag triggers `.github/workflows/release.yml`.
- The tag becomes the public release version and is embedded into generated manifests.

## CI Outputs

The release workflow publishes:

- `f8unitymods_setup` Python wheel
- `F8SkeletonStreamer-mono.zip`
- `F8SkeletonStreamer-il2cpp.zip`
- `F8Live2DStreamer-mono.zip`
- `F8Live2DStreamer-il2cpp.zip`
- `configs-manifest.json`
- `release-manifest.json`
- `configs-pack.zip` as an optional admin/debug bundle

The normal CI workflow also uploads build artifacts for inspection on pushes and pull requests.

## Config Publishing

Config templates remain source-controlled under `configs/*.json`.

During release:

1. `tools/release_manifest.py validate` checks for malformed configs, duplicate profile IDs, and duplicate normalized process aliases.
2. `tools/release_manifest.py generate` writes:
   - `configs-manifest.json`
   - `release-manifest.json`
   - optional `configs-pack.zip`
3. `configs-manifest.json` points clients at raw config JSON files for the tagged revision.

The installer uses this order when resolving a known profile:

1. local/bundled config
2. cached remote config with matching checksum
3. remote manifest download
4. generated custom template

## Local-Only / Offline Use

For local debugging or air-gapped use:

- keep `prefer_local_configs = true`
- set `allow_remote_configs = false` in `tools/game_setup_config.json`, or pass `--no-remote-configs`
- use `--offline` to force cached third-party assets only

If remote self-release assets are unavailable, the setup tool falls back to local exporter artifacts when they exist in the repo/build output.
