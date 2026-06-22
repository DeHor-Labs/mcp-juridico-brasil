"""Provider DataJud CNJ - implementacao concreta da interface ProcessoProvider."""

from .client import DataJudClient
from .provider import DataJudProvider

__all__ = ["DataJudClient", "DataJudProvider"]
