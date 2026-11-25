"""Configuração central do pipeline de transcrição de vídeos via Vulkan."""
import http.client
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

BASE_DIR = Path(__file__).resolve().parent
MODEL_FOLDER = BASE_DIR / "models"
BIN_FOLDER = BASE_DIR / "bin"

# Idioma padrão das gravações ("pt" = português)
LANGUAGE = "pt"

# Preset padrão: fast (large-v3-turbo q5_0, greedy decoding, 53s / 1h áudio)
DEFAULT_PRESET = "fast"

DOWNLOAD_TIMEOUT = 30
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
DownloadProgress = Callable[[int, int | None], None]

VULKAN_RELEASE_URL = "https://github.com/jerryshell/whisper.cpp-windows-vulkan-bin/releases/download/v1.0.0/whisper.cpp-windows-vulkan.zip"
LINUX_RELEASE_URL = "https://github.com/ggml-org/whisper.cpp/releases/download/b5454/whisper-bin-ubuntu-x64.tar.gz"

MODEL_URLS = {
    "ggml-large-v3-turbo-q5_0.bin": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q5_0.bin",
    "ggml-large-v3-turbo.bin": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin",
    "ggml-base.bin": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin",
}


def find_ffmpeg() -> str:
    """Retorna o caminho do executável FFmpeg instalado diretamente pelo uv (imageio-ffmpeg)."""
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _download_file(
    url: str,
    destination: Path,
    on_progress: DownloadProgress | None = None,
    timeout: float = DOWNLOAD_TIMEOUT,
) -> None:
    """Publica o arquivo após verificar o tamanho, se informado pelo servidor.

    O callback recebe bytes baixados e o total (None quando desconhecido).
    """
    request = urllib.request.Request(url, headers={"User-Agent": "whisper-txt/1.0"})
    temp_path = None
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_length = response.headers.get("Content-Length")
            total = int(content_length) if content_length is not None else None
            if total is not None and total < 0:
                raise ValueError(f"Content-Length inválido: {content_length}")

            downloaded = 0
            if on_progress:
                on_progress(downloaded, total)
            with tempfile.NamedTemporaryFile(
                dir=destination.parent, prefix=f"{destination.name}.", suffix=".tmp", delete=False,
            ) as output:
                temp_path = Path(output.name)
                while chunk := response.read(DOWNLOAD_CHUNK_SIZE):
                    downloaded += len(chunk)
                    if total is not None and downloaded > total:
                        break
                    output.write(chunk)
                    if on_progress:
                        on_progress(downloaded, total)

        if total is not None and downloaded != total:
            raise ValueError(f"Content-Length de {total} bytes, recebidos {downloaded} bytes")
        temp_path.replace(destination)
    except (OSError, http.client.HTTPException, ValueError) as error:
        cause = error.reason if isinstance(error, urllib.error.URLError) else error
        detail = f"tempo limite de {timeout:g} s excedido" if isinstance(cause, TimeoutError) else str(error)
        raise RuntimeError(f"Falha ao baixar {destination.name}: {detail}") from error
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def get_whisper_cli(on_progress: DownloadProgress | None = None) -> Path:
    """
    Localiza o binário whisper-cli com aceleração Vulkan.
    Se não estiver presente em bin/, baixa e descompacta automaticamente.
    """
    BIN_FOLDER.mkdir(parents=True, exist_ok=True)
    exe_name = "whisper-cli.exe" if sys.platform == "win32" else "whisper-cli"
    cli_path = BIN_FOLDER / exe_name

    if cli_path.exists():
        if sys.platform != "win32" and not os.access(cli_path, os.X_OK):
            os.chmod(cli_path, 0o755)
        return cli_path

    # Tenta localizar no PATH do sistema
    system_cli = shutil.which("whisper-cli")
    if system_cli:
        return Path(system_cli)

    # Download automático do pacote Vulkan pré-compilado para Windows
    if sys.platform == "win32":
        with tempfile.TemporaryDirectory(dir=BIN_FOLDER) as download_dir:
            zip_path = Path(download_dir) / "whisper_vulkan.zip"
            _download_file(VULKAN_RELEASE_URL, zip_path, on_progress)
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(BIN_FOLDER)

        if cli_path.exists():
            return cli_path

    # Download automático para Linux
    if sys.platform.startswith("linux"):
        with tempfile.TemporaryDirectory(dir=BIN_FOLDER) as download_dir:
            tar_path = Path(download_dir) / "whisper_linux.tar.gz"
            _download_file(LINUX_RELEASE_URL, tar_path, on_progress)
            extract_options = {"filter": "data"} if getattr(tarfile, "data_filter", None) else {}
            with tarfile.open(tar_path, "r:gz") as tar_ref:
                for member in tar_ref.getmembers():
                    if member.isreg() or member.issym():
                        parts = Path(member.name).parts
                        member.name = parts[-1] if len(parts) > 1 else member.name
                        tar_ref.extract(member, BIN_FOLDER, **extract_options)

        if cli_path.exists():
            os.chmod(cli_path, 0o755)
            for lib_file in BIN_FOLDER.glob("*.so*"):
                try:
                    os.chmod(lib_file, 0o755)
                except Exception:
                    pass
            return cli_path

    raise FileNotFoundError(
        f"Binário {exe_name} não encontrado em {BIN_FOLDER}.\n"
        "Para compilar com suporte acelerado a Vulkan no Linux, execute:\n"
        "    uv run python scripts/build_vulkan.py\n"
        "Ou coloque o executável whisper-cli manualmente em bin/ ou no PATH do sistema."
    )


def get_model_path(model_filename: str, on_progress: DownloadProgress | None = None) -> Path:
    """
    Retorna o caminho do modelo GGUF/bin.
    Se não existir em models/, baixa automaticamente do repositório oficial da Hugging Face.
    """
    MODEL_FOLDER.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_FOLDER / model_filename

    if model_path.exists():
        return model_path

    url = MODEL_URLS.get(model_filename)
    if not url:
        # Se for nome customizado, tenta baixar diretamente do Hugging Face whisper.cpp
        url = f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{model_filename}"

    _download_file(url, model_path, on_progress)
    return model_path


def detect_device_name() -> str:
    """Detecta e retorna o nome da GPU Vulkan ativa."""
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        res = subprocess.run(
            ["vulkaninfo", "--summary"],
            capture_output=True,
            text=True,
            creationflags=creationflags,
        )
        for line in res.stdout.splitlines():
            if "deviceName" in line:
                return line.split("=")[-1].strip()
    except Exception:
        pass
    return "Vulkan (GPU Universal)"


DEVICE = detect_device_name()


def sanitize_filename(name: str) -> str:
    """Remove caracteres inválidos de nomes de arquivo."""
    for ch in r'<>:"/\|?*':
        name = name.replace(ch, "_")
    return name.strip()
