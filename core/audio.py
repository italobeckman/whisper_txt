"""Audio extraction and format handling utilities using FFmpeg."""
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import config

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".mov", ".webm", ".avi", ".flv", ".wmv",
    ".m4v", ".ts", ".3gp", ".mpeg", ".mpg",
}
AUDIO_EXTENSIONS = {
    ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".wma", ".opus",
}


def is_video_file(path: Path) -> bool:
    """Retorna True se o arquivo tiver extensão de vídeo suportada."""
    p = Path(path)
    if p.suffix.lower() in VIDEO_EXTENSIONS:
        return True
    if p.is_file() and not p.suffix:
        tracks = get_audio_tracks(p)
        if tracks:
            return True
    return False


def is_audio_file(path: Path) -> bool:
    """Retorna True se o arquivo tiver extensão de áudio suportada."""
    return Path(path).suffix.lower() in AUDIO_EXTENSIONS


def get_audio_tracks(video_path: Path, ffmpeg_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Inspeciona o arquivo de vídeo e retorna a lista de trilhas/streams de áudio encontradas.
    Retorna lista de dicionários com: index, stream_id, language, description.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        return []

    ffmpeg = ffmpeg_path or config.find_ffmpeg()
    cmd = [ffmpeg, "-i", str(video_path)]
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            creationflags=creationflags,
        )
        output = res.stderr or ""
    except Exception:
        return []

    tracks: List[Dict[str, Any]] = []
    # Padrão: Stream #0:1[0x2](por): Audio: aac (LC)... ou Stream #0:1: Audio: aac...
    pattern = re.compile(r"Stream #(\d+:\d+)(?:\[.*?\])?(?:\((.*?)\))?:\s*Audio:\s*(.*)")

    audio_idx = 0
    for line in output.splitlines():
        match = pattern.search(line)
        if match:
            stream_id = match.group(1)
            language = match.group(2) or "und"
            description = match.group(3).strip()
            tracks.append({
                "index": audio_idx,
                "stream_id": stream_id,
                "language": language,
                "codec": description.split()[0] if description else "audio",
                "description": description,
            })
            audio_idx += 1

    return tracks


def extract_audio(
    video_path: Path,
    audio_path: Path,
    ffmpeg_path: Optional[str] = None,
    overwrite: bool = False,
    track_index: int = 0,
) -> bool:
    """
    Extrai a trilha de áudio especificada de um vídeo para WAV mono 16kHz PCM.
    Se o arquivo de saída já existir e overwrite for False, pula a extração.
    """
    video_path = Path(video_path)
    audio_path = Path(audio_path)

    if audio_path.exists() and not overwrite:
        return True

    audio_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = ffmpeg_path or config.find_ffmpeg()

    cmd = [
        ffmpeg,
        "-y",
        "-i", str(video_path),
        "-map", f"0:a:{track_index}",
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        str(audio_path),
    ]

    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            creationflags=creationflags,
        )
        if result.returncode != 0:
            err_msg = result.stderr.strip() if result.stderr else f"Código de saída {result.returncode}"
            print(f"[ERRO FFmpeg] {err_msg}", file=sys.stderr)
            return False
        return True
    except Exception as e:
        print(f"[ERRO] Falha ao executar FFmpeg: {e}", file=sys.stderr)
        return False


def resolve_audio_source(
    input_path: Path,
    temp_dir: Optional[Path] = None,
    ffmpeg_path: Optional[str] = None,
    track_index: int = 0,
) -> Tuple[Path, bool]:
    """
    Garante que o arquivo de entrada seja um áudio válido para o Whisper.
    - Se for um arquivo de áudio, retorna (input_path, False).
    - Se for um arquivo de vídeo, extrai a trilha solicitada para um arquivo
      temporário WAV 16kHz e retorna (temp_audio_path, True).
    """
    input_path = Path(input_path)

    if is_audio_file(input_path):
        return input_path, False

    if is_video_file(input_path):
        prefix = f"whisper_txt_{config.sanitize_filename(input_path.stem)}_t{track_index}_"
        temp_file = tempfile.NamedTemporaryFile(
            prefix=prefix,
            suffix=".wav",
            dir=str(temp_dir) if temp_dir else None,
            delete=False,
        )
        temp_audio_path = Path(temp_file.name)
        temp_file.close()

        success = extract_audio(
            input_path,
            temp_audio_path,
            ffmpeg_path=ffmpeg_path,
            overwrite=True,
            track_index=track_index,
        )
        if not success:
            cleanup_temp_audio(temp_audio_path)
            raise RuntimeError(f"Falha ao extrair áudio de {input_path}")
        return temp_audio_path, True

    raise ValueError(f"Formato não suportado para transcrição: {input_path.suffix}")


def cleanup_temp_audio(audio_path: Optional[Path]) -> None:
    """Remove o arquivo temporário de áudio com segurança."""
    if audio_path is None:
        return
    try:
        path = Path(audio_path)
        if path.exists():
            path.unlink()
    except Exception as e:
        print(f"[AVISO] Não foi possível remover arquivo temporário {audio_path}: {e}", file=sys.stderr)
