FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN python -m pip install --no-cache-dir \
    "fastapi>=0.115.0" \
    "uvicorn>=0.32.0" \
    "httpx>=0.27.0" \
    "pydantic>=2.9.0"

COPY agent /app/agent

EXPOSE 8787

CMD ["python", "-m", "agent.orchestrator"]
