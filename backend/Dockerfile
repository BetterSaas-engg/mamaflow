# Mamaflow API — Railway deploy image.
# Build context = backend/ (set the service Root Directory to /backend in Railway).
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first for layer caching; the spaCy model (~600MB, Presidio's
# NER backbone) is baked at build time so cold starts don't download it.
COPY requirements.txt .
RUN pip install -r requirements.txt \
    && python -m spacy download en_core_web_lg

COPY . .

RUN chmod +x start.sh

# Railway injects $PORT; start.sh runs migrations then uvicorn.
CMD ["./start.sh"]
