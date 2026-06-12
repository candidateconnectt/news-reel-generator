FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

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

RUN wget -O /tmp/ffmpeg.tar.xz https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz \
 && tar -xf /tmp/ffmpeg.tar.xz -C /tmp \
 && mv /tmp/ffmpeg-*-static/ffmpeg /usr/local/bin/ffmpeg \
 && mv /tmp/ffmpeg-*-static/ffprobe /usr/local/bin/ffprobe \
 && chmod +x /usr/local/bin/ffmpeg /usr/local/bin/ffprobe \
 && rm -rf /tmp/ffmpeg*

RUN /usr/local/bin/ffmpeg -encoders 2>/dev/null | grep -q 'libx264' \
 && echo "✓ libx264 encoder available" \
 || (echo "✗ libx264 encoder missing - build will fail" && exit 1)

WORKDIR /app

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PATH="/usr/local/bin:${PATH}"

# Debug startup script - this will show us exactly what's failing
RUN echo '#!/bin/bash\n\
set -e\n\
echo "========================================="\n\
echo "Starting application container"\n\
echo "========================================="\n\
echo "Python version: $(python --version)"\n\
echo "Working directory: $(pwd)"\n\
echo "Files in /app: $(ls -la)"\n\
echo "========================================="\n\
echo "Testing Python imports..."\n\
python -c "import app.main; print(\'✓ app.main imported\')" || exit 1\n\
python -c "from app.main import app; print(\'✓ FastAPI app created\')" || exit 1\n\
echo "========================================="\n\
echo "Checking environment variables..."\n\
echo "PORT: ${PORT:-8000}"\n\
echo "========================================="\n\
echo "Starting uvicorn..."\n\
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --log-level debug\n\
' > /app/start.sh && chmod +x /app/start.sh

EXPOSE 8000

CMD ["/app/start.sh"]