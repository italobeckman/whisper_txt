# syntax=docker/dockerfile:1

# Imagem oficial do uv em versão exata (evita "latest" e builds não reprodutíveis).
# Usada apenas como fonte do binário copiado para a imagem final.
FROM ghcr.io/astral-sh/uv:0.12.22 AS uv

# Imagem base com runtime Vulkan necessário para executar o whisper.cpp.
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

# Dependências do sistema: Python 3, runtime Vulkan e utilitários.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    libvulkan1 \
    vulkan-tools \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copia o uv e o uvx da imagem oficial fixada acima.
COPY --from=uv /uv /uvx /bin/

WORKDIR /app

# Copia apenas os manifests primeiro para aproveitar o cache de camadas.
# O uv.lock é obrigatório: é ele que torna a resolução de dependências exata.
COPY pyproject.toml uv.lock ./

# --frozen instala exatamente o que está no uv.lock e falha se ele divergir do pyproject.toml.
RUN uv sync --frozen

# Copia o código da aplicação.
COPY . .

# Volumes persistentes para não baixar modelos e binário a cada container.
# Monte volumes nomeados nesses caminhos para reaproveitar o cache (veja o README).
VOLUME ["/app/models", "/app/bin"]

# Executa com o lock congelado; o comando padrão exibe a ajuda da CLI.
ENTRYPOINT ["uv", "run", "--frozen", "cli.py"]
CMD ["--help"]
