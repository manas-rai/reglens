FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock* LICENSE ./
COPY src/ ./src/

RUN uv sync --no-dev

# Port and agent name are set via environment variables in docker-compose.yml
EXPOSE 8001

CMD ["uv", "run", "python", "-m", "reglens.agents.ingestion.server"]
