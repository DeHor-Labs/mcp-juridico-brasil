"""Tool MCP: listar_movimentacoes."""

from __future__ import annotations

from mcp_juridico_brasil._core import JuridicoValidationError, get_logger
from mcp_juridico_brasil.datajud.provider import DataJudProvider
from mcp_juridico_brasil.shared.validators import normalizar_numero_cnj, validar_numero_cnj

logger = get_logger(__name__)
_provider = DataJudProvider()


async def listar_movimentacoes(
    numero_processo: str,
    tribunal: str,
    limite: int = 20,
) -> dict[str, object]:
    """Lista as movimentações mais recentes de um processo judicial.

    Retorna o histórico de andamentos com código TPU, nome e data/hora,
    ordenado do mais recente para o mais antigo.

    Args:
        numero_processo: Número no formato CNJ.
        tribunal: Sigla do tribunal (obrigatória nesta tool para evitar
                  varredura de todos os índices).
        limite: Número máximo de movimentações a retornar (padrão 20, max 50).

    Returns:
        Lista de movimentações com metadados.
    """
    if not validar_numero_cnj(numero_processo):
        raise JuridicoValidationError(
            field="numero_processo",
            value=numero_processo,
            reason="Formato inválido. Use o padrão CNJ: NNNNNNN-DD.AAAA.J.TT.OOOO.",
        )

    limite = min(max(1, limite), 50)
    numero_normalizado = normalizar_numero_cnj(numero_processo)
    logger.info("listar_movimentacoes_solicitado", numero=numero_normalizado, tribunal=tribunal)

    movs = await _provider.listar_movimentacoes(numero_normalizado, tribunal, limite)

    return {
        "numero_processo": numero_normalizado,
        "tribunal": tribunal,
        "total_retornado": len(movs),
        "movimentacoes": [m.model_dump(mode="json") for m in movs],
        "nota": (
            "Movimentações refletem o DataJud com possível defasagem de T+1 a T+7 dias. "
            "Consulte o portal do tribunal para dados em tempo real."
        ),
    }


__all__ = ["listar_movimentacoes"]
