"""Validadores para numero CNJ e dados processuais."""

from __future__ import annotations

import re

# Formato CNJ: NNNNNNN-DD.AAAA.J.TT.OOOO
# Ex.: 0001234-56.2023.8.26.0100
_CNJ_PATTERN = re.compile(r"^(\d{7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})$")

# Mesmo numero sem formatacao
_CNJ_DIGITS_PATTERN = re.compile(r"^\d{20}$")


def validar_numero_cnj(numero: str) -> bool:
    """Valida se o numero esta no formato CNJ (com ou sem formatacao)."""
    limpo = numero.strip()
    if _CNJ_PATTERN.match(limpo):
        return True
    # Aceita versao sem pontuacao (20 digitos)
    digits_only = re.sub(r"[-.]", "", limpo)
    return bool(_CNJ_DIGITS_PATTERN.match(digits_only))


def normalizar_numero_cnj(numero: str) -> str:
    """Retorna o numero sem formatacao (20 digitos) para uso na API DataJud."""
    return re.sub(r"[-.]", "", numero.strip())


def extrair_tribunal_cnj(numero: str) -> str | None:
    """Extrai a sigla do tribunal a partir do numero CNJ.

    O segmento J.TT do numero CNJ indica:
    - J=1: STF
    - J=2: CNJ
    - J=3: STJ
    - J=4: Justica Federal
    - J=5: Trabalho
    - J=6: Eleitoral
    - J=7: Militar da Uniao
    - J=8: Estadual/DF
    - J=9: Militar Estadual

    Retorna None se o numero for invalido ou se o tribunal nao for identificavel
    sem tabela auxiliar (ex.: J=8 TT=26 = TJSP, mas exige lookup).
    """
    limpo = numero.strip()
    match = _CNJ_PATTERN.match(limpo)
    if not match:
        return None
    # grupos: nnnnnnn, dd, aaaa, j, tt, oooo
    j = match.group(4)
    tt = match.group(5)
    return f"J{j}T{tt}"  # placeholder - Fase 1 expande com tabela completa


__all__ = ["extrair_tribunal_cnj", "normalizar_numero_cnj", "validar_numero_cnj"]
