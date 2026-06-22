"""Tool MCP: resumir_andamento.

Gera um resumo em linguagem natural do andamento processual com base
nas movimentacoes do DataJud. O resumo e produzido pelo proprio LLM
que invoca esta tool - o MCP retorna os dados estruturados e a instrucao
de resumo; nao chama um LLM externo (sem dependencia de OpenAI/Anthropic).

DISCLAIMER: O resumo e gerado a partir de metadados publicos do DataJud.
Nao substitui a leitura integral dos autos pelo advogado responsavel.
"""

from __future__ import annotations

from mcp_juridico_brasil._core import JuridicoValidationError, get_logger
from mcp_juridico_brasil.datajud.provider import DataJudProvider
from mcp_juridico_brasil.shared.validators import normalizar_numero_cnj, validar_numero_cnj

logger = get_logger(__name__)
_provider = DataJudProvider()

_INSTRUCAO_RESUMO = """
Com base nos dados estruturados do processo acima, produza um resumo objetivo
em linguagem juridica acessivel contendo:
1. Identificacao do processo (tribunal, classe, assunto principal, orgao julgador).
2. Status atual (ultima movimentacao e seu significado pratico).
3. Historico resumido das ultimas movimentacoes em ordem cronologica.
4. Pontos de atencao que o advogado deve verificar no portal do tribunal.

Mantenha tom tecnico-juridico. Nao emita opiniao sobre o merito da causa.
Nao faca previsoes de resultado. Se algum dado estiver ausente, indique
'nao disponivel via DataJud' e oriente o advogado a consultar o portal do tribunal.
"""


async def resumir_andamento(
    numero_processo: str,
    tribunal: str | None = None,
) -> dict[str, object]:
    """Retorna dados estruturados de um processo para geracao de resumo pelo LLM.

    Esta tool busca o processo no DataJud e devolve os dados formatados
    junto com instrucoes para que o modelo gere o resumo em linguagem natural.
    O processamento semantico (resumo) fica no modelo, nao no MCP.

    Args:
        numero_processo: Numero no formato CNJ.
        tribunal: Sigla do tribunal. Se omitida, o sistema pesquisa em todos.

    Returns:
        Dados do processo + instrucao de resumo para o modelo.
    """
    if not validar_numero_cnj(numero_processo):
        raise JuridicoValidationError(
            field="numero_processo",
            value=numero_processo,
            reason="Formato invalido. Use o padrao CNJ: NNNNNNN-DD.AAAA.J.TT.OOOO.",
        )

    numero_normalizado = normalizar_numero_cnj(numero_processo)
    logger.info("resumir_andamento_solicitado", numero=numero_normalizado)

    processo = await _provider.buscar_processo(numero_normalizado, tribunal)

    return {
        "dados_processo": processo.model_dump(mode="json"),
        "instrucao_resumo": _INSTRUCAO_RESUMO.strip(),
        "aviso": (
            "AVISO LEGAL: Este resumo e gerado a partir de metadados publicos "
            "do DataJud CNJ com possivel defasagem. Nao constitui consultoria juridica "
            "nem substitui a leitura integral dos autos pelo advogado responsavel. "
            "Fundamento: OAB Recomendacao 001/2024."
        ),
        "fonte": "DataJud CNJ (API Publica)",
    }


__all__ = ["resumir_andamento"]
