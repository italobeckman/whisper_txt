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

A CLI é dividida em 3 subcomandos principais com comportamentos específicos:

- **`transcribe`:** Converte vídeo ou áudio diretamente para texto puro (`.txt`). Extrai a faixa para áudio temporário na memória/disco e a apaga ao final.
- **`extract`:** Extrai exclusivamente a faixa de áudio do vídeo para arquivo WAV 16kHz mono PCM (sem executar o modelo de transcrição).
- **`run`:** Executa o pipeline completo permitindo preservar permanentemente o arquivo de áudio WAV gerado com a flag `--keep-audio`.

#### Comportamento Padrão de Saída e Retomada (Batch Resume)
- **Local de Saída:** O arquivo `.txt` é gerado por padrão **no mesmo diretório do arquivo original** com o mesmo nome base (ex: `aula.mp4` -> `aula.txt`). Caso queira centralizar em outra pasta, use `-o / --output`.
- **Pulo Automático de Arquivos:** Se o arquivo `.txt` correspondente já existir, o processamento **pula o arquivo automaticamente** para economizar GPU.
- **Forçar Regravação:** Para sobrescrever transcrições já existentes, utilize a flag `-f` / `--overwrite`.

#### Referência de Parâmetros (`transcribe`)

| Parâmetro | Tipo | Padrão | Descrição |
|---|---|---|---|
| `-i, --input` | Caminho | *(Obrigatório)* | Arquivo de vídeo/áudio ou diretório |
| `-o, --output` | Caminho | Mesma pasta | Pasta de destino para o `.txt` |
| `-q, --quality` | Opção | `fast` | Nível de precisão (`fast`, `balanced`, `max`) |
| `-l, --language` | Texto | `pt` | Idioma falado (`pt`, `en`, `es`, ou `auto` para autodetectar) |
| `-t, --track` | Inteiro | `0` | Índice da trilha de áudio em vídeos multi-canal (OBS) |
| `-f, --overwrite` | Flag | `False` | Força sobrescrever transcrições existentes |
| `-r, --recursive` | Flag | `False` | Busca recursiva em subpastas caso a entrada seja um diretório |
| `--prompt` | Texto | `None` | Termos técnicos, siglas e nomes próprios para guiar o Whisper |
| `--threads` | Inteiro | `8` | Quantidade de threads de CPU utilizadas no processamento |
| `--model` | Texto | *(Do preset)* | Sobrescreve o arquivo GGML (ex: `ggml-large-v3-turbo-q5_0.bin`) |
| `--device` | Inteiro | `0` | ID da GPU Vulkan em sistemas com múltiplas placas de vídeo |

#### Exemplos Práticos de Uso

```bash
# 1. Transcrever um vídeo individual com configuração padrão
uv run cli.py transcribe -i "aula.mp4"

# 2. Processar uma pasta inteira recursivamente com retomada automática (pula os já transcritos)
uv run cli.py transcribe -i "./gravacoes" -r

# 3. Forçar regravação de uma pasta completa
uv run cli.py transcribe -i "./gravacoes" -r -f

# 4. Gravação com áudio separado (ex: faixa 1 do microfone em gravação OBS)
uv run cli.py transcribe -i "podcast.mkv" -t 1

# 5. Injetar vocabulário técnico e autodetectar idioma
uv run cli.py transcribe -i "talk.mp4" -l auto --prompt "Kubernetes, Docker, CI/CD, DevOps"

# 6. Salvar saída em pasta customizada
uv run cli.py transcribe -i "aula.mp4" -o "./transcricoes"

# 7. Extrair apenas áudio WAV mono 16kHz (sem transcrever)
uv run cli.py extract -i "aula.mp4" -o "audio_aula.wav"

# 8. Executar pipeline e manter o arquivo WAV intermediário
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
whisper-txt/
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
