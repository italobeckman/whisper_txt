import asyncio
import io
import sys
import tarfile
import zipfile
from unittest.mock import Mock, patch
from urllib.error import URLError

import pytest
from textual.widgets import Label, ProgressBar

import cli
import config
from tui.app import WhisperTxtApp


def mock_response(chunks, content_length):
    response = Mock()
    response.headers = {} if content_length is None else {"Content-Length": str(content_length)}
    response.read.side_effect = chunks
    return response


@pytest.mark.parametrize("content_length", [5, None])
def test_model_download_reports_progress_and_publishes_complete_file(tmp_path, monkeypatch, content_length):
    monkeypatch.setattr(config, "MODEL_FOLDER", tmp_path)
    model_path = tmp_path / "ggml-base.bin"
    progress = []

    def on_progress(downloaded, total):
        assert not model_path.exists()
        progress.append((downloaded, total))

    with patch("config.urllib.request.urlopen") as urlopen:
        urlopen.return_value.__enter__.return_value = mock_response([b"ab", b"cde", b""], content_length)
        assert config.get_model_path(model_path.name, on_progress) == model_path
        assert config.get_model_path(model_path.name, on_progress) == model_path

    urlopen.assert_called_once()
    assert urlopen.call_args.args[0].full_url == config.MODEL_URLS[model_path.name]
    assert urlopen.call_args.kwargs["timeout"] == config.DOWNLOAD_TIMEOUT
    assert progress == [(0, content_length), (2, content_length), (5, content_length)]
    assert model_path.read_bytes() == b"abcde"
    assert list(tmp_path.iterdir()) == [model_path]


@pytest.mark.parametrize(
    ("chunks", "message"),
    [
        ([b"ab", ConnectionResetError("conexão interrompida")], "conexão interrompida"),
        ([b"ab", TimeoutError()], "tempo limite de 30 s excedido"),
        ([b"ab", b""], "Content-Length de 5 bytes, recebidos 2 bytes"),
        ([b"abcdef"], "Content-Length de 5 bytes, recebidos 6 bytes"),
    ],
)
def test_invalid_model_download_leaves_no_file_and_can_be_retried(tmp_path, monkeypatch, chunks, message):
    monkeypatch.setattr(config, "MODEL_FOLDER", tmp_path)
    model_name = "ggml-base.bin"

    with patch("config.urllib.request.urlopen") as urlopen:
        urlopen.return_value.__enter__.return_value = mock_response(chunks, 5)
        with pytest.raises(RuntimeError, match=rf"Falha ao baixar {model_name}: {message}"):
            config.get_model_path(model_name)
        assert list(tmp_path.iterdir()) == []

        urlopen.return_value.__enter__.return_value = mock_response([b"abcde", b""], 5)
        model_path = config.get_model_path(model_name)

    assert model_path.read_bytes() == b"abcde"
    assert list(tmp_path.iterdir()) == [model_path]


def test_open_timeout_identifies_download(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MODEL_FOLDER", tmp_path)
    with patch("config.urllib.request.urlopen", side_effect=URLError(TimeoutError())):
        with pytest.raises(RuntimeError, match=r"Falha ao baixar ggml-base\.bin: tempo limite de 30 s excedido"):
            config.get_model_path("ggml-base.bin")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("platform", "exe_name", "release_url"),
    [("win32", "whisper-cli.exe", config.VULKAN_RELEASE_URL), ("linux", "whisper-cli", config.LINUX_RELEASE_URL)],
)
def test_binary_download_validates_archive_before_extraction(tmp_path, monkeypatch, platform, exe_name, release_url):
    monkeypatch.setattr(config, "BIN_FOLDER", tmp_path)
    archive = io.BytesIO()
    executable = b"mock executable"
    if platform == "win32":
        with zipfile.ZipFile(archive, "w") as zip_ref:
            zip_ref.writestr(exe_name, executable)
    else:
        with tarfile.open(fileobj=archive, mode="w:gz") as tar_ref:
            member = tarfile.TarInfo(f"release/bin/{exe_name}")
            member.size = len(executable)
            tar_ref.addfile(member, io.BytesIO(executable))

    data = archive.getvalue()
    progress = Mock()
    with (
        patch("config.sys.platform", platform),
        patch("config.shutil.which", return_value=None),
        patch("config.urllib.request.urlopen") as urlopen,
    ):
        urlopen.return_value.__enter__.return_value = mock_response([data[:10], b""], len(data))
        with pytest.raises(RuntimeError, match="Content-Length"):
            config.get_whisper_cli(progress)
        assert list(tmp_path.iterdir()) == []

        urlopen.return_value.__enter__.return_value = mock_response([data, b""], len(data))
        cli_path = config.get_whisper_cli(progress)

    assert urlopen.call_args.args[0].full_url == release_url
    progress.assert_called_with(len(data), len(data))
    assert cli_path == tmp_path / exe_name
    assert cli_path.read_bytes() == executable
    assert list(tmp_path.iterdir()) == [cli_path]


@pytest.fixture
def transcription_input(tmp_path, monkeypatch):
    audio_path = tmp_path / "audio.wav"
    audio_path.touch()
    monkeypatch.setattr(config, "MODEL_FOLDER", tmp_path / "models")
    monkeypatch.setattr(config, "get_whisper_cli", Mock(return_value=tmp_path / "whisper-cli"))
    monkeypatch.setattr(config, "backend_name", Mock(return_value="CPU"))
    process = Mock()
    process.stdout = io.StringIO("progress = 50%\n")
    process.wait.return_value = 0
    monkeypatch.setattr("core.transcriber.subprocess.Popen", Mock(return_value=process))
    return audio_path


@pytest.mark.parametrize("command", ["transcribe", "run"])
def test_cli_displays_download_progress(command, transcription_input, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["whisper-txt", command, "-i", str(transcription_input)])
    with patch("config.urllib.request.urlopen") as urlopen:
        urlopen.return_value.__enter__.return_value = mock_response([b"ab", b"cde", b""], 5)
        cli.main()

    output = capsys.readouterr().out
    assert "Baixando modelo... 40%" in output
    assert "Baixando modelo... 100%" in output
    assert transcription_input.with_suffix(".txt").exists()


@pytest.mark.asyncio
async def test_tui_displays_download_progress(transcription_input, capsys):
    app = WhisperTxtApp()
    states = []

    def capture_progress():
        status = app.query_one("#lbl-status", Label)
        bar = app.query_one("#progress-bar", ProgressBar)
        states.append((str(status.render()), bar.progress, bar.total))

    def download_chunks():
        yield b"ab"
        app.call_from_thread(capture_progress)
        yield b"cde"
        yield b""

    with patch("config.urllib.request.urlopen") as urlopen:
        urlopen.return_value.__enter__.return_value = mock_response(download_chunks(), 5)
        async with app.run_test():
            app.selected_file = transcription_input
            app.start_transcription()
            worker = next(worker for worker in app.workers if worker.name == "run_transcription_worker")
            await asyncio.wait_for(worker.wait(), timeout=15)
            bar = app.query_one("#progress-bar", ProgressBar)
            assert bar.progress == bar.total == 100

    assert states == [("Status: Baixando modelo... 40%", 2, 5)]
    assert transcription_input.with_suffix(".txt").exists()
    output = capsys.readouterr()
    assert output.out == output.err == ""
