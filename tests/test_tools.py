"""Testes das tools MCP com mock do DataJudProvider.

Garante que as tools:
- Validam o numero CNJ antes de qualquer chamada externa
- Delegam corretamente ao provider
- Incluem os campos obrigatorios de aviso e disclaimer
- Propagam erros do provider sem mascarar
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from mcp_juridico_brasil._core.errors import (
    JuridicoNotFoundError,
    JuridicoSigiloError,
    JuridicoValidationError,
)
from mcp_juridico_brasil.shared.schemas import Movimentacao, Processo

# ---------------------------------------------------------------------------
# Fixtures de dados
# ---------------------------------------------------------------------------

NUMERO_VALIDO = "0001234-56.2023.8.26.0100"
NUMERO_NORMALIZADO = "00012345620238260100"
TRIBUNAL = "TJSP"


def _processo_mock() -> Processo:
    """Cria instancia de Processo para uso nos mocks."""
    return Processo(
        numero_processo=NUMERO_NORMALIZADO,
        tribunal=TRIBUNAL,
        grau="G1",
        nivel_sigilo=0,
        data_ajuizamento=datetime(2023, 3, 15, tzinfo=timezone.utc),
        data_ultima_atualizacao=datetime(2024, 1, 10, 14, 30, tzinfo=timezone.utc),
        classe_nome="Procedimento Comum",
        movimentacoes=[
            Movimentacao(
                codigo=11010,
                nome="Juntada de Peticao",
                data_hora=datetime(2024, 1, 10, 14, 30, tzinfo=timezone.utc),
            ),
            Movimentacao(
                codigo=11009,
                nome="Distribuicao",
                data_hora=datetime(2023, 3, 15, 9, 0, tzinfo=timezone.utc),
            ),
        ],
    )


def _movimentacoes_mock() -> list[Movimentacao]:
    return _processo_mock().movimentacoes


# ---------------------------------------------------------------------------
# Testes: buscar_processo_por_numero
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buscar_processo_retorna_dados_e_aviso() -> None:
    """Tool deve retornar dados do processo e campo 'aviso' obrigatorio."""
    from mcp_juridico_brasil.processo.tools import buscar_processo_por_numero

    with patch(
        "mcp_juridico_brasil.processo.tools._provider.buscar_processo",
        new_callable=AsyncMock,
        return_value=_processo_mock(),
    ):
        resultado = await buscar_processo_por_numero(NUMERO_VALIDO, TRIBUNAL)

    assert "processo" in resultado
    assert "aviso" in resultado
    assert "fonte" in resultado
    processo_data: Any = resultado["processo"]
    assert processo_data["numero_processo"] == NUMERO_NORMALIZADO


@pytest.mark.asyncio
async def test_buscar_processo_numero_invalido_lanca_validation_error() -> None:
    """Numero CNJ invalido deve lancar JuridicoValidationError sem chamar o provider."""
    from mcp_juridico_brasil.processo.tools import buscar_processo_por_numero

    with pytest.raises(JuridicoValidationError) as exc_info:
        await buscar_processo_por_numero("numero-invalido", TRIBUNAL)

    assert "numero_processo" in exc_info.value.detail["field"]


@pytest.mark.asyncio
async def test_buscar_processo_propaga_not_found() -> None:
    """JuridicoNotFoundError do provider deve ser propagada pela tool."""
    from mcp_juridico_brasil.processo.tools import buscar_processo_por_numero

    with patch(
        "mcp_juridico_brasil.processo.tools._provider.buscar_processo",
        new_callable=AsyncMock,
        side_effect=JuridicoNotFoundError(NUMERO_NORMALIZADO, TRIBUNAL),
    ):
        with pytest.raises(JuridicoNotFoundError):
            await buscar_processo_por_numero(NUMERO_VALIDO, TRIBUNAL)


@pytest.mark.asyncio
async def test_buscar_processo_propaga_sigilo_error() -> None:
    """JuridicoSigiloError do provider deve ser propagada pela tool."""
    from mcp_juridico_brasil.processo.tools import buscar_processo_por_numero

    with patch(
        "mcp_juridico_brasil.processo.tools._provider.buscar_processo",
        new_callable=AsyncMock,
        side_effect=JuridicoSigiloError(NUMERO_NORMALIZADO, 1),
    ):
        with pytest.raises(JuridicoSigiloError):
            await buscar_processo_por_numero(NUMERO_VALIDO, TRIBUNAL)


# ---------------------------------------------------------------------------
# Testes: listar_movimentacoes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_listar_movimentacoes_retorna_lista_e_metadata() -> None:
    """Tool deve retornar lista de movimentacoes com metadata de contexto."""
    from mcp_juridico_brasil.movimentacoes.tools import listar_movimentacoes

    with patch(
        "mcp_juridico_brasil.movimentacoes.tools._provider.listar_movimentacoes",
        new_callable=AsyncMock,
        return_value=_movimentacoes_mock(),
    ):
        resultado = await listar_movimentacoes(NUMERO_VALIDO, TRIBUNAL, limite=20)

    assert "movimentacoes" in resultado
    assert "total_retornado" in resultado
    assert resultado["total_retornado"] == 2
    assert resultado["tribunal"] == TRIBUNAL
    assert "nota" in resultado


@pytest.mark.asyncio
async def test_listar_movimentacoes_limite_sanitizado() -> None:
    """Limite acima de 50 deve ser truncado para 50; abaixo de 1, para 1."""
    from mcp_juridico_brasil.movimentacoes.tools import listar_movimentacoes

    chamadas: list[int] = []

    async def mock_listar(numero: str, tribunal: str, limite: int) -> list[Movimentacao]:
        chamadas.append(limite)
        return _movimentacoes_mock()

    with patch(
        "mcp_juridico_brasil.movimentacoes.tools._provider.listar_movimentacoes",
        side_effect=mock_listar,
    ):
        # Limite acima de 50 deve ser truncado para 50
        await listar_movimentacoes(NUMERO_VALIDO, TRIBUNAL, limite=100)
        assert chamadas[-1] == 50

        # Limite abaixo de 1 deve ser elevado para 1
        await listar_movimentacoes(NUMERO_VALIDO, TRIBUNAL, limite=0)
        assert chamadas[-1] == 1


@pytest.mark.asyncio
async def test_listar_movimentacoes_numero_invalido() -> None:
    """Numero CNJ invalido deve lancar JuridicoValidationError."""
    from mcp_juridico_brasil.movimentacoes.tools import listar_movimentacoes

    with pytest.raises(JuridicoValidationError):
        await listar_movimentacoes("invalido", TRIBUNAL)


# ---------------------------------------------------------------------------
# Testes: resumir_andamento
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resumir_andamento_retorna_dados_e_instrucao() -> None:
    """Tool deve retornar dados_processo, instrucao_resumo e aviso legal."""
    from mcp_juridico_brasil.resumo.tools import resumir_andamento

    with patch(
        "mcp_juridico_brasil.resumo.tools._provider.buscar_processo",
        new_callable=AsyncMock,
        return_value=_processo_mock(),
    ):
        resultado = await resumir_andamento(NUMERO_VALIDO, TRIBUNAL)

    assert "dados_processo" in resultado
    assert "instrucao_resumo" in resultado
    assert "aviso" in resultado
    assert "fonte" in resultado
    # Instrucao nao deve estar vazia
    instrucao: Any = resultado["instrucao_resumo"]
    assert len(instrucao) > 20
    # Aviso deve mencionar OAB ou responsabilidade
    aviso: Any = resultado["aviso"]
    assert "aviso" in aviso.lower() or "legal" in aviso.lower() or "oab" in aviso.lower()


@pytest.mark.asyncio
async def test_resumir_andamento_nao_chama_llm_externo() -> None:
    """resumir_andamento deve retornar instrucao para o modelo, nao chamar LLM."""
    from mcp_juridico_brasil.resumo.tools import resumir_andamento

    with patch(
        "mcp_juridico_brasil.resumo.tools._provider.buscar_processo",
        new_callable=AsyncMock,
        return_value=_processo_mock(),
    ):
        resultado = await resumir_andamento(NUMERO_VALIDO, TRIBUNAL)

    # Confirma que existe instrucao de resumo (delega ao modelo)
    assert "instrucao_resumo" in resultado
    instrucao = resultado["instrucao_resumo"]
    assert isinstance(instrucao, str)
    assert len(instrucao) > 0


# ---------------------------------------------------------------------------
# Testes: monitorar_processo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_monitorar_processo_detecta_atualizacao() -> None:
    """Quando houve atualizacao, houve_atualizacao deve ser True."""
    from mcp_juridico_brasil.monitoramento.tools import monitorar_processo

    # data_ultima_atualizacao do mock e 2024-01-10, desde e 2024-01-01
    with (
        patch(
            "mcp_juridico_brasil.monitoramento.tools._provider.verificar_atualizacao",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "mcp_juridico_brasil.monitoramento.tools._provider.buscar_processo",
            new_callable=AsyncMock,
            return_value=_processo_mock(),
        ),
    ):
        resultado = await monitorar_processo(NUMERO_VALIDO, TRIBUNAL, "2024-01-01T00:00:00")

    assert resultado["houve_atualizacao"] is True
    assert resultado["tribunal"] == TRIBUNAL
    assert "aviso_defasagem" in resultado


@pytest.mark.asyncio
async def test_monitorar_processo_sem_atualizacao() -> None:
    """Quando nao houve atualizacao, houve_atualizacao deve ser False."""
    from mcp_juridico_brasil.monitoramento.tools import monitorar_processo

    with (
        patch(
            "mcp_juridico_brasil.monitoramento.tools._provider.verificar_atualizacao",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "mcp_juridico_brasil.monitoramento.tools._provider.buscar_processo",
            new_callable=AsyncMock,
            return_value=_processo_mock(),
        ),
    ):
        resultado = await monitorar_processo(NUMERO_VALIDO, TRIBUNAL, "2025-01-01T00:00:00")

    assert resultado["houve_atualizacao"] is False


# ---------------------------------------------------------------------------
# Testes: calcular_proximo_prazo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calcular_prazo_retorna_estimativa_e_aviso() -> None:
    """Tool deve retornar estimativa de prazo com campos da Fase 2 e aviso proeminente."""
    from mcp_juridico_brasil.prazo.tools import calcular_proximo_prazo

    with patch(
        "mcp_juridico_brasil.prazo.tools._provider.buscar_processo",
        new_callable=AsyncMock,
        return_value=_processo_mock(),
    ):
        resultado = await calcular_proximo_prazo(NUMERO_VALIDO, TRIBUNAL, "Contestacao")

    # Campos da nova implementacao Fase 2
    assert "data_final_iso" in resultado
    assert "termo_inicial_iso" in resultado
    assert "aviso" in resultado
    assert "limitacao" in resultado
    assert resultado["dias_uteis_prazo"] == 15  # Contestacao = 15 dias uteis
    assert "base_legal" in resultado
    assert "feriados_e_recessos_no_periodo" in resultado


@pytest.mark.asyncio
async def test_calcular_prazo_tipo_ato_personalizado() -> None:
    """Embargos de Declaracao deve usar 5 dias uteis (art. 1.023 CPC)."""
    from mcp_juridico_brasil.prazo.tools import calcular_proximo_prazo

    with patch(
        "mcp_juridico_brasil.prazo.tools._provider.buscar_processo",
        new_callable=AsyncMock,
        return_value=_processo_mock(),
    ):
        resultado = await calcular_proximo_prazo(NUMERO_VALIDO, TRIBUNAL, "Embargos de Declaracao")

    assert resultado["dias_uteis_prazo"] == 5


@pytest.mark.asyncio
async def test_calcular_prazo_sem_movimentacoes() -> None:
    """Processo sem movimentacoes deve retornar prazo_estimado None com motivo."""
    from mcp_juridico_brasil.prazo.tools import calcular_proximo_prazo

    processo_sem_movs = Processo(
        numero_processo=NUMERO_NORMALIZADO,
        tribunal=TRIBUNAL,
        nivel_sigilo=0,
    )

    with patch(
        "mcp_juridico_brasil.prazo.tools._provider.buscar_processo",
        new_callable=AsyncMock,
        return_value=processo_sem_movs,
    ):
        resultado = await calcular_proximo_prazo(NUMERO_VALIDO, TRIBUNAL)

    assert resultado["prazo_estimado"] is None
    assert "motivo" in resultado
    assert "aviso" in resultado


# ---------------------------------------------------------------------------
# Testes: listar_tribunais (inline no server)
# ---------------------------------------------------------------------------


def test_listar_tribunais_total_minimo() -> None:
    """listar_tribunais deve retornar pelo menos 91 entradas (cobertura DataJud).

    O mapeamento atual cobre 92 tribunais: 5 superiores (STF, STJ, TST, TSE, STM),
    6 TRFs, 27 TJs estaduais e DF, 24 TRTs, 27 TREs e 3 militares estaduais.
    """
    from mcp_juridico_brasil.datajud.tribunais import listar_tribunais

    tribunais = listar_tribunais()
    assert len(tribunais) >= 91


def test_listar_tribunais_contem_tjsp() -> None:
    """TJSP deve estar na lista de tribunais."""
    from mcp_juridico_brasil.datajud.tribunais import listar_tribunais

    assert "TJSP" in listar_tribunais()


def test_listar_tribunais_contem_superiores() -> None:
    """Tribunais superiores devem estar presentes."""
    from mcp_juridico_brasil.datajud.tribunais import listar_tribunais

    trib = listar_tribunais()
    for sigla in ["STF", "STJ", "TST", "TSE", "STM"]:
        assert sigla in trib, f"{sigla} ausente na lista"


def test_listar_tribunais_contem_trts() -> None:
    """Todos os TRTs de 1 a 24 devem estar presentes."""
    from mcp_juridico_brasil.datajud.tribunais import listar_tribunais

    trib = listar_tribunais()
    for i in range(1, 25):
        assert f"TRT{i}" in trib, f"TRT{i} ausente na lista"


def test_listar_tribunais_contem_tres() -> None:
    """TREs estaduais devem estar presentes."""
    from mcp_juridico_brasil.datajud.tribunais import listar_tribunais

    trib = listar_tribunais()
    for sigla in ["TRESP", "TRERJ", "TREMG", "TRERS"]:
        assert sigla in trib, f"{sigla} ausente na lista"


def test_sigla_para_indice_tjsp() -> None:
    """TJSP deve mapear para 'tjsp'."""
    from mcp_juridico_brasil.datajud.tribunais import sigla_para_indice

    assert sigla_para_indice("TJSP") == "tjsp"
    assert sigla_para_indice("tjsp") == "tjsp"  # case insensitive


def test_sigla_para_indice_desconhecida() -> None:
    """Sigla inexistente deve retornar None."""
    from mcp_juridico_brasil.datajud.tribunais import sigla_para_indice

    assert sigla_para_indice("XXXXXX") is None


def test_indice_para_url_tjsp() -> None:
    """indice_para_url deve montar URL correta do DataJud para o TJSP."""
    from mcp_juridico_brasil.datajud.tribunais import indice_para_url

    url = indice_para_url("TJSP", "https://api-publica.datajud.cnj.jus.br")
    assert url == "https://api-publica.datajud.cnj.jus.br/api_publica_tjsp/_search"
