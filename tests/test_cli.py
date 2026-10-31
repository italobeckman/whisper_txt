import unittest
from cli import build_parser


class TestCLIParser(unittest.TestCase):
    def setUp(self):
        self.parser = build_parser()

    def test_transcribe_defaults(self):
        args = self.parser.parse_args(["transcribe", "-i", "aula.mp4"])
        self.assertEqual(args.command, "transcribe")
        self.assertEqual(args.input, "aula.mp4")
        self.assertEqual(args.quality, "fast")
        self.assertIsNone(args.output)
        self.assertFalse(args.overwrite)
        self.assertEqual(args.language, "pt")

    def test_transcribe_custom_flags(self):
        args = self.parser.parse_args([
            "transcribe",
            "-i", "aula.mp4",
            "-o", "out_dir",
            "-q", "fast",
            "-l", "en",
            "-t", "1",
            "--prompt", "Machine Learning, PyTorch",
            "--overwrite",
        ])
        self.assertEqual(args.quality, "fast")
        self.assertEqual(args.language, "en")
        self.assertEqual(args.track, 1)
        self.assertEqual(args.output, "out_dir")
        self.assertTrue(args.overwrite)
        self.assertEqual(args.prompt, "Machine Learning, PyTorch")

    def test_extract_flags(self):
        args = self.parser.parse_args(["extract", "-i", "video.mp4", "-o", "audio.wav", "-f"])
        self.assertEqual(args.command, "extract")
        self.assertEqual(args.input, "video.mp4")
        self.assertEqual(args.output, "audio.wav")
        self.assertTrue(args.overwrite)

    def test_run_flags(self):
        args = self.parser.parse_args([
            "run",
            "-i", "video.mp4",
            "-q", "balanced",
            "--keep-audio",
        ])
        self.assertEqual(args.command, "run")
        self.assertEqual(args.quality, "balanced")
        self.assertTrue(args.keep_audio)

    def test_tui_subcommand(self):
        args = self.parser.parse_args(["tui"])
        self.assertEqual(args.command, "tui")


if __name__ == "__main__":
    unittest.main()
