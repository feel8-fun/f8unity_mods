# F8Live2DStreamer

Independent BepInEx plugin for real-time Live2D drawable bounding box export over UDP.

Protocol schema:

- `unity.live2d.drawables.bbox.v1`
- optional keypoint stream from drawable bbox center: `unity.keypoints.realtime.v1`

Profile switches:
- `emitDrawablesBbox` controls whether drawable bbox packets are sent.
- `emitKeypointsFromDrawables` controls whether keypoint packets are sent.

Default network target:

- Host: `127.0.0.1`
- Port: `39550`
