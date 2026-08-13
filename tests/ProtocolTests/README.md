# ProtocolTests

The binary golden fixture is generated with the production C# encoder sources:

```powershell
pixi run protocol-fixture -- <output.bin>
```

Automated consumers must accept LMEX v1 and v2. Version 2 adds `profileId`,
`role`, `roleIndex`, and `exporterVersion` before the optional `ANIM` block.

Manual runtime checks:

1. Run a Unity title with `F8SkeletonStreamer` enabled.
2. Bind a UDP listener on `39540` and decode packets with the existing `udp_skeleton.py` decoder.
3. Verify fields:
   - `modelName` contains `characterId|characterName`
   - stable identity is `profileId + role + roleIndex`
   - `timestampMs` is present
   - `schema` equals `unity.skeleton.world.v1` (or configured value)
   - `bones[]` includes world `pos` and `rot` (`qw,qx,qy,qz`)
4. Confirm chunked packets still decode with old parser (trailing extension ignored).

