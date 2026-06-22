"""Calendario forense brasileiro para calculo de prazos processuais.

Implementa as regras do CPC/2015:
- Art. 219: prazos contados em dias uteis
- Art. 224: termo inicial no primeiro dia util seguinte ao da intimacao/publicacao
- Art. 220: suspensao de prazos durante recesso forense (20/dez a 20/jan)

Cobertura de feriados:
- Feriados nacionais via workalendar (Brazil): Confraternizacao, Tiradentes,
  Trabalho, Independencia, Aparecida, Finados, Proclamacao, Natal
- Dia da Consciencia Negra (20/nov): feriado nacional desde 2024 (Lei 14.759/2023);
  patch manual necessario pois o workalendar v17 nao inclui essa data
- Sexta-feira Santa (feriado nacional reconhecido pelo STJ/TST, nao incluido
  no workalendar Brasil por ser movel; calculado com python-dateutil)
- Feriados estaduais via workalendar subregions (BR-SP, BR-RJ, etc.)
  para as UFs mapeadas - ver UF_PARA_ISO abaixo

Limitacoes documentadas (campo 'aviso' na tool):
- Feriados municipais (ex: aniversario da cidade) NAO sao cobertos
- Ponto facultativo de Carnaval (2a/3a-feira) NAO eh feriado legal; tribunais
  podem ou nao suspender expediente - o advogado deve verificar o expediente
  do tribunal
- Corpus Christi (60 dias apos a Pascoa) e ponto facultativo federal e
  suspenso na maioria dos tribunais, mas NAO tem status de feriado legal
  nacional - o advogado deve verificar o expediente do tribunal especifico
- Feriados estaduais de UFs sem subregion mapeada no workalendar sao tratados
  como apenas nacionais
- Feriados criados por legislacao estadual posterior a base de dados do
  workalendar podem nao estar incluidos
- Esta implementacao NAO substitui a consulta ao portal do tribunal
"""

from __future__ import annotations

import datetime
import threading
from dataclasses import dataclass, field

from dateutil.easter import easter

# ---------------------------------------------------------------------------
# Mapa UF (sigla) -> codigo ISO 3166-2 do workalendar
# ---------------------------------------------------------------------------

UF_PARA_ISO: dict[str, str] = {
    "AC": "BR-AC",
    "AL": "BR-AL",
    "AM": "BR-AM",
    "AP": "BR-AP",
    "BA": "BR-BA",
    "CE": "BR-CE",
    "DF": "BR-DF",
    "ES": "BR-ES",
    "GO": "BR-GO",
    "MA": "BR-MA",
    "MG": "BR-MG",
    "MS": "BR-MS",
    "MT": "BR-MT",
    "PA": "BR-PA",
    "PB": "BR-PB",
    "PE": "BR-PE",
    "PI": "BR-PI",
    "PR": "BR-PR",
    "RJ": "BR-RJ",
    "RN": "BR-RN",
    "RO": "BR-RO",
    "RR": "BR-RR",
    "RS": "BR-RS",
    "SC": "BR-SC",
    "SE": "BR-SE",
    "SP": "BR-SP",
    "TO": "BR-TO",
}

# Periodo de recesso forense (art. 220 CPC): 20/12 a 20/01
_RECESSO_INICIO_MES = 12
_RECESSO_INICIO_DIA = 20
_RECESSO_FIM_MES = 1
_RECESSO_FIM_DIA = 20


@dataclass
class ResultadoCalculo:
    """Resultado estruturado do calculo de prazo processual."""

    data_intimacao: datetime.date
    """Data de intimacao/publicacao fornecida."""
    termo_inicial: datetime.date
    """Primeiro dia util apos a intimacao (art. 224 CPC)."""
    data_final: datetime.date
    """Data final do prazo (ultimo dia util contado)."""
    dias_uteis: int
    """Quantidade de dias uteis do prazo."""
    feriados_no_periodo: list[tuple[datetime.date, str]] = field(default_factory=list)
    """Feriados/recessos que caíram no periodo e foram pulados."""
    dias_recesso: int = 0
    """Quantidade de dias de recesso forense que afetaram o calculo."""
    uf: str | None = None
    """UF considerada no calculo (influencia feriados estaduais)."""
    aviso: str = ""
    """Aviso de limitacoes do calculo."""


