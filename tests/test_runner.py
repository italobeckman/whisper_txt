import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core import runner


class TestCoreRunner(unittest.TestCase):
    @patch("core.runner.resolve_audio_source")
    @patch("core.runner.Transcriber")
    def test_run_pipeline_single_audio_file(self, mock_transcriber_cls, mock_resolve):
        mock_resolve.return_value = (Path("audio.wav"), False)
        mock_transcriber = MagicMock()
        mock_transcriber_cls.return_value = mock_transcriber

        mock_transcriber.transcribe.return_value = ([MagicMock()], MagicMock())
        mock_transcriber.export_txt.return_value = Path("teste.txt")

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_file = Path(tmp_dir) / "teste.wav"
            input_file.touch()

            result = runner.run_pipeline(
                input_path=input_file,
                output_dir=Path(tmp_dir),
                quality="max",
                overwrite=True,
            )

            self.assertIn("transcripts", result)
            self.assertEqual(len(result["transcripts"]), 1)
            self.assertTrue(str(result["transcripts"][0]).endswith(".txt"))

    @patch("core.runner.resolve_audio_source")
    @patch("core.runner.Transcriber")
    def test_run_pipeline_forwards_track_index(self, mock_transcriber_cls, mock_resolve):
        mock_resolve.return_value = (Path("audio.wav"), True)
        mock_transcriber = MagicMock()
        mock_transcriber_cls.return_value = mock_transcriber
        mock_transcriber.transcribe.return_value = ([MagicMock()], MagicMock())
        mock_transcriber.export_txt.return_value = Path("teste.txt")

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_file = Path(tmp_dir) / "teste.mp4"
            input_file.touch()

            runner.run_pipeline(
                input_path=input_file,
                output_dir=Path(tmp_dir),
                track_index=2,
            )
            mock_resolve.assert_called_once_with(input_file, track_index=2)


if __name__ == "__main__":
    unittest.main()
