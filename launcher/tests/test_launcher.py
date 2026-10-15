# SPDX-License-Identifier: GPL-2.0-only
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from gow3ps3 import app, diagnostics, game, psf, rpcs3, settings, sysinfo
from helpers import make_fake_rpcs3, make_firmware, make_game


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class PsfTests(unittest.TestCase):
    def test_round_trip(self):
        data = psf.build({"TITLE_ID": "BCES00510", "ATTRIBUTE": 32, "TITLE": "GOD OF WAR® III"})
        self.assertEqual(psf.parse(data), {"TITLE_ID": "BCES00510", "ATTRIBUTE": 32, "TITLE": "GOD OF WAR® III"})

    def test_rejects_other_files(self):
        with self.assertRaises(psf.PsfError):
            psf.parse(b"not a sfo file at all")

    def test_rejects_truncated(self):
        with self.assertRaises(psf.PsfError):
            psf.parse(psf.build({"TITLE_ID": "BCUS98111"})[:30])


class GameTests(TempDirCase):
    def test_disc_layout_is_recognised(self):
        info = game.inspect(make_game(self.tmp / "disc"))
        self.assertTrue(info.ok, info.findings)
        self.assertEqual((info.serial, info.region, info.required_firmware), ("BCUS98111", "América do Norte", "3.15"))
        self.assertEqual(info.boot_path, self.tmp / "disc")
        self.assertEqual(info.eboot_kind, "SELF (original do disco)")

    def test_ps3_game_folder_selected_directly(self):
        make_game(self.tmp / "disc")
        info = game.inspect(self.tmp / "disc" / "PS3_GAME")
        self.assertTrue(info.ok)
        self.assertEqual(info.boot_path, self.tmp / "disc" / "PS3_GAME")

    def test_other_game_is_refused(self):
        info = game.inspect(make_game(self.tmp / "x", serial="BLUS30001"))
        self.assertFalse(info.ok)

    def test_missing_eboot_is_an_error(self):
        info = game.inspect(make_game(self.tmp / "x", eboot=None))
        self.assertFalse(info.ok)

    def test_corrupt_eboot_is_an_error(self):
        info = game.inspect(make_game(self.tmp / "x", eboot=b"garbage!"))
        self.assertFalse(info.ok)

    def test_empty_files_are_reported(self):
        root = make_game(self.tmp / "x")
        (root / "PS3_GAME" / "USRDIR" / "level.psarc").write_bytes(b"")
        info = game.inspect(root)
        self.assertTrue(any(f.level == "aviso" and "vazio" in f.message for f in info.findings))

    def test_manifest_detects_changes(self):
        root = make_game(self.tmp / "x")
        saved = game.file_manifest(root / "PS3_GAME")
        self.assertEqual(game.compare_manifest(saved, saved)[0].level, "ok")
        (root / "PS3_GAME" / "USRDIR" / "data.psarc").write_bytes(b"alterado")
        self.assertEqual(game.compare_manifest(saved, game.file_manifest(root / "PS3_GAME"))[0].level, "erro")


class Rpcs3Tests(TempDirCase):
    def test_windows_env_keeps_trailing_separator(self):
        env = rpcs3.environment(r"C:\Users\x\GOW3PS3PC\rpcs3_profile", base_env={}, platform="win32")
        self.assertTrue(env["RPCS3_CONFIG_DIR"].endswith("\\"))

    def test_linux_env_uses_xdg(self):
        env = rpcs3.environment(self.tmp, base_env={}, platform="linux")
        self.assertEqual(env["XDG_CONFIG_HOME"], str(self.tmp / "xdg" / "config"))
        self.assertEqual(env["XDG_CACHE_HOME"], str(self.tmp / "xdg" / "cache"))

    def test_profile_paths(self):
        win = rpcs3.profile_paths(Path("P"), "win32")
        self.assertEqual(win.log_file, Path("P/log/RPCS3.log"))
        self.assertEqual(win.savedata, Path("P/dev_hdd0/home/00000001/savedata"))
        lin = rpcs3.profile_paths(Path("P"), "linux")
        self.assertEqual(lin.dev_flash, Path("P/xdg/config/rpcs3/dev_flash"))
        self.assertEqual(lin.log_file, Path("P/xdg/cache/rpcs3/RPCS3.log"))

    def test_firmware_version_matches_rpcs3_rule(self):
        for raw, expected in (("04.9200", "4.92"), ("04.9000", "4.90"), ("03.1500", "3.15"), ("00.3100", "0.31")):
            make_firmware(self.tmp, raw)
            paths = rpcs3.profile_paths(self.tmp, "win32")
            self.assertEqual(rpcs3.firmware_version(paths), expected, raw)
            self.assertTrue(rpcs3.firmware_installed(paths))

    def test_boot_command(self):
        command = rpcs3.boot_command("rpcs3.exe", "D:/GOW3", "cfg.yml", fullscreen=True)
        self.assertEqual(command, ["rpcs3.exe", "--no-gui", "--fullscreen", "--config", "cfg.yml", "D:/GOW3"])
        self.assertNotIn("--fullscreen", rpcs3.boot_command("rpcs3.exe", "g", "c", fullscreen=False))

    def test_portable_folder_is_detected(self):
        exe = self.tmp / "rpcs3.exe"
        exe.write_bytes(b"")
        self.assertIsNone(rpcs3.portable_dir(exe))
        (self.tmp / "portable").mkdir()
        self.assertIsNotNone(rpcs3.portable_dir(exe))
        self.assertEqual(rpcs3.find_executable(self.tmp), exe)