class _CalendarioCache:
    """Cache de feriados por UF e ano, thread-safe via Lock.

    Uso interno: asyncio single-thread. O Lock garante corretude caso o
    servidor seja chamado com concorrencia real em Fase 3+ (ex: multiplas
    requisicoes HTTP simultaneas).
    """

    def __init__(self) -> None:
        self._cache: dict[tuple[str | None, int], set[datetime.date]] = {}
        self._nomes: dict[tuple[str | None, int], dict[datetime.date, str]] = {}
        self._lock = threading.Lock()

    def _sexta_santa(self, ano: int) -> datetime.date:
        """Calcula a Sexta-feira Santa (2 dias antes da Pascoa)."""
        pascoa: datetime.date = easter(ano)
        return pascoa - datetime.timedelta(days=2)

    def _feriados_nacionais_base(self, ano: int) -> set[datetime.date]:
        """Feriados nacionais via workalendar + patches manuais.

        Patches necessarios:
        - Sexta-feira Santa: feriado movel nao incluido no workalendar Brasil
        - Dia da Consciencia Negra (20/nov): feriado nacional desde 2024
          (Lei 14.759/2023); workalendar v17 nao inclui essa data
        """
        from workalendar.america import Brazil

        cal = Brazil()
        feriados = {d for d, _ in cal.holidays(ano)}
        feriados.add(self._sexta_santa(ano))
        # Patch: 20/nov = Dia da Consciencia Negra (Lei 14.759/2023, vigente a
        # partir de 2024). workalendar v17 nao inclui; patch manual necessario.
        if ano >= 2024:
            feriados.add(datetime.date(ano, 11, 20))
        return feriados

    def _nomes_nacionais_base(self, ano: int) -> dict[datetime.date, str]:
        """Nomes dos feriados nacionais (inclui patches manuais).

        Constroi o mapa date->nome uma unica vez por ano; chamadas subsequentes
        devem usar get_nomes() que cacheia o resultado.
        """
        from workalendar.america import Brazil

        cal = Brazil()
        nomes: dict[datetime.date, str] = {d: str(n) for d, n in cal.holidays(ano)}
        nomes[self._sexta_santa(ano)] = "Sexta-feira Santa"
        if ano >= 2024:
            nomes[datetime.date(ano, 11, 20)] = "Dia da Consciencia Negra"
        return nomes

    def _feriados_estaduais(self, uf: str, ano: int) -> set[datetime.date]:
        """Feriados estaduais via workalendar subregion."""
        iso = UF_PARA_ISO.get(uf.upper())
        if iso is None:
            return set()
        from workalendar.registry import registry

        cal_class = registry.get(iso)
        if cal_class is None:
            return set()
        cal_uf = cal_class()
        # feriados do estado inclui nacionais; pegamos so os extras
        nacionais = self._feriados_nacionais_base(ano)
        todos_uf = {d for d, _ in cal_uf.holidays(ano)}
        return todos_uf - nacionais

    def _nomes_estaduais(self, uf: str, ano: int) -> dict[datetime.date, str]:
        """Nomes dos feriados estaduais extras (sem os nacionais)."""
        iso = UF_PARA_ISO.get(uf.upper())
        if iso is None:
            return {}
        from workalendar.registry import registry

        cal_class = registry.get(iso)
        if cal_class is None:
            return {}
        cal_uf = cal_class()
        nacionais = self._feriados_nacionais_base(ano)
        return {
            d: f"{n} (feriado estadual {uf})"
            for d, n in cal_uf.holidays(ano)
            if d not in nacionais
        }

    def get_feriados(self, uf: str | None, ano: int) -> set[datetime.date]:
        """Retorna conjunto de feriados para o ano e UF dados (com cache)."""
        chave = (uf.upper() if uf else None, ano)
        with self._lock:
            if chave not in self._cache:
                nacionais = self._feriados_nacionais_base(ano)
                if uf:
                    extras = self._feriados_estaduais(uf, ano)
                    self._cache[chave] = nacionais | extras
                else:
                    self._cache[chave] = nacionais
            return self._cache[chave]

    def get_nomes(self, uf: str | None, ano: int) -> dict[datetime.date, str]:
        """Retorna mapa date->nome para o ano e UF dados (com cache).

        Evita instanciar Brazil() ou chamar holidays() repetidamente;
        o resultado e calculado uma unica vez por (uf, ano).
        """
        chave = (uf.upper() if uf else None, ano)
        with self._lock:
            if chave not in self._nomes:
                nomes = self._nomes_nacionais_base(ano)
                if uf:
                    nomes.update(self._nomes_estaduais(uf, ano))
                self._nomes[chave] = nomes
            return self._nomes[chave]


_cache = _CalendarioCache()


def _em_recesso(data: datetime.date) -> bool:
    """Verifica se a data cai no recesso forense (20/dez a 20/jan, inclusive)."""
    mes, dia = data.month, data.day
    if mes == 12:
        return dia >= _RECESSO_INICIO_DIA
    if mes == 1:
        return dia <= _RECESSO_FIM_DIA
    return False


def _eh_dia_util_forense(data: datetime.date, feriados: set[datetime.date]) -> bool:
    """Retorna True se a data eh dia util para fins de prazo processual.

    Considera: fim de semana, feriados nacionais/estaduais e recesso forense.
    """
    if data.weekday() >= 5:  # sabado=5, domingo=6
        return False
    if _em_recesso(data):
        return False
    if data in feriados:
        return False
    return True


