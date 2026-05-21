FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv==0.9.18 || pip install --no-cache-dir uv

# Copy dependency files first (layer caching)
COPY pyproject.toml uv.lock* LICENSE README.md alembic.ini ./
COPY src/ ./src/

# Install project with all extras
RUN uv sync --no-dev

# Create uploads directory
RUN mkdir -p /app/uploads

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "reglens.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
