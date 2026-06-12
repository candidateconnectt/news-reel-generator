FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install ffmpeg with ALL codecs - critical for Railway
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        ffmpeg \
        # These codec libraries are essential
        libx264-dev \
        libx265-dev \
        libvpx-dev \
        libmp3lame-dev \
        libopus-dev \
        libvorbis-dev \
        libass-dev \
        fonts-dejavu-core \
        fonts-liberation \
        curl \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Verify ffmpeg has the required encoders
RUN ffmpeg -encoders | grep -q libx264 && echo "✓ libx264 available" || echo "⚠️ libx264 missing"

WORKDIR /app

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure ffmpeg/ffprobe are in PATH
ENV PATH="/usr/bin:/usr/local/bin:${PATH}"

EXPOSE 8000

# Use direct uvicorn command (simpler, fewer points of failure)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]