import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile

from core import audio


class TestCoreAudio(unittest.TestCase):
    def test_file_type_detection(self):
        self.assertTrue(audio.is_video_file(Path("aula.mp4")))
        self.assertTrue(audio.is_video_file(Path("aula.mkv")))
        self.assertTrue(audio.is_video_file(Path("aula.mov")))
        self.assertTrue(audio.is_video_file(Path("aula.webm")))
        self.assertTrue(audio.is_video_file(Path("aula.m4v")))
        self.assertTrue(audio.is_video_file(Path("aula.ts")))
        self.assertTrue(audio.is_video_file(Path("aula.3gp")))
        self.assertFalse(audio.is_video_file(Path("audio.wav")))
        self.assertFalse(audio.is_video_file(Path("texto.txt")))

        self.assertTrue(audio.is_audio_file(Path("audio.wav")))
        self.assertTrue(audio.is_audio_file(Path("audio.mp3")))
        self.assertTrue(audio.is_audio_file(Path("audio.m4a")))
        self.assertTrue(audio.is_audio_file(Path("audio.opus")))
        self.assertFalse(audio.is_audio_file(Path("aula.mp4")))
        self.assertFalse(audio.is_audio_file(Path("doc.pdf")))

    @patch("core.audio.get_audio_tracks")
    def test_extensionless_file_detection(self, mock_get_tracks):
        mock_get_tracks.return_value = [{"index": 0, "codec": "aac", "language": "por"}]
        with patch.object(Path, "is_file", return_value=True):
            self.assertTrue(audio.is_video_file(Path("arquivo_sem_extensao")))

    @patch("core.audio.get_audio_tracks")
    def test_non_media_file_does_not_probe_ffmpeg(self, mock_get_tracks):
        with patch.object(Path, "is_file", return_value=True):
            self.assertFalse(audio.is_video_file(Path("documento.pdf")))
            mock_get_tracks.assert_not_called()

    @patch("subprocess.run")
    def test_extract_audio_calls_ffmpeg(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        res = audio.extract_audio(Path("input.mp4"), Path("out.wav"), ffmpeg_path="ffmpeg", overwrite=True, track_index=1)
        self.assertTrue(res)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd[0], "ffmpeg")
        self.assertIn("-map", cmd)
        self.assertIn("0:a:1", cmd)
        self.assertIn("-y", cmd)
        self.assertIn("-vn", cmd)
        self.assertIn("-ac", cmd)
        self.assertIn("1", cmd)
        self.assertIn("-ar", cmd)
        self.assertIn("16000", cmd)
        self.assertIn("pcm_s16le", cmd)

    @patch("subprocess.run")
    def test_extract_audio_ffmpeg_failure_returns_false_silently(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="erro no FFmpeg")
        with patch("sys.stderr") as mock_stderr:
            res = audio.extract_audio(
                Path("input.mp4"), Path("out.wav"), ffmpeg_path="ffmpeg", overwrite=True
            )
        self.assertFalse(res)
        mock_stderr.write.assert_not_called()

    @patch("subprocess.run")
    def test_extract_audio_raises_with_stderr_tail(self, mock_run):
        stderr = "\n".join(f"linha {i}" for i in range(10))
        mock_run.return_value = MagicMock(returncode=1, stderr=stderr)
        with self.assertRaises(audio.FFmpegError) as ctx:
            audio.extract_audio(
                Path("input.mp4"),
                Path("out.wav"),
                ffmpeg_path="ffmpeg",
                overwrite=True,
                raise_on_error=True,
            )
        message = str(ctx.exception)
        self.assertIn("código 1", message)
        self.assertIn("linha 9", message)
        self.assertNotIn("linha 0", message)

    @patch("subprocess.run")
    def test_resolve_audio_source_error_includes_ffmpeg_stderr(self, mock_run):
        mock_run.return_value = MagicMock(returncode=2, stderr="[mov] moov atom not found")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError) as ctx:
                audio.resolve_audio_source(Path("voz.m4a"), temp_dir=Path(tmp))
        message = str(ctx.exception)
        self.assertIn("voz.m4a", message)
        self.assertIn("moov atom not found", message)

    def test_cleanup_temp_audio_logs_warning_instead_of_printing(self):
        with patch.object(Path, "exists", return_value=True), patch.object(
            Path, "unlink", side_effect=OSError("acesso negado")
        ):
            with patch("sys.stderr") as mock_stderr:
                with self.assertLogs("core.audio", level="WARNING") as captured:
                    audio.cleanup_temp_audio(Path("temp.wav"))
        self.assertIn("acesso negado", "\n".join(captured.output))
        mock_stderr.write.assert_not_called()

    @patch("subprocess.run")
    def test_get_audio_tracks_parses_ffmpeg_output(self, mock_run):
        mock_output = (
            "Input #0, mov,mp4,m4a,3gp,from 'aula.mp4':\n"
            "  Stream #0:0[0x1](und): Video: h264\n"
            "  Stream #0:1[0x2](por): Audio: aac (LC) (mp4a), 48000 Hz, stereo, fltp, 192 kb/s\n"
            "  Stream #0:2[0x3](eng): Audio: aac (LC) (mp4a), 48000 Hz, stereo, fltp, 128 kb/s\n"
        )
        mock_run.return_value = MagicMock(returncode=0, stderr=mock_output)
        with patch.object(Path, "exists", return_value=True):
            tracks = audio.get_audio_tracks(Path("aula.mp4"), ffmpeg_path="ffmpeg")
        self.assertEqual(len(tracks), 2)
        self.assertEqual(tracks[0]["index"], 0)
        self.assertEqual(tracks[0]["stream_id"], "0:1")
        self.assertEqual(tracks[0]["language"], "por")
        self.assertEqual(tracks[1]["index"], 1)
        self.assertEqual(tracks[1]["stream_id"], "0:2")
        self.assertEqual(tracks[1]["language"], "eng")

    def test_extract_audio_skips_when_exists_and_not_overwrite(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = Path(f.name)
        try:
            with patch("subprocess.run") as mock_run:
                res = audio.extract_audio(Path("input.mp4"), temp_path, overwrite=False)
                self.assertTrue(res)
                mock_run.assert_not_called()
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_resolve_audio_source_for_audio_file(self):
        audio_file = Path("gravacao.wav")
        resolved, is_temp = audio.resolve_audio_source(audio_file)
        self.assertEqual(resolved, audio_file)
        self.assertFalse(is_temp)

    @patch("core.audio.extract_audio")
    def test_resolve_audio_source_for_video_file(self, mock_extract):
        mock_extract.return_value = True
        video_file = Path("gravacao.mp4")
        resolved, is_temp = audio.resolve_audio_source(video_file)
        self.assertTrue(is_temp)
        self.assertTrue(str(resolved).endswith(".wav"))
        mock_extract.assert_called_once()
        # Clean up the created temp file if exists
        audio.cleanup_temp_audio(resolved)

    def test_resolve_audio_source_keeps_native_formats(self):
        for name in ("a.wav", "a.mp3", "a.flac", "a.ogg", "A.MP3"):
            with self.subTest(name=name):
                resolved, is_temp = audio.resolve_audio_source(Path(name))
                self.assertEqual(resolved, Path(name))
                self.assertFalse(is_temp)

    @patch("core.audio.extract_audio")
    def test_resolve_audio_source_converts_non_native_audio(self, mock_extract):
        """whisper-cli não lê m4a/aac/opus/wma: devem ser convertidos para WAV."""
        mock_extract.return_value = True
        for name in ("voz.m4a", "voz.aac", "voz.opus", "voz.wma"):
            with self.subTest(name=name):
                mock_extract.reset_mock()
                resolved, is_temp = audio.resolve_audio_source(Path(name))
                try:
                    self.assertTrue(is_temp)
                    self.assertTrue(str(resolved).endswith(".wav"))
                    mock_extract.assert_called_once()
                finally:
                    audio.cleanup_temp_audio(resolved)

    def test_is_native_audio_file(self):
        self.assertTrue(audio.is_native_audio_file(Path("a.WAV")))
        self.assertFalse(audio.is_native_audio_file(Path("a.m4a")))
        self.assertFalse(audio.is_native_audio_file(Path("a.mp4")))


if __name__ == "__main__":
    unittest.main()
