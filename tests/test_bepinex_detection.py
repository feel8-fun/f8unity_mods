from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from f8unitymods_setup.common import DetectionResult, SetupConfig, detect_bepinex, inspect_bepinex
from f8unitymods_setup.game_setup import _build_install_plan, run_install


class BepInExDetectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.game_root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _detection(self) -> DetectionResult:
        state = inspect_bepinex(self.game_root)
        return DetectionResult(
            target_input=str(self.game_root / "Game.exe"),
            game_root=self.game_root,
            exe_path=self.game_root / "Game.exe",
            data_dir=self.game_root / "Game_Data",
            process_name="Game",
            game_type="test",
            profile_id="test",
            exporter_key="default",
            unity_version="2021.3.1f1",
            backend="mono",
            arch="x64",
            has_bepinex=state.installed,
            bepinex_variant=state.variant,
            bepinex_version=state.version,
            bepinex_major=state.major,
            bepinex_partial=state.partial,
            bepinex_core_present=state.core_present,
            bepinex_bootstrap_present=state.bootstrap_present,
            bepinex_core_files=state.core_files,
            bepinex_bootstrap_files=state.bootstrap_files,
            bepinex_missing_components=state.missing_components,
        )

    def _config(self) -> SetupConfig:
        return SetupConfig(
            self_release_repo="",
            self_release_tag="",
            self_release_channel="latest",
            config_manifest_url="",
            config_base_url="",
            prefer_local_configs=True,
            allow_remote_configs=False,
            bepinex_release_repo="",
            bepinex_be_index_url="",
            rue_release_repo="",
            cue_release_repo="",
            config_manager_release_repo="",
            universal_unity_demosaics_release_repo="",
            cache_dir=self.game_root / "cache",
            remote_cache_dir=self.game_root / "remote-cache",
            timeout_sec=1,
            remote_timeout_sec=1,
            asset_regex_overrides={},
        )

    def test_proxy_without_core_is_partial_not_installed(self) -> None:
        (self.game_root / "winhttp.dll").write_bytes(b"proxy")

        state = inspect_bepinex(self.game_root)

        self.assertFalse(state.installed)
        self.assertTrue(state.partial)
        self.assertFalse(state.core_present)
        self.assertFalse(state.bootstrap_present)
        self.assertIn("BepInEx/core/BepInEx*.dll", state.missing_components)
        self.assertIn("doorstop_config.ini", state.missing_components)
        self.assertEqual(detect_bepinex(self.game_root), (False, "unknown", "unknown", None))

    def test_exporter_directory_without_loader_core_is_partial(self) -> None:
        plugin_dir = self.game_root / "BepInEx" / "plugins" / "F8SkeletonStreamer"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "F8SkeletonStreamer.dll").write_bytes(b"plugin")

        state = inspect_bepinex(self.game_root)

        self.assertFalse(state.installed)
        self.assertTrue(state.partial)
        self.assertEqual(
            state.missing_components,
            ("BepInEx/core/BepInEx*.dll", "doorstop_config.ini", "winhttp.dll"),
        )

        plan = _build_install_plan(
            self._detection(),
            force_reinstall=False,
            skip_exporter=False,
            install_rue=False,
            install_cue=False,
            install_config_manager=False,
            install_uud=False,
            prefer_local_configs=True,
            allow_remote_configs=False,
            refresh_remote_cache=False,
            release_tag="",
        )
        self.assertIn("repair_incomplete_bepinex", plan["actions"])
        self.assertEqual(plan["blocking_errors"], [])

    def test_complete_mono_loader_requires_core_and_bootstrap(self) -> None:
        core_dir = self.game_root / "BepInEx" / "core"
        core_dir.mkdir(parents=True)
        core_dll = core_dir / "BepInEx.dll"
        core_dll.write_bytes(b"core")
        (self.game_root / "doorstop_config.ini").write_text("enabled=true\n", encoding="utf-8")
        (self.game_root / "winhttp.dll").write_bytes(b"proxy")

        with mock.patch("f8unitymods_setup.common._read_windows_file_version", return_value="5.4.23.3"):
            state = inspect_bepinex(self.game_root)

        self.assertTrue(state.installed)
        self.assertFalse(state.partial)
        self.assertEqual(state.variant, "mono")
        self.assertEqual(state.version, "5.4.23.3")
        self.assertEqual(state.major, 5)
        self.assertEqual(state.core_files, (str(core_dll),))
        self.assertEqual(state.missing_components, ())

    def test_core_without_winhttp_proxy_is_partial(self) -> None:
        core_dir = self.game_root / "BepInEx" / "core"
        core_dir.mkdir(parents=True)
        (core_dir / "BepInEx.Unity.IL2CPP.dll").write_bytes(b"core")
        (self.game_root / "doorstop_config.ini").write_text("enabled=true\n", encoding="utf-8")

        with mock.patch("f8unitymods_setup.common._read_windows_file_version", return_value="6.0.0"):
            state = inspect_bepinex(self.game_root)

        self.assertFalse(state.installed)
        self.assertTrue(state.partial)
        self.assertEqual(state.variant, "il2cpp")
        self.assertTrue(state.core_present)
        self.assertFalse(state.bootstrap_present)
        self.assertEqual(state.missing_components, ("winhttp.dll",))

    def test_auxiliary_dll_without_loader_entry_point_is_partial(self) -> None:
        core_dir = self.game_root / "BepInEx" / "core"
        core_dir.mkdir(parents=True)
        auxiliary_dll = core_dir / "BepInEx.Harmony.dll"
        auxiliary_dll.write_bytes(b"auxiliary")
        (self.game_root / "doorstop_config.ini").write_text("enabled=true\n", encoding="utf-8")
        (self.game_root / "winhttp.dll").write_bytes(b"proxy")

        state = inspect_bepinex(self.game_root)

        self.assertFalse(state.installed)
        self.assertTrue(state.partial)
        self.assertFalse(state.core_present)
        self.assertEqual(state.variant, "unknown")
        self.assertEqual(state.core_files, (str(auxiliary_dll),))
        self.assertIn("BepInEx/core/BepInEx*.dll", state.missing_components)

    def test_install_repairs_partial_loader_and_reports_evidence(self) -> None:
        (self.game_root / "winhttp.dll").write_bytes(b"proxy")
        partial = self._detection()
        complete = replace(
            partial,
            has_bepinex=True,
            bepinex_variant="mono",
            bepinex_version="5.4.23.3",
            bepinex_major=5,
            bepinex_partial=False,
            bepinex_core_present=True,
            bepinex_bootstrap_present=True,
            bepinex_core_files=(str(self.game_root / "BepInEx" / "core" / "BepInEx.dll"),),
            bepinex_bootstrap_files=(
                str(self.game_root / "doorstop_config.ini"),
                str(self.game_root / "winhttp.dll"),
            ),
            bepinex_missing_components=(),
        )

        with mock.patch("f8unitymods_setup.game_setup.detect_game", side_effect=(partial, complete)), mock.patch(
            "f8unitymods_setup.game_setup._install_bepinex_mono"
        ) as installer:
            result = run_install(
                target=str(partial.exe_path),
                config=self._config(),
                skip_exporter=True,
            )

        installer.assert_called_once()
        self.assertIn({"install_bepinex": "repaired_incomplete"}, result["actions"])
        self.assertTrue(result["bepinex_status"]["installed"])
        self.assertTrue(result["bepinex_status"]["corePresent"])
        self.assertTrue(result["bepinex_status"]["bootstrapPresent"])
        self.assertEqual(result["bepinex_status"]["missingComponents"], [])


if __name__ == "__main__":
    unittest.main()
