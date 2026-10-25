FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    libimage-exiftool-perl \
    darktable \
    imagemagick \
    ca-certificates \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip3 install --no-cache-dir --break-system-packages "redis>=5.0.0"

COPY src ./src

ENV PYTHONPATH=/app

ENTRYPOINT ["python3", "-m", "src"]