class SettingsTests(TempDirCase):
    def test_mapping(self):
        tree = settings.rpcs3_config(settings.Settings(internal_resolution="1440p", output_scaling="fsr",
                                                       anisotropic=16, vsync="full", frame_limit="60"))
        video = tree["Video"]
        self.assertEqual(video["Resolution Scale"], 200)
        self.assertEqual(video["Output Scaling Mode"], "FidelityFX Super Resolution")
        self.assertEqual(video["Anisotropic Filter Override"], 16)
        self.assertEqual(video["VSync Mode"], "Full")
        self.assertEqual(video["Frame limit"], "60")
        self.assertTrue(video["Write Color Buffers"])
        self.assertEqual(tree["Core"]["SPU Block Size"], "Safe")

    def test_invalid_values_are_refused(self):
        with self.assertRaises(ValueError):
            settings.rpcs3_config(settings.Settings(internal_resolution="8K"))
        with self.assertRaises(ValueError):
            settings.rpcs3_config(settings.Settings(anisotropic=3))

    def test_yaml_is_valid(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML não instalado")
        path = settings.write_rpcs3_config(settings.Settings(vulkan_adapter='AMD "Radeon"'), self.tmp / "c.yml")
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded, settings.rpcs3_config(settings.Settings(vulkan_adapter='AMD "Radeon"')))

    def test_save_and_corrupt_file(self):
        value = settings.Settings(game_path="D:/GOW3", internal_resolution="1080p")
        settings.save(value, self.tmp / "s.json")
        self.assertEqual(settings.load(self.tmp / "s.json"), value)
        (self.tmp / "bad.json").write_text("{nope")
        self.assertEqual(settings.load(self.tmp / "bad.json"), settings.Settings())


class DiagnosticsTests(unittest.TestCase):
    def test_known_errors(self):
        log = ("·! 0:00:00.000 SYS: RPCS3 v0.0.38\n"
               "·W 0:00:01.000 SYS: something\n"
               "·E 0:00:01.000 SYS: Booting '/g' with cli argument failed: reason: Firmware is missing\n"
               "·F 0:00:02.000 RSX: No compatible GPU devices found\n")
        report = diagnostics.analyse_text(log)
        self.assertEqual((report.errors, report.warnings), (1, 1))
        self.assertEqual(report.fatal, ["0:00:02.000 RSX: No compatible GPU devices found"])
        self.assertEqual(len(report.explanations), 2)


class SysinfoTests(unittest.TestCase):
    def test_vulkaninfo_summary(self):
        text = ("Devices:\n========\nGPU0:\n\tdeviceName         = AMD Radeon 890M\n"
                "GPU1:\n\tdeviceName         = NVIDIA GeForce RTX 4090 Laptop GPU\n")
        self.assertEqual(sysinfo.parse_vulkaninfo(text), ["AMD Radeon 890M", "NVIDIA GeForce RTX 4090 Laptop GPU"])

    def test_evaluate(self):
        weak = sysinfo.SystemInfo(threads=2, avx2=False, ram_gb=4, vulkan_checked=True)
        levels = [f.level for f in sysinfo.evaluate(weak)]
        self.assertEqual(levels.count("aviso"), 3)
        self.assertIn("erro", levels)
        self.assertTrue(sysinfo.collect().threads > 0)


@unittest.skipIf(sys.platform.startswith("win"), "o RPCS3 falso é um script de shell")
class EndToEndTests(TempDirCase):
    def test_preflight_and_launch_with_fake_rpcs3(self):
        record = self.tmp / "record.json"
        executable = make_fake_rpcs3(self.tmp / "rpcs3", record)
        game_root = make_game(self.tmp / "God of War III")
        launcher = app.Launcher(base_dir=self.tmp / "home", platform="linux")
        value = settings.Settings(rpcs3_path=str(executable.parent), game_path=str(game_root),
                                  internal_resolution="1080p")

        findings, _ = launcher.preflight(value)
        self.assertTrue(any("Firmware" in f.message and f.level == "erro" for f in findings))
        with self.assertRaises(RuntimeError):
            launcher.play(value)

        make_firmware(launcher.paths.emu_dir)
        findings, info = launcher.preflight(value)
        self.assertFalse([f for f in findings if f.level == "erro"], findings)
        self.assertEqual(launcher.play(value).wait(), 0)

        seen = json.loads(record.read_text())
        config = launcher.paths.override_config
        self.assertEqual(seen["argv"], ["--no-gui", "--fullscreen", "--config", str(config), str(game_root)])
        self.assertEqual(seen["env"]["XDG_CONFIG_HOME"], str(launcher.profile_dir / "xdg" / "config"))
        self.assertIn("Resolution Scale: 150", config.read_text())

    def test_firmware_install_command(self):
        record = self.tmp / "record.json"
        executable = make_fake_rpcs3(self.tmp / "rpcs3", record)
        launcher = app.Launcher(base_dir=self.tmp / "home", platform="linux")
        pup = self.tmp / "PS3UPDAT.PUP"
        pup.write_bytes(b"x")
        launcher.install_firmware(settings.Settings(rpcs3_path=str(executable)), pup).wait()
        self.assertEqual(json.loads(record.read_text())["argv"], ["--installfw", str(pup)])
        with self.assertRaises(RuntimeError):
            launcher.install_firmware(settings.Settings(rpcs3_path=str(executable)), self.tmp / "other.bin")


if __name__ == "__main__":
    unittest.main()
