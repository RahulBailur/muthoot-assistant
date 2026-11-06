# Build from the repository root:  docker build -f backend/Dockerfile .

# --- Stage 1: build the React app ---------------------------------------------------------
FROM node:24-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- Stage 2: the FastAPI app, which also serves the built frontend -----------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    FRONTEND_BUILD_DIR=/app/frontend/build \
    SILERO_VAD_MODEL=/app/models/silero_vad_v6.onnx \
    FASTEMBED_CACHE_PATH=/models/fastembed

WORKDIR /app/backend

# Dependencies first, so editing application code does not reinstall them
COPY backend/pyproject.toml ./
# The base dependencies plus the ml (intent embeddings) and voice (Silero VAD) extras
RUN python -c "import tomllib; p = tomllib.load(open('pyproject.toml', 'rb'))['project']; o = p['optional-dependencies']; print('\n'.join(p['dependencies'] + o['ml'] + o['voice']))" > /tmp/requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

COPY backend/ ./
COPY --from=frontend /frontend/build /app/frontend/build

# The Silero VAD model (about 1 MB) is part of the image; the embedding model is downloaded
# on first use into /models, which Compose keeps on a volume so it survives rebuilds
RUN JWT_SECRET=build-only python -m scripts.get_vad_model \
    && useradd --system --no-create-home goldloan \
    && mkdir -p /models && chown goldloan /models
# The app user has no home directory, so the Hugging Face download cache goes to the volume too
ENV HF_HOME=/models/huggingface
USER goldloan

# Hosts such as Render say which port to listen on in $PORT; 8000 otherwise
EXPOSE 8000
# No HEALTHCHECK here: each check starts a Python process, and on a host with a tenth of a
# CPU they pile up and starve the app. Compose defines one; Render polls /api/health itself.

# One worker on purpose: Socket.IO rooms live in this process
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
