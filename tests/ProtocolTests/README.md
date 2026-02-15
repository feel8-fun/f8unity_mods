# ProtocolTests

Manual protocol checks:

1. Run a Unity title with `F8HSceneAnimatorStreamer` enabled.
2. Bind a UDP listener on `39540` and decode packets with the existing `udp_skeleton.py` decoder.
3. Verify fields:
   - `modelName` contains `characterId|characterName`
   - `timestampMs` is present
   - `schema` equals `unity.skeleton.world.v1` (or configured value)
   - `bones[]` includes world `pos` and `rot` (`qw,qx,qy,qz`)
4. Confirm chunked packets still decode with old parser (trailing extension ignored).

