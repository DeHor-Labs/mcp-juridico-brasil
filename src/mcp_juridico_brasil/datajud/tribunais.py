"""Mapeamento de siglas de tribunais para indices DataJud.

Fonte: https://datajud-wiki.cnj.jus.br/api-publica/acesso/
Atualizado para cobertura de 91 tribunais conforme Portaria CNJ 160/2020.
"""

from __future__ import annotations

# Mapa: sigla_tribunal (uppercase) -> sufixo do indice DataJud (lowercase)
# Exemplo: "TJSP" -> "tjsp" -> api_publica_tjsp
TRIBUNAIS: dict[str, str] = {
    # Tribunais Superiores
    "STF": "stf",
    "STJ": "stj",
    "TST": "tst",
    "TSE": "tse",
    "STM": "stm",
    # Tribunais Regionais Federais
    "TRF1": "trf1",
    "TRF2": "trf2",
    "TRF3": "trf3",
    "TRF4": "trf4",
    "TRF5": "trf5",
    "TRF6": "trf6",
    # Tribunais de Justica Estaduais e DF
    "TJAC": "tjac",
    "TJAL": "tjal",
    "TJAM": "tjam",
    "TJAP": "tjap",
    "TJBA": "tjba",
    "TJCE": "tjce",
    "TJDFT": "tjdft",
    "TJES": "tjes",
    "TJGO": "tjgo",
    "TJMA": "tjma",
    "TJMG": "tjmg",
    "TJMS": "tjms",
    "TJMT": "tjmt",
    "TJPA": "tjpa",
    "TJPB": "tjpb",
    "TJPE": "tjpe",
    "TJPI": "tjpi",
    "TJPR": "tjpr",
    "TJRJ": "tjrj",
    "TJRN": "tjrn",
    "TJRO": "tjro",
    "TJRR": "tjrr",
    "TJRS": "tjrs",
    "TJSC": "tjsc",
    "TJSE": "tjse",
    "TJSP": "tjsp",
    "TJTO": "tjto",
    # Tribunais Regionais do Trabalho (TRT1 a TRT24)
    **{f"TRT{i}": f"trt{i}" for i in range(1, 25)},
    # Tribunais Regionais Eleitorais
    "TREAC": "treac",
    "TREAL": "treal",
    "TREAM": "tream",
    "TREAP": "treap",
    "TREBA": "treba",
    "TRECE": "trece",
    "TREDF": "tredf",
    "TREES": "trees",
    "TREGO": "trego",
    "TREMA": "trema",
    "TREMG": "tremg",
    "TREMS": "trems",
    "TREMT": "tremt",
    "TREPA": "trepa",
    "TREPB": "trepb",
    "TREPE": "trepe",
    "TREPI": "trepi",
    "TREPR": "trepr",
    "TRERJ": "trerj",
    "TRERN": "trern",
    "TRERO": "trero",
    "TRERR": "trerr",
    "TRERS": "trers",
    "TRESC": "tresc",
    "TRESE": "trese",
    "TRESP": "tresp",
    "TRETO": "treto",
    # Tribunais de Justica Militares Estaduais
    "TJMMG": "tjmmg",
    "TJMRS": "tjmrs",
    "TJMSP": "tjmsp",
}


def sigla_para_indice(sigla: str) -> str | None:
    """Converte sigla do tribunal para o sufixo do indice DataJud."""
    return TRIBUNAIS.get(sigla.upper())


def indice_para_url(sigla: str, base_url: str) -> str | None:
    """Retorna a URL completa do endpoint DataJud para o tribunal."""
    idx = sigla_para_indice(sigla)
    if not idx:
        return None
    return f"{base_url}/api_publica_{idx}/_search"


def listar_tribunais() -> list[str]:
    """Retorna a lista de siglas de tribunais suportados."""
    return sorted(TRIBUNAIS.keys())


__all__ = ["TRIBUNAIS", "indice_para_url", "listar_tribunais", "sigla_para_indice"]
