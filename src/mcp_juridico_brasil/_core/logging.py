"""Configuracao de logging estruturado com structlog."""

from __future__ import annotations

import logging
from typing import cast

import structlog


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Retorna um logger estruturado para o modulo informado."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))


def configure_logging(level: str = "INFO") -> None:
    """Configura o pipeline do structlog para o ambiente de execucao."""
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, level.upper(), logging.INFO),
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


__all__ = ["configure_logging", "get_logger"]
