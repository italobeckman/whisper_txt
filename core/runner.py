"""Orchestrator for the transcription pipeline (audio extraction -> transcription -> .txt)."""
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import config
from core.audio import (
    cleanup_temp_audio,
    extract_audio,
    is_audio_file,
    resolve_audio_source,
)
from core.transcriber import Transcriber, add_extension


def run_pipeline(
    input_path: Path,
    output_dir: Optional[Path] = None,
    quality: str = "fast",
    keep_audio: bool = False,
    overwrite: bool = False,
    initial_prompt: Optional[str] = None,
    language: Optional[str] = "pt",
    track_index: int = 0,
    on_segment: Optional[Callable[[Any], None]] = None,
    on_progress: Optional[Callable[[str, float, str], None]] = None,
    transcriber_instance: Optional[Transcriber] = None,
) -> Dict[str, Any]:
    """
    Executa a transcrição completa de um vídeo gerando .txt.
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {input_path}")

    out_dir = Path(output_dir) if output_dir else input_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    base_name = config.sanitize_filename(input_path.stem)
    base_out_path = out_dir / base_name

    txt_target = add_extension(base_out_path, "txt")

    result_info: Dict[str, Any] = {
        "input": input_path,
        "audio": None,
        "transcripts": [txt_target],
        "skipped": False,
    }

    if txt_target.exists() and not overwrite:
        result_info["skipped"] = True
        return result_info

    # 1. Obter áudio
    if on_progress:
        on_progress("audio", 0.0, "Resolvendo trilha de áudio...")

    temp_audio_path = None
    is_temp = False

    if is_audio_file(input_path):
        audio_target = input_path
    else:
        if keep_audio:
            suffix_name = f"{base_name}_t{track_index}" if track_index > 0 else base_name
            audio_target = add_extension(out_dir / suffix_name, "wav")
            success = extract_audio(input_path, audio_target, overwrite=overwrite, track_index=track_index)
            if not success:
                raise RuntimeError(f"Falha ao extrair áudio de {input_path}")
        else:
            audio_target, is_temp = resolve_audio_source(input_path, track_index=track_index)
            temp_audio_path = audio_target

    result_info["audio"] = audio_target

    try:
        # 2. Transcrição (Whisper)
        if on_progress:
            on_progress("transcribe", 10.0, f"Carregando modelo Whisper ({quality})...")

        transcriber = transcriber_instance or Transcriber(quality=quality)

        def segment_wrapper(seg):
            if on_segment:
                on_segment(seg)

        def progress_wrapper(pct, elapsed):
            if on_progress:
                on_progress("transcribe", 10.0 + (pct * 0.8), f"Transcrevendo... {pct:.1f}%")

        segments, _ = transcriber.transcribe(
            audio_path=audio_target,
            language=language,
            initial_prompt=initial_prompt,
            on_segment=segment_wrapper,
            on_progress=progress_wrapper,
        )

        txt_file = transcriber.export_txt(
            segments=segments,
            base_output_path=base_out_path,
            overwrite=overwrite,
        )
        result_info["transcripts"] = [txt_file]

        if on_progress:
            on_progress("done", 100.0, "Concluído com sucesso!")

    finally:
        if is_temp and temp_audio_path:
            cleanup_temp_audio(temp_audio_path)

    return result_info
