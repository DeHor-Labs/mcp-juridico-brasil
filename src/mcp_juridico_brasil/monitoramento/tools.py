"""Tool MCP: monitorar_processo.

Fase 2: verifica se houve atualizacao desde uma data de referencia.
Fase 3 (provider comercial): substituir polling por webhook push.
"""

from __future__ import annotations

from datetime import datetime

from mcp_juridico_brasil._core import JuridicoValidationError, get_logger
from mcp_juridico_brasil.datajud.provider import DataJudProvider
from mcp_juridico_brasil.shared.validators import normalizar_numero_cnj, validar_numero_cnj

logger = get_logger(__name__)
_provider = DataJudProvider()


async def monitorar_processo(
    numero_processo: str,
    tribunal: str,
    desde_iso: str,
) -> dict[str, object]:
    """Verifica se um processo teve atualizacao apos a data informada.

    Implementacao Fase 2: polling via DataJud (sem tempo real).
    Fase 3 substituira por notificacao push via provider comercial.

    Args:
        numero_processo: Numero no formato CNJ.
        tribunal: Sigla do tribunal (obrigatoria para monitoramento).
        desde_iso: Data/hora de referencia em formato ISO 8601
                   (ex: '2024-01-15T08:00:00').

    Returns:
        Dicionario indicando se houve atualizacao e a data da ultima.
    """
    if not validar_numero_cnj(numero_processo):
        raise JuridicoValidationError(
            field="numero_processo",
            value=numero_processo,
            reason="Formato invalido. Use o padrao CNJ: NNNNNNN-DD.AAAA.J.TT.OOOO.",
        )

    try:
        datetime.fromisoformat(desde_iso)
    except ValueError as exc:
        raise JuridicoValidationError(
            field="desde_iso",
            value=desde_iso,
            reason="Data invalida. Use formato ISO 8601: YYYY-MM-DDTHH:MM:SS",
        ) from exc

    numero_normalizado = normalizar_numero_cnj(numero_processo)
    logger.info(
        "monitorar_processo_solicitado",
        numero=numero_normalizado,
        tribunal=tribunal,
        desde=desde_iso,
    )

    houve_atualizacao = await _provider.verificar_atualizacao(
        numero_normalizado, tribunal, desde_iso
    )

    processo = await _provider.buscar_processo(numero_normalizado, tribunal)
    ultima = (
        processo.data_ultima_atualizacao.isoformat() if processo.data_ultima_atualizacao else None
    )

    return {
        "numero_processo": numero_normalizado,
        "tribunal": tribunal,
        "desde": desde_iso,
        "houve_atualizacao": houve_atualizacao,
        "data_ultima_atualizacao_datajud": ultima,
        "aviso_defasagem": (
            "O DataJud pode ter atraso de T+1 a T+7 dias. "
            "Para monitoramento de prazos criticos, use um provider comercial "
            "com webhook (Fase 3) ou acesse diretamente o portal do tribunal."
        ),
    }


__all__ = ["monitorar_processo"]
