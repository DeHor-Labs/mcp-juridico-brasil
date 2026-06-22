"""Servidor MCP Juridico Brasil.

Registra tools e resources no FastMCP e expoe o servidor via stdio (padrao)
ou HTTP streamable (Smithery/Docker).

Tools expostas (Fase 2):
- buscar_processo_por_numero  : consulta completa por numero CNJ
- listar_movimentacoes        : historico de andamentos
- resumir_andamento           : dados + instrucao de resumo para o LLM
- monitorar_processo          : verifica atualizacao desde data (polling)
- calcular_proximo_prazo      : calculo em dias uteis com calendario forense
- listar_processos_monitorados: lista processos com snapshot em memoria
- listar_tribunais            : lista de siglas suportadas

Resources expostos (Fase 2):
- processo://{numero_processo}/snapshot  : ultimo snapshot do processo

Fases futuras adicionarao tools de webhook push (Fase 3) e
intimacoes DJe (Fase 4) sem quebrar a interface existente.
"""

from __future__ import annotations

import json

import fastmcp

from mcp_juridico_brasil._core import configure_logging, settings
from mcp_juridico_brasil.datajud.tribunais import listar_tribunais as _listar_tribunais
from mcp_juridico_brasil.monitoramento.store import (
    listar_processos_monitorados as _listar_monitorados,
)
from mcp_juridico_brasil.monitoramento.store import (
    obter_snapshot,
)
from mcp_juridico_brasil.monitoramento.tools import monitorar_processo
from mcp_juridico_brasil.movimentacoes.tools import listar_movimentacoes
from mcp_juridico_brasil.prazo.tools import calcular_proximo_prazo
from mcp_juridico_brasil.processo.tools import buscar_processo_por_numero
from mcp_juridico_brasil.resumo.tools import resumir_andamento

app = fastmcp.FastMCP(
    name="MCP Juridico Brasil",
    version="0.2.0",
    instructions=(
        "Ferramentas de acompanhamento de processos judiciais brasileiros via DataJud CNJ. "
        "Cobertura de 91 tribunais. Dados com possivel defasagem de T+1 a T+7 dias. "
        "Fase 2: calculo de prazos em dias uteis (art. 219/220/224 CPC) com calendario "
        "forense nacional e estadual. "
        "AVISO: Estas ferramentas sao destinadas a advogados e profissionais do direito. "
        "Nao constituem consultoria juridica. A analise final e responsabilidade do "
        "advogado habilitado (OAB Recomendacao 001/2024)."
    ),
)

# ---------------------------------------------------------------------------
# Tools registradas
# ---------------------------------------------------------------------------

app.tool()(buscar_processo_por_numero)
app.tool()(listar_movimentacoes)
app.tool()(resumir_andamento)
app.tool()(monitorar_processo)
app.tool()(calcular_proximo_prazo)


@app.tool()
async def listar_tribunais() -> dict[str, object]:
    """Lista todos os tribunais suportados pelo MCP (91 ao total).

    Retorna siglas que podem ser usadas no parametro 'tribunal' das demais tools.
    """
    tribunais = _listar_tribunais()
    return {
        "total": len(tribunais),
        "tribunais": tribunais,
        "nota": (
            "Siglas baseadas no cadastro DataJud CNJ (Portaria 160/2020). "
            "Use exatamente estas siglas no parametro 'tribunal' das demais tools."
        ),
    }


@app.tool()
async def listar_processos_monitorados() -> dict[str, object]:
    """Lista processos com snapshot em memoria na sessao atual.

    Retorna os numeros de processos que tiveram snapshot salvo nesta sessao.
    Use o resource processo://{numero}/snapshot para ler os dados completos.

    Returns:
        Dicionario com lista de numeros e total.
    """
    numeros = _listar_monitorados()
    return {
        "total": len(numeros),
        "processos": numeros,
        "nota": (
            "Snapshots em memoria da sessao MCP atual. "
            "O estado e perdido ao reiniciar o servidor. "
            "Configure JURIDICO_SNAPSHOT_DIR para persistencia em arquivo."
        ),
    }


# ---------------------------------------------------------------------------
# Resources MCP (Fase 2)
# ---------------------------------------------------------------------------


@app.resource("processo://{numero_processo}/snapshot")
async def resource_snapshot_processo(numero_processo: str) -> str:
    """Snapshot mais recente de um processo monitorado.

    Retorna os dados capturados na ultima chamada a monitorar_processo
    ou buscar_processo_por_numero para este numero de processo.

    Args:
        numero_processo: Numero CNJ do processo (normalizado, sem formatacao).

    Returns:
        JSON com dados do snapshot ou mensagem de ausencia.
    """
    snapshot = obter_snapshot(numero_processo)
    if snapshot is None:
        return json.dumps(
            {
                "encontrado": False,
                "numero_processo": numero_processo,
                "mensagem": (
                    "Nenhum snapshot disponivel para este processo. "
                    "Chame buscar_processo_por_numero ou monitorar_processo primeiro."
                ),
            },
            ensure_ascii=False,
        )
    return json.dumps(
        {"encontrado": True, **snapshot},
        ensure_ascii=False,
        default=str,
        indent=2,
    )


def main() -> None:
    configure_logging(settings.juridico_log_level)
    app.run()


if __name__ == "__main__":
    main()
