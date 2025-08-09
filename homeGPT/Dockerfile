FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# ffmpeg + numpy deps
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY src/. .
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
RUN uv sync --locked

CMD ["uv", "run", "python", "audio_test.py"]