FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN python -m pip install --no-cache-dir \
    "fastapi>=0.115.0" \
    "uvicorn>=0.32.0" \
    "websockets>=15.0" \
    "httpx>=0.27.0" \
    "pydantic>=2.9.0" \
    "pyyaml>=6.0.2" \
    "nbtlib>=2.0.4" \
    "litemapy>=0.10.0b0"

COPY companion /app/companion
COPY protocol /app/protocol
COPY evals /app/evals
COPY skills /app/skills
# Shared litematic → FAWE Schematic-root .schem converter (ops /ai ingest).
COPY scripts/__init__.py /app/scripts/__init__.py
COPY scripts/schem_pipeline/__init__.py /app/scripts/schem_pipeline/__init__.py
COPY scripts/schem_pipeline/convert.py /app/scripts/schem_pipeline/convert.py

EXPOSE 8787

CMD ["python", "-m", "companion.app"]
