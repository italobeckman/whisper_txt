"""Audio extraction and format handling utilities using FFmpeg."""
import logging
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import config

logger = logging.getLogger(__name__)

# Quantidade de linhas do stderr do FFmpeg preservada nas mensagens de erro.
FFMPEG_ERROR_TAIL_LINES = 5

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".mov", ".webm", ".avi", ".flv", ".wmv",
    ".m4v", ".ts", ".3gp", ".mpeg", ".mpg",
}
AUDIO_EXTENSIONS = {
    ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".wma", ".opus",
}
# Formatos que o whisper-cli consegue ler diretamente (miniaudio/dr_libs)
WHISPER_NATIVE_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg"}


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


def is_native_audio_file(path: Path) -> bool:
    """Retorna True se o whisper-cli lê o arquivo diretamente (sem conversão)."""
    return Path(path).suffix.lower() in WHISPER_NATIVE_EXTENSIONS


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


class FFmpegError(RuntimeError):
    """Falha ao extrair áudio com o FFmpeg, com a causa reportada pelo processo."""


def _format_ffmpeg_error(stderr: Optional[str], returncode: int) -> str:
    """Resume a falha do FFmpeg preservando as últimas linhas do stderr."""
    lines = [line.strip() for line in (stderr or "").splitlines() if line.strip()]
    if not lines:
        return f"FFmpeg retornou código {returncode}"
    tail = "\n".join(lines[-FFMPEG_ERROR_TAIL_LINES:])
    return f"FFmpeg retornou código {returncode}:\n{tail}"


def extract_audio(
    video_path: Path,
    audio_path: Path,
    ffmpeg_path: Optional[str] = None,
    overwrite: bool = False,
    track_index: int = 0,
    raise_on_error: bool = False,
) -> bool:
    """
    Extrai a trilha de áudio especificada de um vídeo para WAV mono 16kHz PCM.
    Se o arquivo de saída já existir e overwrite for False, pula a extração.

    Retorna False em caso de falha. Com ``raise_on_error=True``, levanta
    :class:`FFmpegError` carregando a causa reportada pelo FFmpeg, para que
    chamadores possam propagá-la sem escrever no terminal.
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
            error = _format_ffmpeg_error(result.stderr, result.returncode)
            if raise_on_error:
                raise FFmpegError(error)
            return False
        return True
    except FFmpegError:
        raise
    except Exception as e:
        if raise_on_error:
            raise FFmpegError(f"Falha ao executar FFmpeg: {e}") from e
        return False


def resolve_audio_source(
    input_path: Path,
    temp_dir: Optional[Path] = None,
    ffmpeg_path: Optional[str] = None,
    track_index: int = 0,
) -> Tuple[Path, bool]:
    """
    Garante que o arquivo de entrada seja um áudio válido para o Whisper.
    - Se for um áudio em formato nativo do whisper-cli, retorna (input_path, False).
    - Se for um vídeo ou áudio não nativo (m4a, aac, opus...), extrai/converte a trilha solicitada para um arquivo
      temporário WAV 16kHz e retorna (temp_audio_path, True).
    """
    input_path = Path(input_path)

    if is_native_audio_file(input_path):
        return input_path, False

    if is_audio_file(input_path) or is_video_file(input_path):
        prefix = f"whisper_txt_{config.sanitize_filename(input_path.stem)}_t{track_index}_"
        temp_file = tempfile.NamedTemporaryFile(
            prefix=prefix,
            suffix=".wav",
            dir=str(temp_dir) if temp_dir else None,
            delete=False,
        )
        temp_audio_path = Path(temp_file.name)
        temp_file.close()

        try:
            extract_audio(
                input_path,
                temp_audio_path,
                ffmpeg_path=ffmpeg_path,
                overwrite=True,
                track_index=track_index,
                raise_on_error=True,
            )
        except FFmpegError as e:
            cleanup_temp_audio(temp_audio_path)
            raise RuntimeError(f"Falha ao extrair áudio de {input_path}: {e}") from e
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
        logger.warning("Não foi possível remover arquivo temporário %s: %s", audio_path, e)
