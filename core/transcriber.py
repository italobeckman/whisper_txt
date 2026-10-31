"""Speech-to-text transcription engine using whisper.cpp with universal Vulkan GPU acceleration."""
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import config

PRESETS: Dict[str, Dict[str, Any]] = {
    "fast": {
        "model": "ggml-large-v3-turbo-q5_0.bin",
        "beam_size": 1,
        "description": "Ultra-rápido (large-v3-turbo q5_0, beam 1 - ~53s / 1h de áudio)",
    },
    "balanced": {
        "model": "ggml-large-v3-turbo-q5_0.bin",
        "beam_size": 5,
        "description": "Equilíbrio entre velocidade e precisão (large-v3-turbo q5_0, beam 5)",
    },
    "max": {
        "model": "ggml-large-v3-turbo.bin",
        "beam_size": 5,
        "description": "Máxima precisão (large-v3-turbo float16, beam 5)",
    },
}


def normalize_model_filename(name: Optional[str], default_filename: str) -> str:
    """Normaliza o nome do modelo para o formato de arquivo GGML/GGUF correspondente."""
    if not name:
        return default_filename
    clean_name = name.strip()
    if clean_name.startswith("ggml-") and clean_name.endswith(".bin"):
        return clean_name
    lower_name = clean_name.lower()
    if "turbo" in lower_name and "q5" in lower_name:
        return "ggml-large-v3-turbo-q5_0.bin"
    if "turbo" in lower_name:
        return "ggml-large-v3-turbo.bin"
    if "base" in lower_name:
        return "ggml-base.bin"
    if not clean_name.startswith("ggml-"):
        clean_name = f"ggml-{clean_name}"
    if not clean_name.endswith(".bin"):
        clean_name = f"{clean_name}.bin"
    return clean_name


def add_extension(base_path: Path, ext: str) -> Path:
    """Anexa uma extensão ao nome do arquivo sem truncar pontos existentes no nome base."""
    base = Path(base_path)
    clean_ext = ext.lstrip(".")
    return base.parent / f"{base.name}.{clean_ext}"


class Segment:
    """Representa um segmento de fala transcrito com timestamps e texto."""

    def __init__(self, start: float, end: float, text: str):
        self.start = float(start)
        self.end = float(end)
        self.text = text.strip()

    def __repr__(self) -> str:
        return f"Segment(start={self.start:.2f}, end={self.end:.2f}, text={self.text!r})"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Segment):
            return False
        return (
            abs(self.start - other.start) < 0.001
            and abs(self.end - other.end) < 0.001
            and self.text == other.text
        )


class TranscriptionInfo:
    """Metadados do áudio e da transcrição."""

    def __init__(self, language: str = "pt", duration: Optional[float] = None):
        self.language = language
        self.duration = duration


class Transcriber:
    """Motor de transcrição universal com aceleração gráfica Vulkan via whisper.cpp."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        download_root: Optional[str] = None,
        quality: str = "fast",
        threads: Optional[int] = None,
        **kwargs: Any,
    ):
        preset = PRESETS.get(quality.lower(), PRESETS[config.DEFAULT_PRESET])
        self.quality = quality.lower()
        default_model = preset["model"]
        self.model_filename = normalize_model_filename(model_name, default_model)
        self.beam_size = preset.get("beam_size", 1)
        self.device = device or config.DEVICE
        self.threads = threads or min(8, max(1, (os.cpu_count() or 4)))
        self.download_root = download_root or config.MODEL_FOLDER

    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = "pt",
        beam_size: Optional[int] = None,
        initial_prompt: Optional[str] = None,
        on_segment: Optional[Callable[[Segment], None]] = None,
        on_progress: Optional[Callable[[float, float], None]] = None,
        **kwargs: Any,
    ) -> Tuple[List[Segment], TranscriptionInfo]:
        """
        Executa a transcrição do áudio utilizando o binário whisper-cli com aceleração Vulkan.
        Transmite segmentos transcritos em tempo real para on_segment e progresso percentual para on_progress.
        """
        cli_path = config.get_whisper_cli()
        model_path = config.get_model_path(self.model_filename)
        beam = beam_size if beam_size is not None else self.beam_size
        lang = language or config.LANGUAGE

        cmd = [
            str(cli_path),
            "-m", str(model_path),
            "-f", str(audio_path),
            "-l", lang,
            "-t", str(self.threads),
            "-bs", str(beam),
            "-bo", str(beam),
            "-pp",
        ]
        if self.device and str(self.device).isdigit():
            cmd.extend(["-dev", str(self.device)])
        if initial_prompt:
            cmd.extend(["--prompt", initial_prompt])

        start_time = time.time()
        collected_segments: List[Segment] = []
        re_progress = re.compile(r"progress\s*=\s*(\d+)%")
        re_segment = re.compile(
            r"\[(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})\.(\d{3})\]\s*(.*)"
        )

        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )

        try:
            if process.stdout:
                for line in iter(process.stdout.readline, ""):
                    line_str = line.strip()
                    if not line_str:
                        continue

                    # Notifica progresso percentual
                    match_prog = re_progress.search(line_str)
                    if match_prog and on_progress:
                        pct = float(match_prog.group(1))
                        elapsed = time.time() - start_time
                        try:
                            on_progress(pct, elapsed)
                        except Exception:
                            pass

                    # Notifica segmento de fala transcrito
                    match_seg = re_segment.search(line_str)
                    if match_seg:
                        h1, m1, s1, ms1 = map(int, match_seg.groups()[0:4])
                        h2, m2, s2, ms2 = map(int, match_seg.groups()[4:8])
                        seg_start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000.0
                        seg_end = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000.0
                        seg_text = match_seg.group(9).strip()

                        if seg_text:
                            segment = Segment(start=seg_start, end=seg_end, text=seg_text)
                            collected_segments.append(segment)
                            if on_segment:
                                try:
                                    on_segment(segment)
                                except Exception:
                                    pass
        finally:
            if process.poll() is None:
                try:
                    process.kill()
                except Exception:
                    pass
            if process.stdout:
                try:
                    process.stdout.close()
                except Exception:
                    pass
            returncode = process.wait()

        if returncode != 0:
            raise RuntimeError(f"whisper-cli falhou com código de saída {returncode}")

        total_duration = collected_segments[-1].end if collected_segments else 0.0
        info = TranscriptionInfo(language=lang, duration=total_duration)
        return collected_segments, info

    def export_txt(
        self,
        segments: List[Segment],
        base_output_path: Path,
        overwrite: bool = False,
    ) -> Path:
        """Exporta as falas transcritas exclusivamente em arquivo .txt."""
        base_path = Path(base_output_path)
        base_path.parent.mkdir(parents=True, exist_ok=True)
        txt_path = add_extension(base_path, "txt")

        if overwrite or not txt_path.exists():
            with open(txt_path, "w", encoding="utf-8") as f:
                for seg in segments:
                    text = seg.text.strip()
                    if text:
                        f.write(text + "\n")
        return txt_path
