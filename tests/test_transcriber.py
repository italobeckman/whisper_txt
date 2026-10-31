import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.transcriber import PRESETS, Segment, Transcriber, normalize_model_filename


class TestCoreTranscriber(unittest.TestCase):
    def test_presets_structure(self):
        self.assertIn("max", PRESETS)
        self.assertIn("balanced", PRESETS)
        self.assertIn("fast", PRESETS)

        self.assertEqual(PRESETS["max"]["model"], "ggml-large-v3-turbo.bin")
        self.assertEqual(PRESETS["max"]["beam_size"], 5)

        self.assertEqual(PRESETS["balanced"]["model"], "ggml-large-v3-turbo-q5_0.bin")
        self.assertEqual(PRESETS["balanced"]["beam_size"], 5)

        self.assertEqual(PRESETS["fast"]["model"], "ggml-large-v3-turbo-q5_0.bin")
        self.assertEqual(PRESETS["fast"]["beam_size"], 1)

    def test_normalize_model_filename(self):
        self.assertEqual(
            normalize_model_filename(None, "ggml-large-v3-turbo-q5_0.bin"),
            "ggml-large-v3-turbo-q5_0.bin",
        )
        self.assertEqual(
            normalize_model_filename("ggml-custom.bin", "default.bin"),
            "ggml-custom.bin",
        )
        self.assertEqual(
            normalize_model_filename("large-v3-turbo.bin", "default.bin"),
            "ggml-large-v3-turbo.bin",
        )
        self.assertEqual(
            normalize_model_filename("large-v3-turbo-q5_0", "default.bin"),
            "ggml-large-v3-turbo-q5_0.bin",
        )
        self.assertEqual(
            normalize_model_filename("base", "default.bin"),
            "ggml-base.bin",
        )

    def test_export_txt_creates_file(self):
        segments = [
            Segment(0.0, 3.5, "Olá mundo."),
            Segment(4.0, 7.2, "Esta é uma aula de teste."),
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            base_out = Path(tmp_dir) / "teste_aula"
            transcriber = Transcriber.__new__(Transcriber)

            txt_file = transcriber.export_txt(
                segments=segments,
                base_output_path=base_out,
                overwrite=True,
            )

            self.assertTrue(txt_file.exists())
            self.assertEqual(txt_file.name, "teste_aula.txt")

            txt_content = txt_file.read_text(encoding="utf-8")
            self.assertIn("Olá mundo.", txt_content)
            self.assertIn("Esta é uma aula de teste.", txt_content)

    def test_export_txt_preserves_dots_in_filename(self):
        segments = [Segment(0.0, 2.0, "Texto teste.")]
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_out = Path(tmp_dir) / "Aula 1.1 - Redes"
            transcriber = Transcriber.__new__(Transcriber)
            txt_file = transcriber.export_txt(
                segments=segments,
                base_output_path=base_out,
                overwrite=True,
            )
            self.assertEqual(txt_file.name, "Aula 1.1 - Redes.txt")
            self.assertTrue(txt_file.exists())

    @patch("config.get_model_path")
    @patch("config.get_whisper_cli")
    @patch("subprocess.Popen")
    def test_transcribe_invokes_callbacks_and_parses_stream(
        self, mock_popen, mock_get_cli, mock_get_model
    ):
        mock_get_cli.return_value = Path("bin/whisper-cli.exe")
        mock_get_model.return_value = Path("models/ggml-large-v3-turbo-q5_0.bin")

        mock_process = MagicMock()
        mock_process.stdout = io.StringIO(
            "whisper_init: loading model\n"
            "progress = 25%\n"
            "[00:00:00.000 --> 00:00:02.500]   Primeira fala transcrita.\n"
            "progress = 75%\n"
            "[00:00:02.500 --> 00:00:05.100]   Segunda fala transcrita.\n"
            "progress = 100%\n"
        )
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        transcriber = Transcriber(quality="fast")

        collected_segments = []
        progress_calls = []

        def on_segment(seg):
            collected_segments.append(seg)

        def on_progress(pct, elapsed):
            progress_calls.append(pct)

        segs, info = transcriber.transcribe(
            audio_path=Path("audio.wav"),
            language="pt",
            beam_size=1,
            on_segment=on_segment,
            on_progress=on_progress,
        )

        self.assertEqual(len(segs), 2)
        self.assertEqual(segs[0].text, "Primeira fala transcrita.")
        self.assertEqual(segs[0].start, 0.0)
        self.assertEqual(segs[0].end, 2.5)
        self.assertEqual(segs[1].text, "Segunda fala transcrita.")
        self.assertEqual(segs[1].start, 2.5)
        self.assertEqual(segs[1].end, 5.1)

        self.assertEqual(len(collected_segments), 2)
        self.assertIn(25.0, progress_calls)
        self.assertIn(75.0, progress_calls)
        self.assertIn(100.0, progress_calls)
        self.assertEqual(info.language, "pt")
        self.assertEqual(info.duration, 5.1)


if __name__ == "__main__":
    unittest.main()