def calcular_prazo(
    data_intimacao: datetime.date,
    dias_uteis: int,
    uf: str | None = None,
) -> ResultadoCalculo:
    """Calcula o prazo processual em dias uteis a partir da data de intimacao.

    Regras aplicadas:
    - O prazo comeca a correr no primeiro dia util SEGUINTE a data de intimacao
      (art. 224 CPC). A data de intimacao em si nao entra na contagem.
    - Sabados, domingos, feriados nacionais, feriados estaduais (se UF fornecida)
      e dias de recesso forense (20/dez a 20/jan) sao ignorados.
    - O prazo termina no ultimo dia util contado.

    Args:
        data_intimacao: Data de intimacao/publicacao (dia 0, nao entra na contagem).
        dias_uteis: Quantidade de dias uteis do prazo (ex: 15 para contestacao).
        uf: Sigla da UF para incluir feriados estaduais (ex: 'SP', 'RJ').
            Se omitida, usa apenas feriados nacionais.

    Returns:
        ResultadoCalculo com termo inicial, data final e metadados.
    """
    if dias_uteis <= 0:
        raise ValueError(f"dias_uteis deve ser positivo, recebeu {dias_uteis}")

    # Pre-carrega feriados por ano conforme necessario
    feriados_por_ano: dict[int, set[datetime.date]] = {}

    def _get_feriados(ano: int) -> set[datetime.date]:
        if ano not in feriados_por_ano:
            feriados_por_ano[ano] = _cache.get_feriados(uf, ano)
        return feriados_por_ano[ano]

    def _util(data: datetime.date) -> bool:
        return _eh_dia_util_forense(data, _get_feriados(data.year))

    # Art. 224: termo inicial = primeiro dia util APOS a intimacao
    candidato = data_intimacao + datetime.timedelta(days=1)
    while not _util(candidato):
        candidato += datetime.timedelta(days=1)
    termo_inicial = candidato

    # Contar dias_uteis a partir do termo_inicial (inclusive)
    dias_contados = 0
    cursor = termo_inicial
    data_final = termo_inicial

    while dias_contados < dias_uteis:
        if _util(cursor):
            dias_contados += 1
            data_final = cursor
        cursor += datetime.timedelta(days=1)

    # Coletar feriados/recessos que afetaram o calculo.
    # O scan vai de (data_intimacao + 1) ate data_final para capturar tambem
    # feriados que atrasaram o proprio termo inicial (ex: Tiradentes forcou
    # o termo a avancar de 21/abr para 22/abr).
    feriados_periodo: list[tuple[datetime.date, str]] = []
    dias_recesso = 0
    dia_scan = data_intimacao + datetime.timedelta(days=1)
    while dia_scan <= data_final:
        if dia_scan.weekday() < 5:  # apenas dias de semana importam ao advogado
            if _em_recesso(dia_scan):
                feriados_periodo.append((dia_scan, "Recesso forense (art. 220 CPC)"))
                dias_recesso += 1
            elif dia_scan in _get_feriados(dia_scan.year):
                nome = _nome_feriado(dia_scan, uf)
                feriados_periodo.append((dia_scan, nome))
        dia_scan += datetime.timedelta(days=1)

    uf_aviso = ""
    if uf:
        iso = UF_PARA_ISO.get(uf.upper())
        if iso is None:
            uf_aviso = (
                f" ATENCAO: UF '{uf}' nao tem feriados estaduais mapeados; "
                "apenas feriados nacionais foram considerados."
            )

    aviso = (
        "AVISO LEGAL: Este calculo e uma estimativa tecnica baseada em feriados nacionais"
        + (f" e estaduais ({uf})" if uf else "")
        + " e no recesso forense (art. 220 CPC). "
        "NAO considera: feriados municipais, pontos facultativos de Carnaval, "
        "Corpus Christi (ponto facultativo federal suspenso na maioria dos tribunais, "
        "mas sem status de feriado legal nacional), "
        "suspensoes extraordinarias (pandemias, catastrofes), prazos proprios de "
        "cada tribunal ou portarias de antecipacao de recesso. "
        "O advogado responsavel DEVE verificar o prazo efetivo no portal do tribunal. "
        "(OAB Rec. 001/2024)" + uf_aviso
    )

    return ResultadoCalculo(
        data_intimacao=data_intimacao,
        termo_inicial=termo_inicial,
        data_final=data_final,
        dias_uteis=dias_uteis,
        feriados_no_periodo=feriados_periodo,
        dias_recesso=dias_recesso,
        uf=uf,
        aviso=aviso,
    )


def _nome_feriado(data: datetime.date, uf: str | None) -> str:
    """Retorna o nome do feriado para uma data (melhor esforco).

    Usa o cache do modulo para evitar instanciar Brazil() e chamar
    holidays() repetidamente. O mapa date->nome e calculado uma unica
    vez por (uf, ano) e reutilizado em chamadas subsequentes.
    """
    nomes = _cache.get_nomes(uf, data.year)
    return nomes.get(data, "Feriado")


__all__ = [
    "UF_PARA_ISO",
    "ResultadoCalculo",
    "calcular_prazo",
]
