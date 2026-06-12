FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Tools needed to download and extract the static ffmpeg tarball,
# plus the fonts used by the PIL caption renderer in the stitcher.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        wget \
        xz-utils \
        ca-certificates \
        fonts-dejavu-core \
        bash \
 && rm -rf /var/lib/apt/lists/*

# Static ffmpeg build (johnvansickle.com) -- self-contained binary
# with ALL codecs statically linked (libx264, libx265, libvpx,
# libmp3lame, libopus, libvorbis, etc.). Sidesteps the Debian
# slim image's stripped-down ffmpeg package entirely.
ARG FFMPEG_VERSION=7.1
ARG FFMPEG_URL=https://johnvansickle.com/ffmpeg/releases/ffmpeg-${FFMPEG_VERSION}-amd64-static.tar.xz
RUN wget -q -O /tmp/ffmpeg.tar.xz "${FFMPEG_URL}" \
 && tar -xJf /tmp/ffmpeg.tar.xz -C /tmp \
 && mv /tmp/ffmpeg-${FFMPEG_VERSION}-amd64-static/ffmpeg  /usr/local/bin/ffmpeg \
 && mv /tmp/ffmpeg-${FFMPEG_VERSION}-amd64-static/ffprobe /usr/local/bin/ffprobe \
 && chmod +x /usr/local/bin/ffmpeg /usr/local/bin/ffprobe \
 && rm -rf /tmp/ffmpeg*

# Sanity check: the build must include libx264, otherwise the
# render worker's chunk creation will fail with "Unknown
# encoder 'libx264'" and we'll find out at runtime.
RUN ffmpeg -version >/dev/null \
 && ffmpeg -encoders 2>/dev/null | grep -q 'libx264' \
 && echo "[build] ffmpeg $(ffmpeg -version | head -n1) -- libx264 OK" \
 || (echo "[build] ffmpeg missing libx264 encoder -- build broken" && exit 1)

WORKDIR /app

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Bash so we can use $PORT with the :- default-value syntax
# (Debian's /bin/sh is dash and doesn't support :-).
CMD ["bash", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
