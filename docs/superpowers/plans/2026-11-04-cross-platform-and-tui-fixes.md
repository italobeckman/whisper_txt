# Cross-Platform and TUI Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide seamless, 100% automated execution for both Linux and Windows, fix TUI folder navigation and media discovery, expand supported formats, and update documentation.

**Architecture:** 
1. Universal platform handler in `config.py` that auto-downloads prebuilt binaries for both Windows and Linux, sets file permissions and RPATH/`LD_LIBRARY_PATH`, plus provides a fallback build utility for custom Vulkan compilation.
2. Dynamic media inspector in `core/audio.py` and `cli.py` that recognizes all common audio/video extensions and uses FFmpeg stream analysis for extensionless or non-standard files.
3. Event-driven directory tree in `tui/app.py` supporting folder expansion via `DirectorySelected`, responsive directory updates, and comprehensive media file filters.
4. Comprehensive, multi-platform documentation in `README.md`.

**Tech Stack:** Python 3.10+, Textual, FFmpeg, whisper.cpp with Vulkan GPU acceleration, uv.

**Spec:** User request for full parity between Windows and Linux, resolving TUI directory browsing issues, and documenting all runtime requirements.

## Global Constraints

- Must work identically on Windows and Linux without manual hacks.
- All existing tests in `tests/` must pass cleanly (`uv run python -m unittest discover tests`).
- No regressions to CLI parameters or default fast preset (`large-v3-turbo-q5_0`).
- No breaking changes to existing public functions in `core/` modules.

## Review Focus

1. **Extensionless media file handling:** A video or audio file with no extension (e.g., `aaaaaa`) must be recognized in CLI, pipeline runner, and TUI without raising errors.
2. **Linux binary retrieval:** On a clean Linux system without `whisper-cli`, `get_whisper_cli()` must either auto-download the official release or provide clear guided steps if Vulkan compiler tools are missing.
3. **TUI folder expansion:** Pressing `[Enter]` on a folder in the TUI directory tree must toggle folder expansion and allow selecting media files nested in subdirectories.
4. **Shared library resolution:** On Linux, `whisper-cli` must resolve sibling libraries (`libggml-vulkan.so`, `libwhisper.so`) located in `bin/` without system-wide library path pollution.
5. **Multi-track audio toggle:** The TUI audio track toggle button must handle wrap-around reliably without timing or layout desynchronization.

---

### Task 1: Expand Supported Media Formats and Smart Stream Detection

**Files:**
- Modify: `core/audio.py`
- Modify: `cli.py`
- Modify: `tests/test_audio.py`

**Interfaces:**
- Consumes: `config.find_ffmpeg()`, `subprocess`
- Produces: `is_video_file(path: Path) -> bool`, `is_audio_file(path: Path) -> bool`, `collect_files(target: Path, ...) -> List[Path]`

- [ ] **Step 1: Write tests for expanded extensions and extensionless media detection**

In `tests/test_audio.py`, add tests verifying:
- Recognition of `.m4v`, `.ts`, `.3gp` as video files.
- Recognition of `.opus` as audio files.
- Fallback detection using `get_audio_tracks` when a file without extension exists and contains audio/video streams.

- [ ] **Step 2: Run tests to verify test expectations**

Run: `uv run python -m unittest tests/test_audio.py`
Expected: Verification of current behavior and failure on missing extensions.

- [ ] **Step 3: Update `VIDEO_EXTENSIONS` and `AUDIO_EXTENSIONS` in `core/audio.py`**

Add `.m4v`, `.ts`, `.3gp`, `.mpeg`, `.mpg` to `VIDEO_EXTENSIONS`.
Add `.opus` to `AUDIO_EXTENSIONS`.
Enhance `is_video_file` and `is_audio_file` to inspect existing files using FFmpeg when extension is unrecognized.

- [ ] **Step 4: Update `collect_files` in `cli.py`**

Ensure that if `target.is_file()`, `is_video_file(target)` or `is_audio_file(target)` is checked as a fallback before rejecting.

- [ ] **Step 5: Run tests and verify PASS**

