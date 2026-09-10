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


# Mapa: codigo TR (2 digitos) -> UF, conforme a ordem alfabetica dos estados
# definida na Res. CNJ 65/2008 para a Justica Estadual e Eleitoral.
_TR_PARA_UF: dict[str, str] = {
    "01": "AC",
    "02": "AL",
    "03": "AP",
    "04": "AM",
    "05": "BA",
    "06": "CE",
    "07": "DF",
    "08": "ES",
    "09": "GO",
    "10": "MA",
    "11": "MT",
    "12": "MS",
    "13": "MG",
    "14": "PA",
    "15": "PB",
    "16": "PR",
    "17": "PE",
    "18": "PI",
    "19": "RJ",
    "20": "RN",
    "21": "RS",
    "22": "RO",
    "23": "RR",
    "24": "SC",
    "25": "SE",
    "26": "SP",
    "27": "TO",
}


def sigla_por_numero_cnj(numero_processo: str) -> str | None:
    """Deduz a sigla do tribunal a partir do numero CNJ.

    O formato NNNNNNN-DD.AAAA.J.TR.OOOO (Res. CNJ 65/2008) ja identifica o
    tribunal: J e o segmento do Judiciario e TR o codigo do tribunal. Deduzir
    daqui evita varrer os 91 indices quando o tribunal nao foi informado.

    Retorna None quando o numero e invalido ou quando o tribunal deduzido nao
    esta no mapa de indices -- nesse caso o chamador deve manter o fallback.
    """
    digitos = "".join(c for c in numero_processo if c.isdigit())
    if len(digitos) != 20:
        return None

    j, tr = digitos[13], digitos[14:16]
    uf = _TR_PARA_UF.get(tr)

    if j == "1":
        sigla = "STF" if tr == "00" else None
    elif j == "3":
        sigla = "STJ" if tr == "00" else None
    elif j == "4":
        sigla = f"TRF{int(tr)}" if tr != "00" else None
    elif j == "5":
        sigla = "TST" if tr == "00" else f"TRT{int(tr)}"
    elif j == "6":
        sigla = "TSE" if tr == "00" else (f"TRE{uf}" if uf else None)
    elif j == "7":
        sigla = "STM"
    elif j == "8":
        sigla = "TJDFT" if tr == "07" else (f"TJ{uf}" if uf else None)
    elif j == "9":
        sigla = f"TJM{uf}" if uf else None
    else:
        return None

    return sigla if sigla in TRIBUNAIS else None


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


__all__ = [
    "TRIBUNAIS",
    "indice_para_url",
    "listar_tribunais",
    "sigla_para_indice",
    "sigla_por_numero_cnj",
]
