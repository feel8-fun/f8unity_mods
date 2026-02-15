# RuntimeMockTests

Runtime validation checklist:

1. Verify mode switching:
   - `HookOnly`, `Hybrid`, `AlwaysOn` via UDP command `set_mode`
   - hotkeys `F6` (capture toggle) and `F7` (mode cycle)
2. Verify event stream on metadata port `39541`:
   - `capture_on/off`
   - `h_start/end`
   - `scene_change`
   - `character_join/leave`
   - `pose_change`
   - `hook_called`
3. Verify control port `39542` commands:
   - `set_mode`
   - `set_capture`
   - `reload_config`
   - `ping` (expects `pong` response)
4. Verify 60fps sampling target under normal load and stable frame ids.