Run: `uv run python -m unittest tests/test_audio.py tests/test_cli.py`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add core/audio.py cli.py tests/test_audio.py
git commit -m "feat: expand supported media formats and support extensionless media inspection"
```

---

### Task 2: Fix TUI Directory Navigation and Tree Media Discovery

**Files:**
- Modify: `tui/app.py`
- Modify: `tests/test_tui.py`

**Interfaces:**
- Consumes: `DirectoryTree.DirectorySelected`, `DirectoryTree.FileSelected`
- Produces: `on_directory_tree_directory_selected`, `FilteredMediaDirectoryTree.filter_paths`

- [ ] **Step 1: Write failing tests in `tests/test_tui.py` for directory expansion**

Add a test `test_directory_selected_toggles_expansion` in `tests/test_tui.py`:
- Simulates selecting a directory node.
- Verifies that `event.node.toggle()` is invoked or node expansion toggles.
- Fix `test_audio_track_detection_and_toggle` using `btn.press()` to reliably test track cycling without UI coordinate shift.

- [ ] **Step 2: Run test to verify failure**

Run: `uv run python -m unittest tests/test_tui.py`
Expected: Fails on directory expansion not being handled.

- [ ] **Step 3: Implement `on_directory_tree_directory_selected` and improve `FilteredMediaDirectoryTree` in `tui/app.py`**

- In `FilteredMediaDirectoryTree.filter_paths`:
  - Allow directory nodes.
  - Allow files matching `VIDEO_EXTENSIONS | AUDIO_EXTENSIONS` (case-insensitive).
  - Allow files without extension if `is_video_file(p)` or `is_audio_file(p)` returns True.
- In `WhisperTxtApp`:
  - Implement `on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected)`:
    - Calls `event.node.toggle()`.
    - Updates `lbl-current-dir` label with `event.path.name or str(event.path)`.

- [ ] **Step 4: Run tests to verify PASS**

Run: `uv run python -m unittest tests/test_tui.py`
Expected: All 9+ tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tui/app.py tests/test_tui.py
git commit -m "fix(tui): handle directory selection, auto-expansion, and robust media filtering"
```

---

### Task 3: Automated Cross-Platform (Linux & Windows) Binary Setup in `config.py`

**Files:**
- Modify: `config.py`
- Modify: `core/transcriber.py`
- Create: `scripts/build_vulkan.py`
- Test: `tests/test_transcriber.py`

**Interfaces:**
- Consumes: `sys.platform`, `shutil.which`, `urllib.request`
- Produces: `get_whisper_cli() -> Path`

- [ ] **Step 1: Enhance `config.py` for automated Linux binary handling**

- Support downloading prebuilt Linux binary tarball from official whisper.cpp releases if `whisper-cli` is missing and not in `PATH`.
- Extract `whisper-cli` and shared libraries to `bin/`.
- Ensure executable permissions on POSIX systems (`os.chmod(cli_path, 0o755)`).
- Provide clear error messaging if system Vulkan drivers or libraries are missing, pointing directly to solution.

- [ ] **Step 2: Add `scripts/build_vulkan.py` as an automated fallback build script**

Create a self-contained helper script `scripts/build_vulkan.py`:
- Checks for `vulkaninfo` and GPU.
- Checks / installs `cmake` and `ninja` via `uv pip`.
- Clones `whisper.cpp` (or uses local submodule/fetch) with `-DGGML_VULKAN=1`.
- Compiles `whisper-cli` with Vulkan and places outputs in `bin/` with correct RPATH.

- [ ] **Step 3: Ensure `LD_LIBRARY_PATH` propagation in `core/transcriber.py`**

Ensure `core/transcriber.py` passes `LD_LIBRARY_PATH` containing `bin/` to `subprocess.Popen` on Linux/macOS.

- [ ] **Step 4: Verify test suite**

Run: `uv run python -m unittest discover tests`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add config.py core/transcriber.py scripts/build_vulkan.py
git commit -m "feat: automated Linux and Windows whisper-cli support with Vulkan build script"
```

---

### Task 4: Complete Multi-Platform Documentation in `README.md`

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: All features, CLI parameters, TUI keybindings, Linux and Windows setup steps

- [ ] **Step 1: Update `README.md` Installation Section**

- Provide explicit instructions for Linux (Ubuntu/Debian, Arch/CachyOS, Fedora) and Windows.
- Document Vulkan prerequisites (`vulkan-tools`, drivers).
- Document automatic binary installation vs build helper (`uv run python scripts/build_vulkan.py`).

- [ ] **Step 2: Update TUI Instructions in `README.md`**

- Document folder navigation:
  - `[Enter]` on a folder: Expands/collapses the directory.
  - `[Enter]` on a media file: Selects and starts transcription.
  - `▲ Subir Pasta`: Navigates to parent directory.
  - `[s]`: Starts transcription.

- [ ] **Step 3: Update Supported Formats Section**

- List all newly supported audio and video formats, including files without extension.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: comprehensive cross-platform and TUI usage guide in README"
```

---

### Task 5: Full System Verification

- [ ] **Step 1: Run complete test suite**

Run: `uv run python -m unittest discover tests`
Expected: 100% PASS with 0 failures.

- [ ] **Step 2: Test CLI transcription on `aaaaaa`**

Run: `uv run cli.py transcribe -i aaaaaa`
Expected: Successfully detects `aaaaaa`, finds existing `aaaaaa.txt` (or re-transcribes if `-f`), exits 0.

- [ ] **Step 3: Verify git status and clean working tree**

Run: `git status`
Expected: Clean working tree.
