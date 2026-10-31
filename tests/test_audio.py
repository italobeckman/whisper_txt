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
        self.assertFalse(audio.is_video_file(Path("audio.wav")))
        self.assertFalse(audio.is_video_file(Path("texto.txt")))

        self.assertTrue(audio.is_audio_file(Path("audio.wav")))
        self.assertTrue(audio.is_audio_file(Path("audio.mp3")))
        self.assertTrue(audio.is_audio_file(Path("audio.m4a")))
        self.assertFalse(audio.is_audio_file(Path("aula.mp4")))
        self.assertFalse(audio.is_audio_file(Path("doc.pdf")))

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


if __name__ == "__main__":
    unittest.main()
