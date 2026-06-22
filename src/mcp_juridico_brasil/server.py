"""Servidor MCP Jurídico Brasil.

Registra tools e resources no FastMCP e expõe o servidor via stdio (padrão)
ou HTTP streamable (Smithery/Docker).

Tools expostas (Fase 2):
- buscar_processo_por_numero  : consulta completa por número CNJ
- listar_movimentacoes        : histórico de andamentos
- resumir_andamento           : dados + instrução de resumo para o LLM
- monitorar_processo          : verifica atualização desde data (polling)
- calcular_proximo_prazo      : cálculo em dias úteis com calendário forense
- listar_processos_monitorados: lista processos com snapshot em memória
- listar_tribunais            : lista de siglas suportadas

Resources expostos (Fase 2):
- processo://{numero_processo}/snapshot  : último snapshot do processo

Fases futuras adicionarão tools de webhook push (Fase 3) e
intimações DJe (Fase 4) sem quebrar a interface existente.
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
        "Cobertura de 91 tribunais. Dados com possível defasagem de T+1 a T+7 dias. "
        "Fase 2: cálculo de prazos em dias úteis (art. 219/220/224 CPC) com calendário "
        "forense nacional e estadual. "
        "AVISO: Estas ferramentas são destinadas a advogados e profissionais do direito. "
        "Não constituem consultoria jurídica. A análise final é responsabilidade do "
        "advogado habilitado (OAB Recomendação 001/2024)."
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

    Retorna siglas que podem ser usadas no parâmetro 'tribunal' das demais tools.
    """
    tribunais = _listar_tribunais()
    return {
        "total": len(tribunais),
        "tribunais": tribunais,
        "nota": (
            "Siglas baseadas no cadastro DataJud CNJ (Portaria 160/2020). "
            "Use exatamente estas siglas no parâmetro 'tribunal' das demais tools."
        ),
    }


@app.tool()
async def listar_processos_monitorados() -> dict[str, object]:
    """Lista processos com snapshot em memória na sessão atual.

    Retorna os números de processos que tiveram snapshot salvo nesta sessão.
    Use o resource processo://{numero}/snapshot para ler os dados completos.

    Returns:
        Dicionário com lista de números e total.
    """
    numeros = _listar_monitorados()
    return {
        "total": len(numeros),
        "processos": numeros,
        "nota": (
            "Snapshots em memória da sessão MCP atual. "
            "O estado é perdido ao reiniciar o servidor. "
            "Configure JURIDICO_SNAPSHOT_DIR para persistência em arquivo."
        ),
    }


# ---------------------------------------------------------------------------
# Resources MCP (Fase 2)
# ---------------------------------------------------------------------------


@app.resource("processo://{numero_processo}/snapshot")
async def resource_snapshot_processo(numero_processo: str) -> str:
    """Snapshot mais recente de um processo monitorado.

    Retorna os dados capturados na última chamada a monitorar_processo
    ou buscar_processo_por_numero para este número de processo.

    Args:
        numero_processo: Número CNJ do processo (normalizado, sem formatação).

    Returns:
        JSON com dados do snapshot ou mensagem de ausência.
    """
    snapshot = obter_snapshot(numero_processo)
    if snapshot is None:
        return json.dumps(
            {
                "encontrado": False,
                "numero_processo": numero_processo,
                "mensagem": (
                    "Nenhum snapshot disponível para este processo. "
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
