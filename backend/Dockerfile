FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install ffmpeg and dependencies
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        wget \
        tar \
        xz-utils \
        ca-certificates \
        fonts-dejavu-core \
        fonts-liberation \
        curl \
 && rm -rf /var/lib/apt/lists/*

# Download static ffmpeg
RUN wget -O /tmp/ffmpeg.tar.xz https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz \
 && tar -xf /tmp/ffmpeg.tar.xz -C /tmp \
 && mv /tmp/ffmpeg-*-static/ffmpeg /usr/local/bin/ \
 && mv /tmp/ffmpeg-*-static/ffprobe /usr/local/bin/ \
 && chmod +x /usr/local/bin/ffmpeg /usr/local/bin/ffprobe \
 && rm -rf /tmp/*

# Verify ffmpeg works
RUN /usr/local/bin/ffmpeg -version | head -n1

WORKDIR /app

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PATH="/usr/local/bin:${PATH}"

# Simple CMD - no complex bash script
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}