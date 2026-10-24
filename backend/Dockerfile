FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FASTEMBED_CACHE_PATH=/opt/fastembed \
    HF_HUB_DISABLE_TELEMETRY=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/opt/fastembed')"

COPY backend /app/backend
COPY examples /app/examples

ENV PYTHONPATH=/app/backend
EXPOSE 8000

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "backend"]
