import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from tui.app import WhisperTxtApp
from textual.widgets import Header, Footer, ProgressBar, RadioSet, Button, Input, RichLog, DirectoryTree, Label


class TestWhisperTxtTUI(unittest.IsolatedAsyncioTestCase):
    async def test_app_layout_and_initial_state(self):
        app = WhisperTxtApp()
        async with app.run_test():
            self.assertEqual(app.title, "Whisper TXT")

            # Check widgets exist
            header = app.query_one(Header)
            footer = app.query_one(Footer)
            progress_bar = app.query_one(ProgressBar)
            radio_set = app.query_one("#quality-radios", RadioSet)
            btn_start = app.query_one("#btn-start", Button)
            prompt_input = app.query_one("#input-prompt", Input)
            transcript_log = app.query_one("#log-transcript", RichLog)

            self.assertIsNotNone(header)
            self.assertIsNotNone(footer)
            self.assertIsNotNone(progress_bar)
            self.assertIsNotNone(radio_set)
            self.assertIsNotNone(btn_start)
            self.assertIsNotNone(prompt_input)
            self.assertIsNotNone(transcript_log)

            # Check default preset is fast
            self.assertEqual(app.selected_quality, "fast")
            self.assertEqual(app.selected_language, "pt")
            self.assertEqual(app.selected_track, 0)

            lang_selector = app.query_one("#radio-language", RadioSet)
            self.assertIsNotNone(lang_selector)

    async def test_language_selection_changes_property(self):
        app = WhisperTxtApp()
        async with app.run_test() as pilot:
            # Click english radio button
            await pilot.click("#lang-en")
            await pilot.pause()
            self.assertEqual(app.selected_language, "en")

    @patch("tui.app.get_audio_tracks")
    async def test_audio_track_detection_and_toggle(self, mock_tracks):
        mock_tracks.return_value = [
            {"index": 0, "codec": "aac", "language": "por"},
            {"index": 1, "codec": "aac", "language": "eng"},
        ]
        app = WhisperTxtApp()
        async with app.run_test() as pilot:
            tree = app.query_one("#file-tree")
            # Simulate file selected
            event = DirectoryTree.FileSelected(tree, Path("test_recording.mp4"))
            app.on_directory_tree_file_selected(event)
            await pilot.pause()

            btn_toggle = app.query_one("#btn-toggle-track", Button)
            self.assertFalse(btn_toggle.disabled)
            self.assertEqual(app.selected_track, 0)

            # Press toggle track button
            btn_toggle.press()
            await pilot.pause()
            self.assertEqual(app.selected_track, 1)

            # Press toggle track button again to wrap around
            btn_toggle.press()
            await pilot.pause()
            self.assertEqual(app.selected_track, 0)

    async def test_directory_selected_toggles_expansion(self):
        app = WhisperTxtApp()
        async with app.run_test() as pilot:
            tree = app.query_one("#file-tree")
            mock_node = MagicMock()
            event = DirectoryTree.DirectorySelected(mock_node, Path("/fake/pasta_teste"))
            app.on_directory_tree_directory_selected(event)
            await pilot.pause()

            mock_node.toggle.assert_called_once()
            lbl_dir = app.query_one("#lbl-current-dir", Label)
            self.assertIn("pasta_teste", str(lbl_dir.render()))

    @patch("tui.app.get_audio_tracks")
    async def test_single_track_disables_toggle(self, mock_tracks):
        mock_tracks.return_value = [{"index": 0, "codec": "aac", "language": "por"}]
        app = WhisperTxtApp()
        async with app.run_test() as pilot:
            tree = app.query_one("#file-tree")
            event = DirectoryTree.FileSelected(tree, Path("single_track.mp4"))
            app.on_directory_tree_file_selected(event)
            await pilot.pause()

            btn_toggle = app.query_one("#btn-toggle-track", Button)
            self.assertTrue(btn_toggle.disabled)
            self.assertEqual(app.selected_track, 0)

    @patch.object(WhisperTxtApp, "run_transcription_worker")
    async def test_start_transcription_passes_language_and_track(self, mock_worker):
        app = WhisperTxtApp()
        async with app.run_test() as pilot:
            # Mock a file that exists or mock is_file
            fake_path = MagicMock(spec=Path)
            fake_path.is_file.return_value = True
            fake_path.name = "dummy.mp4"
            app.selected_file = fake_path
            app.selected_language = "es"
            app.selected_track = 1
            app.start_transcription()
            await pilot.pause()

            mock_worker.assert_called_once_with(
                fake_path,
                "fast",
                "es",
                1,
                None,
            )

    @patch.object(WhisperTxtApp, "start_transcription")
    async def test_keyboard_shortcut_s_triggers_start(self, mock_start):
        app = WhisperTxtApp()
        async with app.run_test() as pilot:
            await pilot.press("s")
            await pilot.pause()
            mock_start.assert_called_once()

    @patch.object(WhisperTxtApp, "start_transcription")
    async def test_reselecting_same_file_triggers_start(self, mock_start):
        app = WhisperTxtApp()
        async with app.run_test() as pilot:
            tree = app.query_one("#file-tree")
            test_file = Path("test_video.mp4")
            event = DirectoryTree.FileSelected(tree, test_file)

            # First selection: defines selected_file
            app.on_directory_tree_file_selected(event)
            await pilot.pause()
            mock_start.assert_not_called()
            self.assertEqual(app.selected_file, test_file)

            # Second selection (pressing Enter on same file): triggers start_transcription!
            app.on_directory_tree_file_selected(event)
            await pilot.pause()
            mock_start.assert_called_once()

    @patch.object(WhisperTxtApp, "start_transcription")
    async def test_input_prompt_submitted_triggers_start(self, mock_start):
        app = WhisperTxtApp()
        async with app.run_test() as pilot:
            inp = app.query_one("#input-prompt", Input)
            inp.value = "Alguma sigla"
            app.on_input_submitted(Input.Submitted(inp, inp.value))
            await pilot.pause()
            mock_start.assert_called_once()

    async def test_btn_dir_up_navigates_to_parent(self):
        start_dir = Path.cwd().resolve()
        app = WhisperTxtApp(initial_path=start_dir)
        async with app.run_test() as pilot:
            tree = app.query_one("#file-tree")
            self.assertEqual(Path(tree.path).resolve(), start_dir)

            # Click btn-dir-up
            await pilot.click("#btn-dir-up")
            await pilot.pause()

            self.assertEqual(Path(tree.path).resolve(), start_dir.parent)


if __name__ == "__main__":
    unittest.main()

