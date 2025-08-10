FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim as base

COPY src/. .

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    portaudio19-dev \
    ffmpeg && \
    rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV PYTHONUNBUFFERED=1

RUN uv sync --locked

CMD ["uv", "run", "python", "__main__.py"]
