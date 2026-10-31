# Imagem base leve com suporte a Vulkan
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Instala dependências do sistema: Python 3, Vulkan runtime e utilitários
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    libvulkan1 \
    vulkan-tools \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Instala o uv copiando o binário oficial
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copia configurações de dependências
COPY pyproject.toml .

# Sincroniza ambiente virtual usando uv
RUN uv sync

# Copia o código do projeto
COPY . .

# Entrypoint via uv run
ENTRYPOINT ["uv", "run", "cli.py"]
CMD ["--help"]
