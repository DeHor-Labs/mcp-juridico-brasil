"""Hierarquia de erros do mcp-juridico-brasil."""

from __future__ import annotations

from typing import Any


class JuridicoError(Exception):
    """Erro base do MCP Juridico Brasil."""

    def __init__(self, message: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class JuridicoValidationError(JuridicoError):
    """Dados de entrada invalidos (numero CNJ malformado, tribunal desconhecido, etc.)."""

    def __init__(self, field: str, value: str, reason: str) -> None:
        super().__init__(
            f"Valor invalido para '{field}': {value!r}. {reason}",
            detail={"field": field, "value": value, "reason": reason},
        )


class JuridicoNotFoundError(JuridicoError):
    """Processo ou recurso nao encontrado na fonte de dados."""

    def __init__(self, numero_processo: str, tribunal: str | None = None) -> None:
        where = f" no tribunal {tribunal}" if tribunal else ""
        super().__init__(
            f"Processo {numero_processo} nao encontrado{where}.",
            detail={"numero_processo": numero_processo, "tribunal": tribunal},
        )


class JuridicoAPIError(JuridicoError):
    """Falha na comunicacao com API externa (DataJud, provider comercial, DJe)."""

    def __init__(self, source: str, status_code: int | None = None, reason: str = "") -> None:
        msg = f"Falha ao acessar {source}"
        if status_code:
            msg += f" (HTTP {status_code})"
        if reason:
            msg += f": {reason}"
        super().__init__(msg, detail={"source": source, "status_code": status_code})


class JuridicoSigiloError(JuridicoError):
    """Processo em segredo de justica - acesso bloqueado por politica de privacidade.

    Este erro DEVE ser propagado ao usuario com mensagem clara. Nao tente contornar
    o sigilo consultando outras fontes ou usando providers comerciais.
    Fundamento legal: art. 189 do CPC e Resolucao CNJ 647/2025.
    """

    def __init__(self, numero_processo: str, nivel_sigilo: int) -> None:
        super().__init__(
            f"O processo {numero_processo} esta em segredo de justica "
            f"(nivel {nivel_sigilo}) e nao pode ser acessado por esta ferramenta. "
            "Acesso restrito as partes e seus advogados via portal do tribunal.",
            detail={"numero_processo": numero_processo, "nivel_sigilo": nivel_sigilo},
        )


__all__ = [
    "JuridicoAPIError",
    "JuridicoError",
    "JuridicoNotFoundError",
    "JuridicoSigiloError",
    "JuridicoValidationError",
]
