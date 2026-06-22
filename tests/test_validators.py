"""Testes unitarios para validadores de numero CNJ."""

import pytest

from mcp_juridico_brasil.shared.validators import (
    extrair_tribunal_cnj,
    normalizar_numero_cnj,
    validar_numero_cnj,
)


@pytest.mark.parametrize(
    "numero",
    [
        "0001234-56.2023.8.26.0100",
        "0000001-12.2020.8.26.0100",
        "1234567-89.2024.4.01.3400",
        "00012345620238260100",  # sem formatacao
    ],
)
def test_validar_numero_cnj_valido(numero: str) -> None:
    assert validar_numero_cnj(numero) is True


@pytest.mark.parametrize(
    "numero",
    [
        "",
        "1234",
        "0001234-56.2023.8.26",
        "AAAA-BB.CCCC.D.EE.FFFF",
        "0001234-56.2023.8.26.010",  # OOOO com 3 digitos
    ],
)
def test_validar_numero_cnj_invalido(numero: str) -> None:
    assert validar_numero_cnj(numero) is False


def test_normalizar_remove_pontuacao() -> None:
    resultado = normalizar_numero_cnj("0001234-56.2023.8.26.0100")
    assert resultado == "00012345620238260100"
    assert "-" not in resultado
    assert "." not in resultado


def test_normalizar_ja_sem_pontuacao() -> None:
    assert normalizar_numero_cnj("00012345620238260100") == "00012345620238260100"


def test_extrair_tribunal_retorna_none_para_invalido() -> None:
    assert extrair_tribunal_cnj("invalido") is None


def test_extrair_tribunal_retorna_codigo() -> None:
    resultado = extrair_tribunal_cnj("0001234-56.2023.8.26.0100")
    # J=8, TT=26 -> TJSP
    assert resultado == "J8T26"
