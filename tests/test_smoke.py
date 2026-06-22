"""Testes de smoke para cli.py, server.py e cobertura de provider.py.

Garante que os pontos de entrada do pacote inicializam sem erros e que
os caminhos criticos do DataJudProvider estao cobertos.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import fastmcp
import pytest

from mcp_juridico_brasil._core.errors import JuridicoValidationError
from mcp_juridico_brasil.shared.schemas import Movimentacao, Processo

# ---------------------------------------------------------------------------
# Fixtures compartilhadas
# ---------------------------------------------------------------------------

NUMERO = "00012345620238260100"
TRIBUNAL = "TJSP"


def _processo_com_atualizacao() -> Processo:
    return Processo(
        numero_processo=NUMERO,
        tribunal=TRIBUNAL,
        nivel_sigilo=0,
        data_ultima_atualizacao=datetime(2024, 6, 10, 12, 0, tzinfo=timezone.utc),
        movimentacoes=[
            Movimentacao(
                codigo=1,
                nome="Despacho",
                data_hora=datetime(2024, 6, 10, 12, 0, tzinfo=timezone.utc),
            )
        ],
    )


def _processo_sem_atualizacao() -> Processo:
    return Processo(
        numero_processo=NUMERO,
        tribunal=TRIBUNAL,
        nivel_sigilo=0,
        data_ultima_atualizacao=None,
    )


# ---------------------------------------------------------------------------
# Smoke: server.py
# ---------------------------------------------------------------------------


def test_server_app_e_fastmcp() -> None:
    """server.app deve ser instancia de FastMCP com as tools registradas."""
    from mcp_juridico_brasil.server import app

    assert isinstance(app, fastmcp.FastMCP)


def test_server_tools_registradas() -> None:
    """As 6 tools do MVP devem estar registradas no servidor."""
    import asyncio

    from mcp_juridico_brasil.server import app

    tools = asyncio.run(app.list_tools())
    nomes = {tool.name for tool in tools}
    esperadas = {
        "buscar_processo_por_numero",
        "listar_movimentacoes",
        "resumir_andamento",
        "monitorar_processo",
        "calcular_proximo_prazo",
        "listar_tribunais",
    }
    assert esperadas.issubset(nomes), f"Tools ausentes: {esperadas - nomes}"


# ---------------------------------------------------------------------------
# Smoke: cli.py
# ---------------------------------------------------------------------------


def test_cli_app_criado() -> None:
    """cli.app deve ser instancia de typer.Typer."""
    import typer

    from mcp_juridico_brasil.cli import app

    assert isinstance(app, typer.Typer)


def test_cli_tem_comandos_esperados() -> None:
    """CLI deve ter os comandos serve, version e tribunais."""
    from mcp_juridico_brasil.cli import app

    # typer armazena name=None quando nao explicitado; usar callback.__name__
    nomes = {(cmd.name or cmd.callback.__name__) for cmd in app.registered_commands if cmd.callback}
    assert "serve" in nomes
    assert "version" in nomes
    assert "tribunais" in nomes


# ---------------------------------------------------------------------------
# DataJudProvider: buscar_processo sem tribunal (multiplos tribunais)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provider_busca_sem_tribunal_chama_multiplos() -> None:
    """buscar_processo sem tribunal deve delegar para buscar_por_numero_multiplos_tribunais."""
    from mcp_juridico_brasil.datajud.provider import DataJudProvider

    provider = DataJudProvider()
    processo_esperado = _processo_com_atualizacao()

    with patch.object(
        provider._client,
        "buscar_por_numero_multiplos_tribunais",
        new_callable=AsyncMock,
        return_value=processo_esperado,
    ) as mock_multi:
        resultado = await provider.buscar_processo(NUMERO, tribunal=None)

    mock_multi.assert_called_once_with(NUMERO)
    assert resultado.numero_processo == NUMERO


@pytest.mark.asyncio
async def test_provider_busca_com_tribunal_chama_por_numero() -> None:
    """buscar_processo com tribunal deve delegar para buscar_por_numero."""
    from mcp_juridico_brasil.datajud.provider import DataJudProvider

    provider = DataJudProvider()
    processo_esperado = _processo_com_atualizacao()

    with patch.object(
        provider._client,
        "buscar_por_numero",
        new_callable=AsyncMock,
        return_value=processo_esperado,
    ) as mock_buscar:
        resultado = await provider.buscar_processo(NUMERO, tribunal=TRIBUNAL)

    mock_buscar.assert_called_once_with(NUMERO, TRIBUNAL)
    assert resultado.numero_processo == NUMERO


# ---------------------------------------------------------------------------
# DataJudProvider: verificar_atualizacao - caminhos cobertos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verificar_atualizacao_retorna_true_quando_atualizado() -> None:
    """verificar_atualizacao deve retornar True quando data_ultima > desde."""
    from mcp_juridico_brasil.datajud.provider import DataJudProvider

    provider = DataJudProvider()

    with patch.object(
        provider._client,
        "buscar_por_numero",
        new_callable=AsyncMock,
        return_value=_processo_com_atualizacao(),
    ):
        resultado = await provider.verificar_atualizacao(NUMERO, TRIBUNAL, "2024-01-01T00:00:00")

    assert resultado is True


@pytest.mark.asyncio
async def test_verificar_atualizacao_retorna_false_quando_nao_atualizado() -> None:
    """verificar_atualizacao deve retornar False quando data_ultima <= desde."""
    from mcp_juridico_brasil.datajud.provider import DataJudProvider

    provider = DataJudProvider()

    with patch.object(
        provider._client,
        "buscar_por_numero",
        new_callable=AsyncMock,
        return_value=_processo_com_atualizacao(),
    ):
        resultado = await provider.verificar_atualizacao(NUMERO, TRIBUNAL, "2025-01-01T00:00:00")

    assert resultado is False


@pytest.mark.asyncio
async def test_verificar_atualizacao_retorna_false_sem_data() -> None:
    """verificar_atualizacao deve retornar False quando data_ultima_atualizacao e None."""
    from mcp_juridico_brasil.datajud.provider import DataJudProvider

    provider = DataJudProvider()

    with patch.object(
        provider._client,
        "buscar_por_numero",
        new_callable=AsyncMock,
        return_value=_processo_sem_atualizacao(),
    ):
        resultado = await provider.verificar_atualizacao(NUMERO, TRIBUNAL, "2024-01-01T00:00:00")

    assert resultado is False


@pytest.mark.asyncio
async def test_verificar_atualizacao_naive_iso_tratado_como_utc() -> None:
    """desde_iso sem offset deve ser interpretado como UTC (sem TypeError)."""
    from mcp_juridico_brasil.datajud.provider import DataJudProvider

    provider = DataJudProvider()

    # data_ultima_atualizacao = 2024-06-10 (aware UTC)
    # desde = "2024-01-01T00:00:00" (naive) -> deve ser tratado como UTC sem erro
    with patch.object(
        provider._client,
        "buscar_por_numero",
        new_callable=AsyncMock,
        return_value=_processo_com_atualizacao(),
    ):
        # Nao deve lancar TypeError
        resultado = await provider.verificar_atualizacao(NUMERO, TRIBUNAL, "2024-01-01T00:00:00")

    assert resultado is True


# ---------------------------------------------------------------------------
# monitoramento/tools: validacao de desde_iso invalido
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_monitorar_processo_desde_iso_invalido_lanca_validation_error() -> None:
    """desde_iso malformado deve lancar JuridicoValidationError com field=desde_iso."""
    from mcp_juridico_brasil.monitoramento.tools import monitorar_processo

    with pytest.raises(JuridicoValidationError) as exc_info:
        await monitorar_processo(
            "0001234-56.2023.8.26.0100",
            TRIBUNAL,
            "nao-e-uma-data",
        )

    assert exc_info.value.detail["field"] == "desde_iso"
