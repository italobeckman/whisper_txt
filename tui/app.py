"""Modern interactive Terminal User Interface (TUI) for whisper-txt using Textual."""
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Garante que a raiz do projeto esteja no sys.path mesmo se app.py for executado diretamente
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import (
    Button,
    DirectoryTree,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    RadioButton,
    RadioSet,
    RichLog,
)

import config
from core.audio import (
    AUDIO_EXTENSIONS,
    VIDEO_EXTENSIONS,
    cleanup_temp_audio,
    get_audio_tracks,
    is_video_file,
    resolve_audio_source,
)
from core.transcriber import Transcriber


def format_seconds(seconds: Optional[float]) -> str:
    if seconds is None:
        return "00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class FilteredMediaDirectoryTree(DirectoryTree):
    """Árvore de diretórios filtrando apenas vídeos e áudios compatíveis."""

    def filter_paths(self, paths: list[Path]) -> list[Path]:
        valid_exts = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS
        return [
            p for p in paths
            if not p.name.startswith((".", "_"))
            and p.name != "__pycache__"
            and (p.is_dir() or (p.is_file() and p.suffix.lower() in valid_exts))
        ]


class WhisperTxtApp(App):
    """Aplicativo Textual interativo para o Whisper TXT."""

    CSS_PATH = "styles.tcss"
    TITLE = "Whisper TXT"
    SUB_TITLE = f"Dispositivo: {config.DEVICE.upper()}"

    BINDINGS = [
        Binding("q", "quit", "Sair"),
        Binding("s", "start", "Iniciar Transcrição"),
        Binding("tab", "focus_next", "Próximo Campo"),
        Binding("shift+tab", "focus_previous", "Campo Anterior"),
    ]

    selected_file: reactive[Optional[Path]] = reactive(None)
    selected_quality: reactive[str] = reactive("fast")
    selected_language: reactive[str] = reactive("pt")
    selected_track: reactive[int] = reactive(0)
    available_tracks: reactive[List[Dict[str, Any]]] = reactive([])
    is_processing: reactive[bool] = reactive(False)

    def __init__(self, initial_path: Optional[Union[str, Path]] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.initial_path = Path(initial_path).resolve() if initial_path else None
        if self.initial_path and self.initial_path.is_file():
            self.start_dir = self.initial_path.parent
            self.preselected_file: Optional[Path] = self.initial_path
        elif self.initial_path and self.initial_path.is_dir():
            self.start_dir = self.initial_path
            self.preselected_file = None
        else:
            self.start_dir = Path.cwd()
            self.preselected_file = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Horizontal(id="main-container"):
            # Coluna Esquerda: Arquivos e Navegação
            with Vertical(id="left-panel"):
                yield Label("ARQUIVOS DE MÍDIA", classes="panel-title")
                with Horizontal(id="dir-nav-bar"):
                    yield Button("▲ Subir Pasta", id="btn-dir-up", variant="default")
                    yield Label(f"Pasta: {self.start_dir.name or str(self.start_dir)}", id="lbl-current-dir")
                yield FilteredMediaDirectoryTree(str(self.start_dir), id="file-tree")
                yield Label("Nenhum arquivo selecionado", id="lbl-selected-file")

            # Coluna Direita: Controles, Botão de Início e Transcrição Ao Vivo
            with Vertical(id="right-panel"):
                # Configurações Compactas
                with Vertical(id="config-box"):
                    with Horizontal(classes="config-row"):
                        yield Label("Qualidade:", classes="row-label")
                        with RadioSet(id="quality-radios"):
                            yield RadioButton("Fast (turbo q5_0, beam 1) [Padrão]", id="fast", value=True)
                            yield RadioButton("Balanced (turbo q5_0, beam 5)", id="balanced")
                            yield RadioButton("Max (turbo fp16, beam 5)", id="max")

                    with Horizontal(classes="config-row"):
                        yield Label("Idioma:", classes="row-label")
                        with RadioSet(id="radio-language"):
                            yield RadioButton("Português (pt)", id="lang-pt", value=True)
                            yield RadioButton("Inglês (en)", id="lang-en")
                            yield RadioButton("Espanhol (es)", id="lang-es")

                    with Container(id="track-box"):
                        with Horizontal(id="track-row"):
                            yield Label("Trilha de Áudio:", classes="row-label")
                            yield Label("Trilha padrão (Trilha 0)", id="lbl-track-info")
                            yield Button("Trocar Trilha", id="btn-toggle-track", variant="primary", disabled=True)

                    with Horizontal(id="prompt-row"):
                        yield Label("Vocabulário:", classes="row-label")
                        yield Input(
                            placeholder="Termos específicos (opcional, ex: PyTorch, TCC)...",
                            id="input-prompt",
                        )

                # Botão de Ação Principal (sempre visível no meio da tela)
                with Container(id="action-bar"):
                    yield Button(
                        "INICIAR TRANSCRIÇÃO (Enter / S)",
                        id="btn-start",
                        variant="success",
                    )

                # Progresso
                with Container(id="progress-box"):
                    yield Label("Status: Pronto.", id="lbl-status")
                    yield ProgressBar(id="progress-bar", total=100, show_eta=True)

                # Transcrição ao vivo
                with Container(id="log-box"):
                    yield Label("TRANSCRIÇÃO EM TEMPO REAL", classes="panel-title")
                    yield RichLog(id="log-transcript", highlight=True, markup=True)

        yield Footer()

    def on_mount(self) -> None:
        """Inicializa estado e pré-seleciona arquivo caso fornecido via argumento."""
        if self.preselected_file and self.preselected_file.is_file():
            self.select_media_file(self.preselected_file)

    def select_media_file(self, file_path: Path) -> None:
        """Atualiza a seleção do arquivo de mídia e analisa trilhas de áudio."""
        self.selected_file = Path(file_path)
        lbl = self.query_one("#lbl-selected-file", Label)
        lbl.update(
            f"Selecionado: [bold green]{self.selected_file.name}[/]\n"
            f"[dim]Pressione [bold]Enter[/] ou tecla [bold]S[/] para iniciar[/]"
        )

        btn_track = self.query_one("#btn-toggle-track", Button)
        lbl_track = self.query_one("#lbl-track-info", Label)

        if is_video_file(self.selected_file):
            try:
                tracks = get_audio_tracks(self.selected_file)
            except Exception:
                tracks = []
            self.available_tracks = tracks
            self.selected_track = 0
            if len(tracks) > 1:
                btn_track.disabled = False
                lbl_track.update(
                    f"Trilha 0 ({tracks[0].get('codec', 'audio')}, {tracks[0].get('language', 'und')}) [1/{len(tracks)}]"
                )
            elif len(tracks) == 1:
                btn_track.disabled = True
                lbl_track.update(f"Trilha única ({tracks[0].get('codec', 'audio')})")
            else:
                btn_track.disabled = True
                lbl_track.update("Nenhuma trilha de áudio detectada")
        else:
            self.available_tracks = []
            self.selected_track = 0
            btn_track.disabled = True
            lbl_track.update("Áudio direto (sem trilhas)")

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Chamado quando um arquivo é clicado ou acionado com Enter na árvore."""
        new_path = Path(event.path)
        if self.selected_file == new_path:
            # Pressionou Enter no mesmo arquivo já selecionado -> inicia a transcrição
            self.start_transcription()
            return
        self.select_media_file(new_path)

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Chamado quando o preset de qualidade ou o idioma é alterado."""
        if event.radio_set.id == "quality-radios" and event.pressed:
            self.selected_quality = event.pressed.id or "fast"
        elif event.radio_set.id == "radio-language" and event.pressed:
            lang_id = event.pressed.id or "lang-pt"
            self.selected_language = lang_id.replace("lang-", "")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Trata cliques em botões."""
        if event.button.id == "btn-start":
            self.start_transcription()
        elif event.button.id == "btn-toggle-track":
            if self.available_tracks:
                self.selected_track = (self.selected_track + 1) % len(self.available_tracks)
                cur_track = self.available_tracks[self.selected_track]
                lbl_track = self.query_one("#lbl-track-info", Label)
                lbl_track.update(
                    f"Trilha {self.selected_track} ({cur_track.get('codec', 'audio')}, {cur_track.get('language', 'und')}) [{self.selected_track + 1}/{len(self.available_tracks)}]"
                )
        elif event.button.id == "btn-dir-up":
            tree = self.query_one("#file-tree", FilteredMediaDirectoryTree)
            current_p = Path(tree.path).resolve()
            parent = current_p.parent
            if parent.exists() and parent != current_p:
                tree.path = parent
                lbl_dir = self.query_one("#lbl-current-dir", Label)
                lbl_dir.update(f"Pasta: {parent.name or str(parent)}")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Pressionar Enter dentro do campo de vocabulário inicia a transcrição."""
        self.start_transcription()

    def action_start(self) -> None:
        """Atalho de teclado 'S' para iniciar a transcrição."""
        self.start_transcription()

    def start_transcription(self) -> None:
        """Valida a seleção e inicia a transcrição em background."""
        if self.is_processing:
            self.notify("Já existe uma transcrição em andamento.", severity="warning")
            return

        if not self.selected_file or not self.selected_file.is_file():
            self.notify("Por favor, selecione um arquivo de mídia à esquerda.", severity="error")
            return

        self.is_processing = True
        btn = self.query_one("#btn-start", Button)
        btn.disabled = True
        prompt_val = self.query_one("#input-prompt", Input).value.strip() or None

        log = self.query_one("#log-transcript", RichLog)
        log.clear()
        log.write(f"[bold cyan]Iniciando transcrição de:[/] {self.selected_file.name}")
        log.write(
            f"[dim]Preset: {self.selected_quality} | Idioma: {self.selected_language} | "
            f"Trilha: {self.selected_track} | Saída: mesma pasta[/]\n"
        )

        self.run_transcription_worker(
            self.selected_file,
            self.selected_quality,
            self.selected_language,
            self.selected_track,
            prompt_val,
        )

    @work(thread=True)
    def run_transcription_worker(
        self,
        file_path: Path,
        quality: str,
        language: str,
        track_index: int,
        prompt: Optional[str],
    ) -> None:
        """Executa a extração e a transcrição em uma thread em background."""
        temp_audio = None
        is_temp = False
        start_time = time.time()

        lbl_status = self.query_one("#lbl-status", Label)
        progress_bar = self.query_one("#progress-bar", ProgressBar)
        btn = self.query_one("#btn-start", Button)

        try:
            self.call_from_thread(lbl_status.update, "Status: Resolvendo áudio...")
            audio_source, is_temp = resolve_audio_source(file_path, track_index=track_index)
            temp_audio = audio_source if is_temp else None

            self.call_from_thread(lbl_status.update, f"Status: Carregando modelo ({quality})...")
            transcriber = Transcriber(quality=quality)

            def segment_callback(seg: Any) -> None:
                ts = format_seconds(seg.start)
                line = f"[bold yellow][{ts}][/] {seg.text.strip()}"
                self.call_from_thread(self._append_log_line, line)

            def progress_callback(pct: float, elapsed: float) -> None:
                self.call_from_thread(progress_bar.update, progress=pct)
                self.call_from_thread(
                    lbl_status.update,
                    f"Status: Transcrevendo... {pct:.1f}% ({elapsed:.0f}s)",
                )

            self.call_from_thread(lbl_status.update, "Status: Transcrevendo áudio com Whisper...")
            segments, _ = transcriber.transcribe(
                audio_path=audio_source,
                language=language,
                initial_prompt=prompt,
                on_segment=segment_callback,
                on_progress=progress_callback,
            )

            # Exporta na mesma pasta do arquivo original em .txt
            base_out = file_path.parent / config.sanitize_filename(file_path.stem)
            txt_file = transcriber.export_txt(
                segments=segments,
                base_output_path=base_out,
                overwrite=True,
            )

            elapsed_total = time.time() - start_time
            self.call_from_thread(progress_bar.update, progress=100.0)
            self.call_from_thread(
                lbl_status.update,
                f"Status: [bold green]Concluído em {elapsed_total:.0f}s![/]",
            )
            self.call_from_thread(
                self._append_log_line,
                f"\n[bold green]✓ Sucesso![/] Transcrição salva em:\n  • {txt_file.name}",
            )
            self.notify(f"Transcrição de {file_path.name} finalizada com sucesso!", severity="information")

        except Exception as e:
            self.call_from_thread(
                lbl_status.update,
                f"Status: [bold red]Erro: {e}[/]",
            )
            self.call_from_thread(self._append_log_line, f"\n[bold red][ERRO][/] {e}")
            self.notify(f"Erro na transcrição: {e}", severity="error")

        finally:
            if is_temp and temp_audio:
                cleanup_temp_audio(temp_audio)
            self.is_processing = False
            self.call_from_thread(setattr, btn, "disabled", False)

    def _append_log_line(self, line: str) -> None:
        log = self.query_one("#log-transcript", RichLog)
        log.write(line)


if __name__ == "__main__":
    app = WhisperTxtApp()
    app.run()
