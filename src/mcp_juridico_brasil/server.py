"""Servidor MCP Juridico Brasil.

Registra as tools no FastMCP e expoe o servidor via stdio (padrao)
ou HTTP streamable (Smithery/Docker).

Tools expostas (Fase 1 MVP):
- buscar_processo_por_numero  : consulta completa por numero CNJ
- listar_movimentacoes        : historico de andamentos
- resumir_andamento           : dados + instrucao de resumo para o LLM
- monitorar_processo          : verifica atualizacao desde data (polling)
- calcular_proximo_prazo      : estimativa de prazo (stub, completo na Fase 2)
- listar_tribunais            : lista de siglas suportadas

Fases futuras adicionarao tools de webhook push (Fase 3) e
intimacoes DJe (Fase 4) sem quebrar a interface existente.
"""

from __future__ import annotations

import fastmcp

from mcp_juridico_brasil._core import configure_logging, settings
from mcp_juridico_brasil.datajud.tribunais import listar_tribunais as _listar_tribunais
from mcp_juridico_brasil.monitoramento.tools import monitorar_processo
from mcp_juridico_brasil.movimentacoes.tools import listar_movimentacoes
from mcp_juridico_brasil.prazo.tools import calcular_proximo_prazo
from mcp_juridico_brasil.processo.tools import buscar_processo_por_numero
from mcp_juridico_brasil.resumo.tools import resumir_andamento

app = fastmcp.FastMCP(
    name="MCP Juridico Brasil",
    version="0.1.0",
    instructions=(
        "Ferramentas de acompanhamento de processos judiciais brasileiros via DataJud CNJ. "
        "Cobertura de 91 tribunais. Dados com possivel defasagem de T+1 a T+7 dias. "
        "AVISO: Estas ferramentas sao destinadas a advogados e profissionais do direito. "
        "Nao constituem consultoria juridica. A analise final e responsabilidade do "
        "advogado habilitado (OAB Recomendacao 001/2024)."
    ),
)

# --- Tools registradas ---

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


def main() -> None:
    configure_logging(settings.juridico_log_level)
    app.run()


if __name__ == "__main__":
    main()
