FROM debian:bookworm-slim

# Buildx sets this (amd64 / arm64 / …).
ARG TARGETARCH

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Base tools from bookworm. Darktable is installed separately:
# - amd64: Debian unstable (5.4.x) for Canon EOS R5 Mark II / LibRaw 0.22+
# - other arches: bookworm darktable (sid has no arm64 darktable package yet)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    libimage-exiftool-perl \
    imagemagick \
    ca-certificates \
    tzdata \
    && case "${TARGETARCH}" in \
         amd64) \
           printf '%s\n' \
             'deb http://deb.debian.org/debian unstable main' \
             > /etc/apt/sources.list.d/unstable.list \
           && printf '%s\n' \
             'Package: *' \
             'Pin: release a=unstable' \
             'Pin-Priority: 100' \
             '' \
             'Package: darktable*' \
             'Pin: release a=unstable' \
             'Pin-Priority: 990' \
             > /etc/apt/preferences.d/darktable-unstable \
           && apt-get update \
           && apt-get install -y --no-install-recommends -t unstable darktable \
           ;; \
         *) \
           apt-get install -y --no-install-recommends darktable \
           ;; \
       esac \
    && darktable-cli --version \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip3 install --no-cache-dir --break-system-packages "redis>=5.0.0"

COPY src ./src

ENV PYTHONPATH=/app

ENTRYPOINT ["python3", "-m", "src"]
