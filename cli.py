"""CLI entrypoint for whisper-txt - Transcrição de Vídeos para TXT."""
import argparse
import sys
import time
from pathlib import Path
from typing import List, Set

import config
from core.audio import (
    AUDIO_EXTENSIONS,
    VIDEO_EXTENSIONS,
    cleanup_temp_audio,
    extract_audio,
    get_audio_tracks,
    is_video_file,
    resolve_audio_source,
)
from core.runner import run_pipeline
from core.transcriber import Transcriber, add_extension


def collect_files(target: Path, extensions: Set[str], recursive: bool = False) -> List[Path]:
    """Coleta arquivos compatíveis com base na lista de extensões."""
    target = Path(target)
    if target.is_file():
        if target.suffix.lower() in extensions:
            return [target]
        return []

    if target.is_dir():
        pattern = "**/*" if recursive else "*"
        matches = [
            p for p in target.glob(pattern)
            if p.is_file()
            and p.suffix.lower() in extensions
            and not p.name.startswith((".", "_"))
            and not any(part.startswith((".", "_")) for part in p.parts[:-1])
        ]
        return sorted(matches)

    return []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="whisper-txt",
        description="whisper-txt - Transcritor de Vídeos para TXT",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. transcribe
    p_transcribe = subparsers.add_parser("transcribe", help="Transcreve vídeos para .txt via Vulkan")
    p_transcribe.add_argument("-i", "--input", required=True, help="Arquivo de vídeo ou pasta")
    p_transcribe.add_argument("-o", "--output", default=None, help="Diretório de saída (padrão: mesma pasta do arquivo original)")
    p_transcribe.add_argument(
        "-q", "--quality", choices=["fast", "balanced", "max"], default="fast",
        help="Nível de qualidade do modelo (padrão: fast [large-v3-turbo q5_0, beam 1])"
    )
    p_transcribe.add_argument("--model", default=None, help="Sobrescreve o arquivo ou modelo GGML (ex: ggml-large-v3-turbo-q5_0.bin)")
    p_transcribe.add_argument("--beam-size", type=int, default=None, help="Sobrescreve o beam_size")
    p_transcribe.add_argument("--threads", type=int, default=None, help="Número de threads para processamento (padrão: 8)")
    p_transcribe.add_argument("-l", "--language", default="pt", help="Idioma das gravações (padrão: pt)")
    p_transcribe.add_argument("-t", "--track", type=int, default=0, help="Índice da trilha de áudio do vídeo (padrão: 0)")
    p_transcribe.add_argument("--device", default=None, help="Dispositivo / GPU Vulkan (padrão: autodetectado)")
    p_transcribe.add_argument("--prompt", default=None, help="Prompt de contexto / termos técnicos para o Whisper")
    p_transcribe.add_argument("-f", "--overwrite", action="store_true", help="Sobrescreve transcrições existentes")
    p_transcribe.add_argument("-r", "--recursive", action="store_true", help="Busca recursiva em subpastas")

    # 2. extract
    p_extract = subparsers.add_parser("extract", help="Extrai áudio WAV 16kHz mono de vídeos")
    p_extract.add_argument("-i", "--input", required=True, help="Arquivo de vídeo ou pasta")
    p_extract.add_argument("-o", "--output", default=None, help="Arquivo ou pasta de saída de áudio")
    p_extract.add_argument("-t", "--track", type=int, default=0, help="Índice da trilha de áudio do vídeo (padrão: 0)")
    p_extract.add_argument("-f", "--overwrite", action="store_true", help="Sobrescreve arquivos existentes")
    p_extract.add_argument("-r", "--recursive", action="store_true", help="Busca recursiva em subpastas")

    # 3. run
    p_run = subparsers.add_parser("run", help="Executa o pipeline (extração de áudio + transcrição para .txt)")
    p_run.add_argument("-i", "--input", required=True, help="Arquivo de vídeo ou pasta")
    p_run.add_argument("-o", "--output", default=None, help="Diretório base de saída")
    p_run.add_argument("-q", "--quality", choices=["fast", "balanced", "max"], default="fast", help="Qualidade da transcrição (padrão: fast)")
    p_run.add_argument("-t", "--track", type=int, default=0, help="Índice da trilha de áudio do vídeo (padrão: 0)")
    p_run.add_argument("--keep-audio", action="store_true", help="Mantém o arquivo de áudio WAV gerado")
    p_run.add_argument("--prompt", default=None, help="Prompt de termos para o Whisper")
    p_run.add_argument("-l", "--language", default="pt", help="Idioma (padrão: pt)")
    p_run.add_argument("-f", "--overwrite", action="store_true", help="Sobrescreve arquivos existentes")
    p_run.add_argument("-r", "--recursive", action="store_true", help="Busca recursiva em subpastas")

    # 4. tui
    p_tui = subparsers.add_parser("tui", help="Abre a interface interativa no terminal")
    p_tui.add_argument("path", nargs="?", default=None, help="Caminho opcional do arquivo ou pasta para abrir na TUI")
    p_tui.add_argument("-i", "--input", dest="input_path", default=None, help="Caminho opcional do arquivo ou pasta para abrir na TUI")

    return parser


