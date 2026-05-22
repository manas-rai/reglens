"""Seed the pgvector policies table from the banking control matrix."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow running from project root: uv run python scripts/seed_rag.py
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reglens.observability.logging import configure_logging
from reglens.rag.ingest import ingest_matrix


async def main() -> None:
    configure_logging()
    matrix_path = (
        Path(__file__).parent.parent / "fixtures" / "control_matrices" / "banking.yaml"
    )
    if not matrix_path.exists():
        print(f"Matrix not found: {matrix_path}", file=sys.stderr)
        sys.exit(1)
    count = await ingest_matrix(matrix_path)
    print(f"Seeded {count} policies into pgvector.")


if __name__ == "__main__":
    asyncio.run(main())
