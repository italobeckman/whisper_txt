import importlib
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import config
from cli import build_parser
from core.transcriber import Transcriber


def test_import_config_does_not_run_subprocess():
    with patch("subprocess.run") as run:
        importlib.reload(config)
        run.assert_not_called()


def test_backend_scenarios():
    for output, expected in [
        ("deviceName = NVIDIA RTX\n", "NVIDIA RTX"),
        ("deviceName = llvmpipe (LLVM)\n", "CPU"),
        ("deviceName = lavapipe\n", "CPU"),
        ("deviceName = SwiftShader Device\n", "CPU"),
        ("", "CPU"),
    ]:
        config.detect_vulkan_devices.cache_clear()
        with patch("config.subprocess.run", return_value=SimpleNamespace(stdout=output)) as run:
            assert config.backend_name() == expected
            assert config.backend_name() == expected
            run.assert_called_once()
    config.detect_vulkan_devices.cache_clear()
    with patch("config.subprocess.run", side_effect=FileNotFoundError):
        assert config.backend_name() == "CPU"
    config.detect_vulkan_devices.cache_clear()


def test_command_backend_and_device():
    for name, cpu, device, expected in [
        ("NVIDIA RTX", False, None, []),
        ("CPU", False, None, ["-ng"]),
        ("NVIDIA RTX", True, None, ["-ng"]),
        ("NVIDIA RTX", False, "1", ["--device", "1"]),
    ]:
        process = MagicMock()
        process.stdout = io.StringIO("")
        process.wait.return_value = 0
        with patch("config.backend_name", return_value="CPU" if cpu else name), \
             patch("config.get_whisper_cli", return_value=Path("whisper-cli")), \
             patch("config.get_model_path", return_value=Path("model")), \
             patch("subprocess.Popen", return_value=process) as popen:
            transcriber = Transcriber(device=device, cpu=cpu)
            transcriber.transcribe(Path("audio.wav"))
            cmd = popen.call_args.args[0]
            assert ("-ng" in cmd) == ("-ng" in expected)
            assert ("--device" in cmd) == ("--device" in expected)
            if "--device" in expected:
                assert cmd[cmd.index("--device") + 1] == "1"


def test_cli_cpu_flags():
    parser = build_parser()
    for command in ("run", "transcribe"):
        assert parser.parse_args([command, "-i", "audio.wav", "--cpu"]).cpu
