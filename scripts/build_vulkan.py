#!/usr/bin/env python3
"""
scripts/build_vulkan.py - Compilador automatizado do whisper.cpp com aceleração Vulkan.
Gera o binário whisper-cli e bibliotecas compartilhadas diretamente em bin/.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT_DIR / "bin"


def run_cmd(cmd, cwd=None, env=None, check=True):
    print(f"-> {' '.join(str(c) for c in cmd)}")
    res = subprocess.run(cmd, cwd=cwd, env=env)
    if check and res.returncode != 0:
        raise RuntimeError(f"Comando falhou com código {res.returncode}: {' '.join(str(c) for c in cmd)}")
    return res.returncode


def ensure_tools():
    """Garante que cmake e ninja estejam disponíveis no ambiente uv/pip."""
    print("[1/5] Verificando ferramentas de compilação (cmake, ninja)...")
    missing = []
    if not shutil.which("cmake"):
        missing.append("cmake")
    if not shutil.which("ninja"):
        missing.append("ninja")

    if missing:
        print(f"Instalando ferramentas ausentes ({', '.join(missing)})...")
        uv_bin = shutil.which("uv")
        if uv_bin:
            subprocess.run([uv_bin, "pip", "install", *missing], check=False)
        else:
            subprocess.run([sys.executable, "-m", "pip", "install", *missing], check=False)


def check_vulkan():
    """Verifica se há drivers Vulkan detectáveis."""
    print("[2/5] Verificando suporte a GPU Vulkan...")
    try:
        res = subprocess.run(["vulkaninfo", "--summary"], capture_output=True, text=True)
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                if "deviceName" in line:
                    print(f"    Dispositivo detectado: {line.split('=')[-1].strip()}")
                    return True
    except FileNotFoundError:
        pass

    print("[AVISO] vulkaninfo não foi encontrado ou não listou GPUs. Continuando compilação...")
    return False


def build_whisper_vulkan():
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    ensure_tools()
    check_vulkan()

    cmake_bin = shutil.which("cmake") or "cmake"
    ninja_bin = shutil.which("ninja")

    with tempfile.TemporaryDirectory(prefix="whisper_build_") as tmpdir:
        build_root = Path(tmpdir)
        src_dir = build_root / "whisper.cpp"
        vulkan_headers_dir = build_root / "Vulkan-Headers"
        spirv_headers_dir = build_root / "SPIRV-Headers"
        prefix_dir = build_root / "local_prefix"
        prefix_dir.mkdir(parents=True, exist_ok=True)

        print("[3/5] Clonando código fonte do whisper.cpp...")
        run_cmd(["git", "clone", "--depth", "1", "https://github.com/ggml-org/whisper.cpp.git", str(src_dir)])

        extra_cxx_flags = []
        extra_cmake_args = []

        # No Linux, se os cabeçalhos Vulkan não estiverem no sistema, clona automaticamente
        if sys.platform.startswith("linux") and not Path("/usr/include/vulkan/vulkan.h").exists():
            print("    Baixando Vulkan-Headers e SPIRV-Headers...")
            run_cmd(["git", "clone", "--depth", "1", "https://github.com/KhronosGroup/Vulkan-Headers.git", str(vulkan_headers_dir)])
            run_cmd(["git", "clone", "--depth", "1", "https://github.com/KhronosGroup/SPIRV-Headers.git", str(spirv_headers_dir)])

            # Instala SPIRV-Headers no prefixo temporário
            spirv_build = spirv_headers_dir / "build"
            run_cmd([cmake_bin, "-B", str(spirv_build), f"-DCMAKE_INSTALL_PREFIX={prefix_dir}"], cwd=spirv_headers_dir)
            run_cmd([cmake_bin, "--build", str(spirv_build), "--target", "install"], cwd=spirv_headers_dir)

            extra_cmake_args.extend([
                f"-DVulkan_INCLUDE_DIR={vulkan_headers_dir / 'include'}",
                f"-DCMAKE_PREFIX_PATH={prefix_dir}",
            ])
            extra_cxx_flags.extend([
                f"-I{prefix_dir / 'include'}",
                f"-I{vulkan_headers_dir / 'include'}",
            ])

        print("[4/5] Configurando CMake com Vulkan (-DGGML_VULKAN=1)...")
        cmake_cmd = [
            cmake_bin,
            "-B", "build",
            "-DGGML_VULKAN=1",
            "-DCMAKE_BUILD_TYPE=Release",
            "-DCMAKE_INSTALL_RPATH=$ORIGIN",
            "-DCMAKE_BUILD_WITH_INSTALL_RPATH=ON",
        ]
        if ninja_bin:
            cmake_cmd.extend(["-G", "Ninja"])
        if extra_cmake_args:
            cmake_cmd.extend(extra_cmake_args)
        if extra_cxx_flags:
            cmake_cmd.append(f"-DCMAKE_CXX_FLAGS={' '.join(extra_cxx_flags)}")

        run_cmd(cmake_cmd, cwd=src_dir)

        print("[5/5] Compilando whisper-cli...")
        cpu_count = os.cpu_count() or 4
        build_cmd = [cmake_bin, "--build", "build", "--config", "Release", "--target", "whisper-cli", f"-j{cpu_count}"]
        run_cmd(build_cmd, cwd=src_dir)

        # Copia os artefatos compilados para bin/
        built_bin_dir = src_dir / "build" / "bin"
        if not built_bin_dir.exists():
            built_bin_dir = src_dir / "bin"

        print(f"Copiando binários de {built_bin_dir} para {BIN_DIR}...")
        for item in built_bin_dir.iterdir():
            dest = BIN_DIR / item.name
            if item.is_file() or item.is_symlink():
                shutil.copy2(item, dest, follow_symlinks=False)
                if sys.platform != "win32":
                    try:
                        os.chmod(dest, 0o755)
                    except Exception:
                        pass

        # No Linux, ajusta RPATH para $ORIGIN se patchelf estiver presente
        if sys.platform.startswith("linux"):
            patchelf = shutil.which("patchelf")
            cli_dest = BIN_DIR / "whisper-cli"
            if patchelf and cli_dest.exists():
                subprocess.run([patchelf, "--set-rpath", "$ORIGIN", str(cli_dest)], check=False)
                for lib in BIN_DIR.glob("*.so*"):
                    subprocess.run([patchelf, "--set-rpath", "$ORIGIN", str(lib)], check=False)

    print("\n[SUCESSO] Compilação concluída! Motor whisper-cli Vulkan disponível em bin/.\n")


if __name__ == "__main__":
    try:
        build_whisper_vulkan()
    except Exception as e:
        print(f"\n[ERRO] Falha na compilação: {e}", file=sys.stderr)
        sys.exit(1)
