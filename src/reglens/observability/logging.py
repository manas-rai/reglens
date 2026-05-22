"""Non-blocking structured JSON logging.

Uses stdlib logging with a QueueHandler so log I/O never blocks the
event loop or request thread. JSON serialization happens in a dedicated
background thread via QueueListener.
"""

from __future__ import annotations

import logging
import logging.handlers
import queue
import sys

from pythonjsonlogger import jsonlogger

_listener: logging.handlers.QueueListener | None = None


def configure_logging(level: str = "INFO") -> None:
    """Configure root logger with non-blocking JSON output to stdout.

    Safe to call multiple times (idempotent after the first call).
    Call shutdown_logging() on process exit to flush the queue.
    """
    global _listener
    if _listener is not None:
        return

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = jsonlogger.JsonFormatter(  # type: ignore[attr-defined]
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        rename_fields={"asctime": "ts", "name": "logger", "levelname": "level"},
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    # QueueHandler returns in ~1 μs; the listener drains it on a background thread.
    log_queue: queue.SimpleQueue[logging.LogRecord] = queue.SimpleQueue()
    queue_handler = logging.handlers.QueueHandler(log_queue)
    root.handlers = [queue_handler]

    _listener = logging.handlers.QueueListener(
        log_queue,
        stream_handler,
        respect_handler_level=True,
    )
    _listener.start()

    for name in (
        "httpx",
        "httpcore",
        "hpack",
        "grpc",
        "sqlalchemy.engine",  # hides BEGIN/COMMIT/SQL statements
        "sqlalchemy.pool",  # hides connection pool chatter
        "langgraph",  # hides internal LangGraph state transitions
        "uvicorn.access",  # hides per-request access logs (use OTel instead)
    ):
        logging.getLogger(name).setLevel(logging.WARNING)


def shutdown_logging() -> None:
    """Flush and stop the background listener. Call on process exit."""
    global _listener
    if _listener is not None:
        _listener.stop()
        _listener = None
