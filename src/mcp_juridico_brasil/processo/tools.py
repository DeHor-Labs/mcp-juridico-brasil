"""Tool MCP: buscar_processo_por_numero.

DISCLAIMER OBRIGATÓRIO (OAB Rec. 001/2024 + Provimento 205/2021):
Esta ferramenta é destinada exclusivamente ao uso por advogados e profissionais
do direito para acompanhamento de processos de seus clientes. Não constitui
consultoria jurídica. A análise final e a orientação ao cliente são de
responsabilidade exclusiva do advogado habilitado.
"""

from __future__ import annotations

from mcp_juridico_brasil._core import (
    JuridicoValidationError,
    get_logger,
)
from mcp_juridico_brasil.datajud.provider import DataJudProvider
from mcp_juridico_brasil.shared.schemas import Processo
from mcp_juridico_brasil.shared.validators import normalizar_numero_cnj, validar_numero_cnj

logger = get_logger(__name__)

_provider = DataJudProvider()

_DISCLAIMER = (
    "AVISO: Esta informação é fornecida para uso exclusivo do advogado responsável. "
    "Não constitui consultoria jurídica. Verifique sempre os dados diretamente no "
    "portal do tribunal antes de tomar qualquer decisão processual."
)


async def buscar_processo_por_numero(
    numero_processo: str,
    tribunal: str | None = None,
) -> dict[str, object]:
    """Busca os dados de um processo judicial pelo número CNJ.

    Consulta a API pública DataJud (CNJ) e retorna metadados do processo,
    classe, assuntos, órgão julgador, partes e histórico de movimentações.

    Cobertura: 91 tribunais (STF, STJ, TST, TSE, STM, TRF1-6, TRTs, TJs
    estaduais, TREs e militares estaduais).

    Args:
        numero_processo: Número no formato CNJ (ex: '0001234-56.2023.8.26.0100')
                         ou sem formatação (20 dígitos).
        tribunal: Sigla do tribunal (ex: 'TJSP', 'TRF4', 'STJ'). Se omitida,
                  o sistema tenta localizar o processo em todos os tribunais
                  (operação mais lenta).

    Returns:
        Dicionário com dados do processo e aviso de responsabilidade.

    Raises:
        JuridicoValidationError: Número CNJ inválido.
        JuridicoSigiloError: Processo em segredo de justiça.
        JuridicoNotFoundError: Processo não localizado.
    """
    if not validar_numero_cnj(numero_processo):
        raise JuridicoValidationError(
            field="numero_processo",
            value=numero_processo,
            reason=(
                "Formato inválido. Use o padrão CNJ: NNNNNNN-DD.AAAA.J.TT.OOOO "
                "ou os 20 dígitos sem formatação."
            ),
        )

    numero_normalizado = normalizar_numero_cnj(numero_processo)
    logger.info("buscar_processo_solicitado", numero=numero_normalizado, tribunal=tribunal)

    processo: Processo = await _provider.buscar_processo(numero_normalizado, tribunal)

    return {
        "processo": processo.model_dump(mode="json"),
        "aviso": _DISCLAIMER,
        "fonte": "DataJud CNJ (API Publica - Portaria CNJ 160/2020)",
        "nota_defasagem": (
            "Os dados refletem o estado registrado no DataJud, que pode ter "
            "atraso de horas a dias em relação ao portal do tribunal de origem."
        ),
    }


__all__ = ["buscar_processo_por_numero"]
