FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock* ./
COPY src/ ./src/

RUN uv sync --no-dev

EXPOSE 8010

CMD ["uv", "run", "python", "-m", "reglens.supervisor.server"]
