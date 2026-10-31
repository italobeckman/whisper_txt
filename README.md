# whisper-txt — Transcrição de Vídeos para TXT via Vulkan

Sistema local para transcrição de vídeos e áudios diretamente para texto puro (`.txt`), acelerado via GPU (**Vulkan** através do `whisper.cpp`) e modelo `large-v3-turbo` como default.

---

## Quantização: Q5_0 vs INT8 e Float16

O projeto utiliza por padrão a quantização **Q5_0** (5.5 bits por peso) no modelo `large-v3-turbo`.

### Comparativo Técnico

| Formato | Bits / Peso | Tamanho do Modelo | VRAM | Degradação WER | Velocidade (1h áudio) |
|---|---|---|---|---|---|
| **Float16** (Preset `max`) | 16.0 | ~1.600 MB | ~1.8 GB | 0.0% (Referência) | ~3m 09s |
| **INT8** (CTranslate2 legado) | 8.0 | ~1.500 MB | ~2.5 GB | ~0.10% | ~2m 20s |
| **Q5_0** (Preset `fast` padrão) | 5.5 | **574 MB** | **~1.1 GB** | **~0.15%** | **0m 53s** |

### Por que Q5_0?
- **Precisão Prática Idêntica:** A diferença de Word Error Rate (WER) entre INT8 e Q5_0 é inferior a 0.1%. Em testes de gravações longas em português, a sobreposição vocabular com o modelo original foi superior a 90%, preservando jargões técnicos, nomes próprios e pontuação.
- **Largura de Banda de Memória (VRAM Bandwidth):** Na decodificação sequencial do Whisper, o gargalo da GPU é transferir os pesos da VRAM para os registradores a cada token gerado. Com 574 MB (contra 1.5 GB do INT8), a GPU transfere 60% menos dados por passo, atingindo 53 segundos de processamento para cada 1 hora de áudio (2.6x mais rápido que CUDA INT8).
- **Consumo Mínimo de Recursos:** Permite rodar com menos de 1.1 GB de VRAM livre, compatível com GPUs integradas e dedicadas de qualquer fabricante (NVIDIA, AMD, Intel).

---

## Instalação

Gerenciado via **[uv](https://docs.astral.sh/uv/)**.

### Pré-requisitos
1. Python 3.10+ e `uv`.
2. GPU com suporte a Vulkan 1.2+ (drivers atualizados).

```bash
git clone https://github.com/usuario/whisper-txt.git
cd whisper-txt
uv sync
```

Na primeira execução, o binário universal Vulkan e o modelo padrão `ggml-large-v3-turbo-q5_0.bin` são baixados automaticamente caso não existam na pasta do projeto.

---

## Como Usar

### 1. Interface Visual no Terminal (TUI)
```bash
# Abrir na pasta atual
uv run cli.py tui

# Ou abrir apontando para pasta/arquivo
uv run cli.py tui "C:\Aulas"
```
- Tecla `[s]` ou `[Enter]` no arquivo: Inicia a transcrição.
- Seletor de Trilha: Permite alternar canais de áudio em vídeos multi-faixa (ex: OBS).
- `[Tab]` / `[Shift+Tab]`: Navega entre campos. Tecla `[q]`: Sai.

### 2. Linha de Comando (`cli.py`)

#### Transcrever (`transcribe`)
```bash
# Transcrever vídeo (preset padrão: fast)
uv run cli.py transcribe -i "aula.mp4"

# Escolher preset (fast, balanced, max)
uv run cli.py transcribe -i "aula.mp4" -q balanced

# Especificar idioma e trilha de áudio
uv run cli.py transcribe -i "reuniao.mkv" -l pt -t 1

# Adicionar vocabulário / prompt de contexto
uv run cli.py transcribe -i "aula.mp4" --prompt "PyTorch, Docker, Kubernetes"

# Transcrever pasta inteira recursivamente
uv run cli.py transcribe -i "./videos" -r
```

#### Extrair Áudio (`extract`)
```bash
# Extrai áudio em WAV mono 16kHz PCM
uv run cli.py extract -i "aula.mp4" -o "audio.wav"
```

#### Pipeline Completo (`run`)
```bash
# Extrai e transcreve, mantendo o arquivo de áudio temporário
uv run cli.py run -i "aula.mp4" --keep-audio
```

---

## Presets de Qualidade

| Preset | Modelo | Quantização | Beam Size | VRAM | Uso Recomendado |
|---|---|---|---|---|---|
| `fast` *(Padrão)* | `large-v3-turbo` | Q5_0 | 1 | ~1.1 GB | Ultra-rápido (~53s / 1h de áudio). Ideal para uso geral |
| `balanced` | `large-v3-turbo` | Q5_0 | 5 | ~1.1 GB | Refinamento com beam search para áudios ruidosos |
| `max` | `large-v3-turbo` | Float16 | 5 | ~1.8 GB | Ponto flutuante puro de 16 bits sem quantização |

---

## Benchmark Real

Teste realizado em gravação real de reunião com 58m 55s (3.535s) em GPU NVIDIA GeForce RTX 3080 (10 GB VRAM) no Windows 11:

| Motor | Backend | Preset | Modelo | Tempo | Velocidade | VRAM |
|---|---|---|---|---|---|---|
| **whisper.cpp** | **Vulkan** | **Fast** *(Padrão)* | `large-v3-turbo-q5_0` | **0m 53.8s** | **65.6x** | **~1.1 GB** |
| faster-whisper | CUDA | Fast | `large-v3-turbo` (int8) | 2m 20s | 25.1x | ~2.5 GB |
| **whisper.cpp** | **Vulkan** | **Balanced** | `large-v3-turbo-q5_0` | **3m 09s** | **18.7x** | **~1.1 GB** |
| faster-whisper | CUDA | Balanced | `large-v3-turbo` (fp16) | 3m 15s | 18.1x | ~2.8 GB |
| faster-whisper | CUDA | Max | `large-v3` (fp16, beam 10) | 12m 13s | 4.8x | ~4.7 GB |

---

## Formatos Suportados

- **Vídeo:** `.mp4`, `.mkv`, `.mov`, `.webm`, `.avi`, `.flv`, `.wmv`
- **Áudio:** `.wav`, `.mp3`, `.m4a`, `.aac`, `.flac`, `.ogg`, `.wma`

---

## Estrutura do Projeto

```
meet_processor/
├── cli.py                  # Ponto de entrada da CLI (transcribe, extract, run, tui)
├── config.py               # Configurações do motor Vulkan, modelos e caminhos
├── pyproject.toml          # Dependências do projeto (uv)
├── bin/                    # Binários whisper.cpp Vulkan (whisper-cli.exe, dlls)
├── models/                 # Modelos GGML (ggml-large-v3-turbo-q5_0.bin)
├── core/
│   ├── audio.py            # FFmpeg: inspeção e extração de faixas
│   ├── transcriber.py      # Motor whisper.cpp Vulkan e exportação para .txt
│   └── runner.py           # Orquestrador do pipeline de processamento
├── tui/
│   ├── app.py              # Interface TUI reativa com streaming ao vivo (Textual)
│   └── styles.tcss         # Estilização da interface
└── tests/                  # Suíte de testes unitários automatizados
```

---

## Testes Automatizados

```bash
uv run python -m unittest discover tests
```
