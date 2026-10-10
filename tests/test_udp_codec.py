from pathlib import Path
import unittest

from tools.udp_dump import decode_skeleton_packet


class UdpCodecTests(unittest.TestCase):
    def test_sdk_golden_packet_preserves_identity_and_animation(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sdk = root / ".sdk"
        if not sdk.exists():
            sdk = root.parents[1] / "sdk"
        packet = decode_skeleton_packet((sdk / "python/tests/fixtures/unity_skeleton_v2.bin").read_bytes())
        self.assertIsNotNone(packet)
        assert packet is not None
        self.assertEqual(packet["trailer"]["profileId"], "hs2")
        self.assertEqual(packet["trailer"]["role"], "Female")
        self.assertEqual(packet["trailer"]["anim"]["clipName"], "Loop")
        self.assertEqual(packet["trailer"]["anim"]["poseKey"], "fixture_pose")

    def test_non_skeleton_datagram_uses_other_format_probes(self) -> None:
        self.assertIsNone(decode_skeleton_packet(b"plain text"))
