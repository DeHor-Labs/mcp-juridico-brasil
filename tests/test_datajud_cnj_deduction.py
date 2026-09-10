"""Testes da deducao de tribunal pelo numero CNJ (DataJud)."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from mcp_juridico_brasil._core.errors import JuridicoAPIError
from mcp_juridico_brasil.datajud.client import DataJudClient

# Reusa helpers do modulo principal de testes DataJud.
from tests.test_datajud_client import BASE_URL, _resp_processo_publico


@pytest.mark.parametrize(
    ("numero", "esperado"),
    [
        ("1000077-34.2026.8.13.0166", "TJMG"),  # Justica Estadual - MG
        ("0002150-34.2023.8.26.0100", "TJSP"),  # Justica Estadual - SP
        ("0001234-56.2023.8.07.0001", "TJDFT"),  # DF usa sigla propria
        ("0001234-56.2023.4.03.6100", "TRF3"),  # Justica Federal
        ("0001234-56.2023.5.03.0001", "TRT3"),  # Justica do Trabalho
        ("0001234-56.2023.1.00.0000", "STF"),  # Tribunal Superior
        ("0001234-56.2023.3.00.0000", "STJ"),  # STJ exige TR=00
        ("0001234-56.2023.1.01.0000", None),  # STF so com TR=00
        ("0001234-56.2023.3.01.0000", None),  # STJ so com TR=00
        ("0001234-56.2023.7.01.0000", "STM"),  # STM mantem indice unico
        ("00012345620238130024", "TJMG"),  # aceita sem mascara
        ("numero invalido", None),  # nao explode
        ("0001234-56.2023.0.99.0001", None),  # segmento inexistente
    ],
)
def test_sigla_por_numero_cnj(numero: str, esperado: str | None) -> None:
    from mcp_juridico_brasil.datajud.tribunais import sigla_por_numero_cnj

    assert sigla_por_numero_cnj(numero) == esperado


@pytest.mark.asyncio
async def test_multiplos_tribunais_tenta_o_tribunal_do_numero_primeiro() -> None:
    """O numero CNJ ja diz o tribunal: deve resolver em 1 requisicao."""
    numero = "10000773420268130166"  # 8.13 => TJMG

    with respx.mock:
        rota_mg = respx.post(f"{BASE_URL}/api_publica_tjmg/_search/").mock(
            return_value=Response(200, json=_resp_processo_publico(numero=numero))
        )
        # Antes da correcao a varredura comecava pelo STF (ordem alfabetica).
        rota_stf = respx.post(f"{BASE_URL}/api_publica_stf/_search/").mock(
            return_value=Response(404)
        )
        processo = await DataJudClient().buscar_por_numero_multiplos_tribunais(numero)

    assert processo.numero_processo == numero
    assert rota_mg.call_count == 1
    assert rota_stf.call_count == 0


@pytest.mark.asyncio
async def test_404_em_um_tribunal_nao_aborta_a_varredura() -> None:
    """HTTP 404 num indice virava HTTPStatusError crua e matava a busca."""
    numero = "00012345620230990001"  # segmento sem tribunal deduzivel

    with respx.mock:
        respx.post(url__regex=rf"{BASE_URL}/api_publica_\w+/_search/").mock(
            return_value=Response(404)
        )
        with pytest.raises(JuridicoAPIError) as exc_info:
            await DataJudClient().buscar_por_numero_multiplos_tribunais(numero)
        assert exc_info.value.detail.get("status_code") == 404
