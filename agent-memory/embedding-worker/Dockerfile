FROM docker.m.daocloud.io/python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models/huggingface \
    TRANSFORMERS_CACHE=/models/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/models/sentence-transformers

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
      --index-url https://download.pytorch.org/whl/cpu \
      torch==2.6.0

RUN pip install --no-cache-dir \
      fastapi==0.115.6 \
      uvicorn==0.34.0 \
      sentence-transformers==3.3.1 \
      sentencepiece==0.2.0 \
      FlagEmbedding==1.3.5 \
      qdrant-client==1.12.1

WORKDIR /work
COPY backend.py build_vectors.py import_vectors.py server.py /work/

ENTRYPOINT ["python", "/work/build_vectors.py"]
