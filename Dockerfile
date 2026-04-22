FROM python:3.11-slim

# Install ffmpeg for chroma-key cutout
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create work_dir for task files
RUN mkdir -p /app/work_dir
EXPOSE ${APP_PORT:-8188}

CMD uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT:-8188}