def handle_transcribe(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[ERRO] Entrada não encontrada: {input_path}")
        sys.exit(1)

    extensions = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS
    files = collect_files(input_path, extensions, recursive=args.recursive)
    if not files:
        print(f"[ERRO] Nenhum vídeo encontrado em: {input_path}")
        sys.exit(1)

    print(f"\n[Transcrição] Encontrados {len(files)} vídeo(s).")
    print(f"Motor: whisper.cpp (Vulkan) | Dispositivo: {config.DEVICE}")
    print(f"Preset: {args.quality} | Idioma: {args.language} | Saída: {args.output or 'mesma pasta'}\n")

    transcriber = Transcriber(
        model_name=args.model,
        device=args.device,
        quality=args.quality,
        threads=getattr(args, "threads", None),
    )

    for i, file_path in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {file_path.name}")
        out_dir = Path(args.output) if args.output else file_path.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        base_out = out_dir / config.sanitize_filename(file_path.stem)
        txt_target = add_extension(base_out, "txt")

        # Checa se já existe
        if not args.overwrite and txt_target.exists():
            print("    -> Transcrição já existe, pulando.")
            continue

        # Trata áudio (extração temporária se for vídeo)
        temp_audio = None
        is_temp = False
        try:
            if is_video_file(file_path):
                tracks = get_audio_tracks(file_path)
                if len(tracks) > 1:
                    chosen = tracks[min(args.track, len(tracks) - 1)]
                    print(
                        f"    [Trilhas de Áudio] {len(tracks)} faixas detectadas. "
                        f"Usando trilha {args.track} ({chosen.get('language', 'und')})"
                    )

            audio_source, is_temp = resolve_audio_source(file_path, track_index=args.track)
            temp_audio = audio_source if is_temp else None

            start_t = time.time()
            segments, _ = transcriber.transcribe(
                audio_path=audio_source,
                language=args.language,
                beam_size=args.beam_size,
                initial_prompt=args.prompt,
            )
            created = transcriber.export_txt(
                segments=segments,
                base_output_path=base_out,
                overwrite=args.overwrite,
            )
            elapsed = time.time() - start_t
            print(f"    -> Concluído em {elapsed:.1f}s: {created.name}")
        except Exception as e:
            print(f"    -> [ERRO] {e}")
        finally:
            if is_temp and temp_audio:
                cleanup_temp_audio(temp_audio)

    print("\nProcessamento concluído.")


def handle_extract(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[ERRO] Entrada não encontrada: {input_path}")
        sys.exit(1)

    files = collect_files(input_path, VIDEO_EXTENSIONS, recursive=args.recursive)
    if not files:
        print(f"[ERRO] Nenhum vídeo encontrado em: {input_path}")
        sys.exit(1)

    print(f"\n[Extração de Áudio] Encontrados {len(files)} vídeo(s).\n")

    for i, video in enumerate(files, 1):
        if args.output:
            out_target = Path(args.output)
            if out_target.is_dir() or len(files) > 1 or not out_target.suffix:
                out_target.mkdir(parents=True, exist_ok=True)
                audio_out = add_extension(out_target / config.sanitize_filename(video.stem), "wav")
            else:
                out_target.parent.mkdir(parents=True, exist_ok=True)
                audio_out = out_target
        else:
            audio_out = add_extension(video.parent / config.sanitize_filename(video.stem), "wav")

        print(f"[{i}/{len(files)}] {video.name} -> {audio_out.name}")
        if audio_out.exists() and not args.overwrite:
            print("    -> Já existe, pulando.")
            continue

        success = extract_audio(video, audio_out, overwrite=args.overwrite, track_index=args.track)
        if success:
            size_mb = audio_out.stat().st_size / (1024 * 1024) if audio_out.exists() else 0.0
            print(f"    -> Extraído com sucesso ({size_mb:.1f} MB)")
        else:
            print(f"    -> [ERRO] Falha ao extrair áudio de {video.name}")

    print("\nExtração concluída.")


def handle_run(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[ERRO] Entrada não encontrada: {input_path}")
        sys.exit(1)

    extensions = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS
    files = collect_files(input_path, extensions, recursive=args.recursive)
    if not files:
        print(f"[ERRO] Nenhum vídeo encontrado em: {input_path}")
        sys.exit(1)

    print(f"\n[Pipeline de Transcrição] Encontrados {len(files)} vídeo(s).")
    print(f"Qualidade: {args.quality} | Idioma: {args.language}\n")

    transcriber_inst = Transcriber(quality=args.quality)

    for i, media_file in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {media_file.name}")
        out_dir = Path(args.output) if args.output else media_file.parent

        def progress_printer(stage, pct, msg):
            print(f"    [{stage.upper()}] {msg}")

        try:
            res = run_pipeline(
                input_path=media_file,
                output_dir=out_dir,
                quality=args.quality,
                keep_audio=args.keep_audio,
                overwrite=args.overwrite,
                initial_prompt=args.prompt,
                language=args.language,
                track_index=args.track,
                on_progress=progress_printer,
                transcriber_instance=transcriber_inst,
            )
            if res.get("skipped"):
                print("    -> Já transcrito, pulando.")
            else:
                print("    -> Transcrito com sucesso.")
        except Exception as e:
            print(f"    -> [ERRO] {e}")

    print("\nPipeline concluído.")


def handle_tui(args: argparse.Namespace) -> None:
    try:
        from tui.app import WhisperTxtApp
    except ImportError as e:
        print("\n[ERRO] A interface de terminal interativa (TUI) requer a biblioteca 'textual'.")
        print("Para instalar, execute:")
        print("    pip install textual")
        print(f"\nDetalhes técnicos: {e}")
        sys.exit(1)

    initial_path = getattr(args, "input_path", None) or getattr(args, "path", None)
    app = WhisperTxtApp(initial_path=initial_path)
    app.run()


def main():
    parser = build_parser()
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    handlers = {
        "transcribe": handle_transcribe,
        "extract": handle_extract,
        "run": handle_run,
        "tui": handle_tui,
    }

    handler = handlers.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
