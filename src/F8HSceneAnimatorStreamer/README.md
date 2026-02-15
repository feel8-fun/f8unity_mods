# F8HSceneAnimatorStreamer

Independent BepInEx (Mono) plugin for real-time skeleton export over UDP.

Project toolchain:

- Solution: `F8UnityMods.sln`
- Build/package: `python tools/build.py build|package`
- Auto setup helper: `python tools/game_setup.py detect|diagnose|install`
- Setup guide: `docs/F8HSceneAnimatorStreamer.Setup.md`

## Ports

- Skeleton: `39540` (binary, hook-only realtime keypoint stream)
