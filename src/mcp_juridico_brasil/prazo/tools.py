"""Tool MCP: calcular_proximo_prazo.

Fase 2: calculo de prazos processuais com base na ultima movimentacao.

IMPORTANTE: Calculo de prazos processuais e materia tecnico-juridica complexa
que depende do tipo de ato, regras do tribunal, feriados locais e sustoensao de
prazo (ex.: recesso forense, pandemia). Esta tool fornece estimativa inicial
como apoio ao advogado, que DEVE verificar o prazo no portal do tribunal e
na legislacao aplicavel antes de qualquer decisao.

Implementacao atual (Fase 1/2): stub com logica basica de dias corridos.
Fase 2 completa: integrar tabela de prazos CPC, feriados por UF e suspensoes.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from mcp_juridico_brasil._core import JuridicoValidationError, get_logger
from mcp_juridico_brasil.datajud.provider import DataJudProvider
from mcp_juridico_brasil.shared.validators import normalizar_numero_cnj, validar_numero_cnj

logger = get_logger(__name__)
_provider = DataJudProvider()

# Prazos CPC mais comuns em dias uteis (simplificado - Fase 2 expande)
_PRAZOS_CPC: dict[str, int] = {
    "Contestacao": 15,
    "Recurso de Apelacao": 15,
    "Agravo Regimental": 15,
    "Embargos de Declaracao": 5,
    "Recurso Especial": 15,
    "Recurso Extraordinario": 15,
    "Contrarrazoes": 15,
    "Manifestacao": 15,
    "Impugnacao": 15,
}

_AVISO_PRAZO = (
    "ATENCAO: Este calculo e uma estimativa preliminar baseada em dias corridos "
    "a partir da ultima movimentacao no DataJud. NAO considera feriados locais, "
    "suspensoes de prazo, recesso forense nem as especificidades do ato processual. "
    "O advogado responsavel DEVE verificar o prazo efetivo no portal do tribunal "
    "e na legislacao aplicavel. O uso indevido desta estimativa e de responsabilidade "
    "exclusiva do profissional. (OAB Rec. 001/2024)"
)


async def calcular_proximo_prazo(
    numero_processo: str,
    tribunal: str,
    tipo_ato: str | None = None,
) -> dict[str, object]:
    """Estima o proximo prazo processual com base na ultima movimentacao.

    STUB - implementacao completa na Fase 2.

    Args:
        numero_processo: Numero no formato CNJ.
        tribunal: Sigla do tribunal.
        tipo_ato: Tipo do ato para calculo de prazo (ex: 'Contestacao',
                  'Recurso de Apelacao'). Se omitido, usa prazo padrao de 15 dias.

    Returns:
        Estimativa de prazo com aviso de responsabilidade.
    """
    if not validar_numero_cnj(numero_processo):
        raise JuridicoValidationError(
            field="numero_processo",
            value=numero_processo,
            reason="Formato invalido. Use o padrao CNJ: NNNNNNN-DD.AAAA.J.TT.OOOO.",
        )

    numero_normalizado = normalizar_numero_cnj(numero_processo)
    logger.info("calcular_prazo_solicitado", numero=numero_normalizado, tipo_ato=tipo_ato)

    processo = await _provider.buscar_processo(numero_normalizado, tribunal)
    ultima_mov = processo.movimentacoes[0] if processo.movimentacoes else None

    if not ultima_mov:
        return {
            "numero_processo": numero_normalizado,
            "tribunal": tribunal,
            "prazo_estimado": None,
            "motivo": "Nenhuma movimentacao disponivel no DataJud para calcular prazo.",
            "aviso": _AVISO_PRAZO,
        }

    dias = _PRAZOS_CPC.get(tipo_ato or "", 15)
    data_referencia = ultima_mov.data_hora
    prazo_estimado = data_referencia + timedelta(days=dias)

    return {
        "numero_processo": numero_normalizado,
        "tribunal": tribunal,
        "ultima_movimentacao": ultima_mov.model_dump(mode="json"),
        "tipo_ato": tipo_ato or "padrao (15 dias corridos)",
        "dias_prazo_estimado": dias,
        "data_referencia_iso": data_referencia.isoformat(),
        "prazo_estimado_iso": prazo_estimado.isoformat(),
        "prazo_estimado_legivel": prazo_estimado.strftime("%d/%m/%Y"),
        "status_prazo": (
            "VENCIDO"
            if prazo_estimado < datetime.now(tz=data_referencia.tzinfo)
            else "EM ABERTO (estimativa)"
        ),
        "aviso": _AVISO_PRAZO,
        "limitacao": (
            "STUB Fase 1 - calculo em dias corridos sem feriados. "
            "Fase 2 implementa calendario forense por UF e tabela completa CPC."
        ),
    }


__all__ = ["calcular_proximo_prazo"]
