"""Tool MCP: resumir_andamento.

Gera um resumo em linguagem natural do andamento processual com base
nas movimentações do DataJud. O resumo é produzido pelo próprio LLM
que invoca esta tool - o MCP retorna os dados estruturados e a instrução
de resumo; não chama um LLM externo (sem dependência de OpenAI/Anthropic).

DISCLAIMER: O resumo é gerado a partir de metadados públicos do DataJud.
Não substitui a leitura integral dos autos pelo advogado responsável.
"""

from __future__ import annotations

from mcp_juridico_brasil._core import JuridicoValidationError, get_logger
from mcp_juridico_brasil.datajud.provider import DataJudProvider
from mcp_juridico_brasil.shared.validators import normalizar_numero_cnj, validar_numero_cnj

logger = get_logger(__name__)
_provider = DataJudProvider()

_INSTRUCAO_RESUMO = """
Com base nos dados estruturados do processo acima, produza um resumo objetivo
em linguagem jurídica acessível contendo:
1. Identificação do processo (tribunal, classe, assunto principal, órgão julgador).
2. Status atual (última movimentação e seu significado prático).
3. Histórico resumido das últimas movimentações em ordem cronológica.
4. Pontos de atenção que o advogado deve verificar no portal do tribunal.

Mantenha tom técnico-jurídico. Não emita opinião sobre o mérito da causa.
Não faça previsões de resultado. Se algum dado estiver ausente, indique
'não disponível via DataJud' e oriente o advogado a consultar o portal do tribunal.
"""


async def resumir_andamento(
    numero_processo: str,
    tribunal: str | None = None,
) -> dict[str, object]:
    """Retorna dados estruturados de um processo para geração de resumo pelo LLM.

    Esta tool busca o processo no DataJud e devolve os dados formatados
    junto com instruções para que o modelo gere o resumo em linguagem natural.
    O processamento semântico (resumo) fica no modelo, não no MCP.

    Args:
        numero_processo: Número no formato CNJ.
        tribunal: Sigla do tribunal. Se omitida, o sistema pesquisa em todos.

    Returns:
        Dados do processo + instrução de resumo para o modelo.
    """
    if not validar_numero_cnj(numero_processo):
        raise JuridicoValidationError(
            field="numero_processo",
            value=numero_processo,
            reason="Formato inválido. Use o padrão CNJ: NNNNNNN-DD.AAAA.J.TT.OOOO.",
        )

    numero_normalizado = normalizar_numero_cnj(numero_processo)
    logger.info("resumir_andamento_solicitado", numero=numero_normalizado)

    processo = await _provider.buscar_processo(numero_normalizado, tribunal)

    return {
        "dados_processo": processo.model_dump(mode="json"),
        "instrucao_resumo": _INSTRUCAO_RESUMO.strip(),
        "aviso": (
            "AVISO LEGAL: Este resumo é gerado a partir de metadados públicos "
            "do DataJud CNJ com possível defasagem. Não constitui consultoria jurídica "
            "nem substitui a leitura integral dos autos pelo advogado responsável. "
            "Fundamento: OAB Recomendação 001/2024."
        ),
        "fonte": "DataJud CNJ (API Pública)",
    }


__all__ = ["resumir_andamento"]
