FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Tools needed to download and extract the static ffmpeg tarball
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        wget \
        tar \
        xz-utils \
        ca-certificates \
        fonts-dejavu-core \
        fonts-liberation \
        bash \
 && rm -rf /var/lib/apt/lists/*

# Download static ffmpeg build (using the latest working URL)
# The johnvansickle.com URL pattern changed - using direct latest version
RUN wget -O /tmp/ffmpeg.tar.xz https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz \
 && tar -xf /tmp/ffmpeg.tar.xz -C /tmp \
 && mv /tmp/ffmpeg-*-static/ffmpeg /usr/local/bin/ffmpeg \
 && mv /tmp/ffmpeg-*-static/ffprobe /usr/local/bin/ffprobe \
 && chmod +x /usr/local/bin/ffmpeg /usr/local/bin/ffprobe \
 && rm -rf /tmp/ffmpeg*

# Verify libx264 encoder is available
RUN /usr/local/bin/ffmpeg -encoders 2>/dev/null | grep -q 'libx264' \
 && echo "✓ libx264 encoder available" \
 || (echo "✗ libx264 encoder missing - build will fail" && exit 1)

WORKDIR /app

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure ffmpeg is in PATH
ENV PATH="/usr/local/bin:${PATH}"

EXPOSE 8000

CMD ["bash", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]