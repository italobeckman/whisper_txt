"""Configuração central do pipeline de transcrição de vídeos via Vulkan."""
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MODEL_FOLDER = BASE_DIR / "models"
BIN_FOLDER = BASE_DIR / "bin"

# Idioma padrão das gravações ("pt" = português)
LANGUAGE = "pt"

# Preset padrão: fast (large-v3-turbo q5_0, greedy decoding, 53s / 1h áudio)
DEFAULT_PRESET = "fast"

VULKAN_RELEASE_URL = "https://github.com/jerryshell/whisper.cpp-windows-vulkan-bin/releases/download/v1.0.0/whisper.cpp-windows-vulkan.zip"

MODEL_URLS = {
    "ggml-large-v3-turbo-q5_0.bin": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q5_0.bin",
    "ggml-large-v3-turbo.bin": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin",
    "ggml-base.bin": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin",
}


def find_ffmpeg() -> str:
    """Retorna o caminho do executável FFmpeg instalado diretamente pelo uv (imageio-ffmpeg)."""
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def get_whisper_cli() -> Path:
    """
    Localiza o binário whisper-cli com aceleração Vulkan.
    Se não estiver presente em bin/, baixa e descompacta automaticamente.
    """
    BIN_FOLDER.mkdir(parents=True, exist_ok=True)
    exe_name = "whisper-cli.exe" if sys.platform == "win32" else "whisper-cli"
    cli_path = BIN_FOLDER / exe_name

    if cli_path.exists():
        return cli_path

    # Tenta localizar no PATH do sistema
    system_cli = shutil.which("whisper-cli")
    if system_cli:
        return Path(system_cli)

    # Download automático do pacote Vulkan pré-compilado para Windows
    if sys.platform == "win32":
        print("[Whisper TXT] Baixando binário universal whisper-cli (Vulkan)...")
        zip_tmp = BIN_FOLDER / "whisper_vulkan.zip.tmp"
        zip_path = BIN_FOLDER / "whisper_vulkan.zip"
        try:
            urllib.request.urlretrieve(VULKAN_RELEASE_URL, zip_tmp)
            zip_tmp.replace(zip_path)
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(BIN_FOLDER)
        finally:
            if zip_tmp.exists():
                zip_tmp.unlink()
            if zip_path.exists():
                zip_path.unlink()

        if cli_path.exists():
            print("[Whisper TXT] Motor Vulkan instalado com sucesso em bin/.")
            return cli_path

    raise FileNotFoundError(
        f"Binário {exe_name} não encontrado em {BIN_FOLDER}. "
        "Certifique-se de que o whisper.cpp com Vulkan está presente."
    )


def get_model_path(model_filename: str) -> Path:
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

    print(f"\n[Whisper TXT] Baixando modelo {model_filename} do Hugging Face...")
    print(f"Origem: {url}")
    print(f"Destino: {model_path}")

    tmp_path = model_path.with_suffix(f"{model_path.suffix}.tmp")
    try:
        urllib.request.urlretrieve(url, tmp_path)
        tmp_path.replace(model_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    print(f"[Whisper TXT] Download concluído ({model_path.stat().st_size // (1024 * 1024)} MB).\n")
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
