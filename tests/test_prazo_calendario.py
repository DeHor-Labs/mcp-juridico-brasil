"""Testes deterministicos do calendario forense brasileiro.

Datas fixas para garantir reproducibilidade independente de quando o teste roda.
Cobre os casos de borda exigidos pelo escopo da Fase 2:
- Prazo de 15 dias uteis com fim de semana e feriado no meio
- Termo inicial caindo em feriado/fim de semana (deve avancar)
- Prazo atravessando recesso forense 20/dez-20/jan (suspende e retoma)
- UF com feriado estadual (SP - 09/jul)
- Entrada invalida (dias_uteis <= 0)
"""

from __future__ import annotations

import datetime

import pytest

from mcp_juridico_brasil.prazo.calendario import (
    ResultadoCalculo,
    calcular_prazo,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _datas_no_periodo(r: ResultadoCalculo) -> set[datetime.date]:
    """Datas puladas (feriados/recesso) do resultado."""
    return {d for d, _ in r.feriados_no_periodo}


# ---------------------------------------------------------------------------
# 1. Prazo basico: 15 dias uteis pulando fim de semana
#
# Intimacao: 2025-01-24 (sexta-feira)
# Termo inicial: 2025-01-27 (segunda, primeiro util apos 24/jan)
# Contagem: 27/jan(1), 28/jan(2), 29/jan(3), 30/jan(4), 31/jan(5),
#           03/fev(6), 04/fev(7), 05/fev(8), 06/fev(9), 07/fev(10),
#           10/fev(11), 11/fev(12), 12/fev(13), 13/fev(14), 14/fev(15)
# Data final esperada: 2025-02-14 (sexta-feira) -- sem feriados nessa janela
# ---------------------------------------------------------------------------


def test_prazo_15_dias_uteis_pula_fim_de_semana() -> None:
    """15 dias uteis a partir de sexta: deve pular sabados e domingos."""
    data_intimacao = datetime.date(2025, 1, 24)  # sexta
    r = calcular_prazo(data_intimacao=data_intimacao, dias_uteis=15)

    assert r.termo_inicial == datetime.date(2025, 1, 27), "Termo inicial deve ser segunda 27/jan"
    assert r.data_final == datetime.date(2025, 2, 14), "Prazo deve terminar em 14/fev"
    assert r.dias_uteis == 15
    assert r.dias_recesso == 0


# ---------------------------------------------------------------------------
# 2. Prazo de 15 dias pulando feriado nacional no meio
#
# Intimacao: 2025-04-17 (quinta)
# Termo inicial: 2025-04-18 -- Sexta-feira Santa (feriado) -> avanca para 22/abr (terca)
# Contagem a partir de 22/abr:
#   22(1), 23(2), 24(3), 25/abr=TIRADENTES(feriado!),
#   28(4), 29(5), 30(6), 01/mai=TRABALHO(feriado!),
#   02(7), 05(8), 06(9), 07(10), 08(11), 09(12), 12(13), 13(14), 14(15)
# Data final esperada: 2025-05-14
# ---------------------------------------------------------------------------


def test_prazo_pula_feriado_nacional_sexta_santa_e_tiradentes() -> None:
    """Prazo com Sexta Santa (18/abr) e Tiradentes (21/abr) deve pula-los.

    Pascoa 2025 = 20/abr (domingo). Sexta Santa = 18/abr. Tiradentes = 21/abr.
    Sequencia: 18/abr(feriado), 19/abr(sabado), 20/abr(domingo+Pascoa),
    21/abr(Tiradentes/segunda-feriado) -> termo inicial em 22/abr (terca).
    Contagem de 15 dias uteis a partir de 22/abr:
      22(1),23(2),24(3),[25sab],[27dom],28(4),29(5),30(6),
      [01/mai=Trabalho],02(7),05(8),06(9),07(10),08(11),09(12),
      12(13),13(14) -> 13/mai e o 14o dia util, data_final=13/mai.
    """
    data_intimacao = datetime.date(2025, 4, 17)  # quinta
    r = calcular_prazo(data_intimacao=data_intimacao, dias_uteis=15)

    # Termo inicial deve pular Sexta Santa (18/abr) E Tiradentes (21/abr)
    assert r.termo_inicial == datetime.date(2025, 4, 22), (
        "Termo inicial deve pular Sexta Santa (18/abr) e Tiradentes (21/abr)"
    )

    # O scan parte de data_intimacao+1, portanto 18/abr e 21/abr aparecem na lista
    datas_puladas = _datas_no_periodo(r)
    assert datetime.date(2025, 4, 18) in datas_puladas, "Sexta Santa (18/abr) deve aparecer"
    assert datetime.date(2025, 4, 21) in datas_puladas, "Tiradentes (21/abr) deve aparecer"
    assert datetime.date(2025, 5, 1) in datas_puladas, "Dia do Trabalho (01/mai) deve ser pulado"

    # Data final apos 15 dias uteis: 13/mai/2025
    assert r.data_final == datetime.date(2025, 5, 13)


# ---------------------------------------------------------------------------
# 3. Termo inicial cai em sabado: deve avancar para segunda
#
# Intimacao: 2025-02-28 (sexta)
# Dia seguinte: 2025-03-01 (sabado) -> avancar para 2025-03-03 (segunda)
# ---------------------------------------------------------------------------


def test_termo_inicial_em_sabado_avanca_para_segunda() -> None:
    """Se o dia seguinte a intimacao for sabado, termo inicial eh a proxima segunda."""
    data_intimacao = datetime.date(2025, 2, 28)  # sexta-feira
    r = calcular_prazo(data_intimacao=data_intimacao, dias_uteis=5)

    assert r.termo_inicial == datetime.date(2025, 3, 3), (
        "Termo inicial deve ser segunda 03/mar (pula sabado e domingo)"
    )


# ---------------------------------------------------------------------------
# 4. Termo inicial cai em domingo: deve avancar para segunda
# ---------------------------------------------------------------------------


def test_termo_inicial_em_domingo_avanca_para_segunda() -> None:
    """Se o dia seguinte a intimacao for domingo, termo inicial eh segunda."""
    data_intimacao = datetime.date(2025, 3, 1)  # sabado -> dia seguinte = domingo
    r = calcular_prazo(data_intimacao=data_intimacao, dias_uteis=5)

    assert r.termo_inicial == datetime.date(2025, 3, 3)


# ---------------------------------------------------------------------------
# 5. Prazo atravessa recesso forense 20/dez-20/jan
#
# Intimacao: 2025-12-18 (quinta)
# Termo inicial: 2025-12-19 (sexta, ultimo dia util antes do recesso)
# 19/dez = dia 1 util. Restam 4 dias uteis.
# 20/dez em diante = recesso ate 20/jan/2026 (inclusive).
# Retomada em 21/jan/2026 (quarta).
# dia1=19/dez, dia2=21/jan(qua), dia3=22/jan(qui), dia4=23/jan(sex), dia5=26/jan(seg)
# -> data final = 2026-01-26
# (24/jan=sex=dia4, 25/jan=sabado, 26/jan=seg=dia5)
# ---------------------------------------------------------------------------


def test_prazo_atravessa_recesso_forense() -> None:
    """Prazo que comeca antes do recesso deve ser suspenso de 20/dez a 20/jan."""
    data_intimacao = datetime.date(2025, 12, 18)  # quinta
    r = calcular_prazo(data_intimacao=data_intimacao, dias_uteis=5)

    # Termo inicial: 2025-12-19 (sexta - ainda antes do recesso)
    assert r.termo_inicial == datetime.date(2025, 12, 19)

    # Deve haver dias de recesso registrados
    assert r.dias_recesso > 0, "Deve registrar dias de recesso afetados"

    # Data final exata: 5 dias uteis com recesso 20/dez-20/jan
    # dia1=19/dez, dia2=21/jan, dia3=22/jan, dia4=23/jan, dia5=26/jan
    assert r.data_final == datetime.date(2026, 1, 26), (
        "Prazo de 5 dias com recesso deve terminar em 26/jan/2026"
    )

    # Recesso 20/dez-20/jan deve aparecer nos feriados do periodo
    descricoes = [nome for _, nome in r.feriados_no_periodo]
    assert any("Recesso" in d or "recesso" in d for d in descricoes), (
        "Recesso forense deve aparecer nos feriados do periodo"
    )


# ---------------------------------------------------------------------------
# 6. Prazo inteiramente dentro do recesso: data final bem depois de 20/jan
#
# Intimacao: 2025-12-19 (sexta)
# Termo inicial: 2025-12-20 -> em recesso -> 2026-01-21 (quarta)
# 5 dias uteis a partir de 21/jan: 21(1),22(2),23(3),24(4),27(5) -> final=27/jan
# ---------------------------------------------------------------------------


def test_prazo_inteiramente_apos_recesso() -> None:
    """Prazo com intimacao na vespera do recesso tem termo inicial em 21/jan."""
    data_intimacao = datetime.date(2025, 12, 19)  # sexta
    r = calcular_prazo(data_intimacao=data_intimacao, dias_uteis=5)

    # Dia seguinte eh 20/dez (sabado E inicio de recesso) -> pula para 21/jan
    assert r.termo_inicial == datetime.date(2026, 1, 21)
    assert r.data_final == datetime.date(2026, 1, 27)


# ---------------------------------------------------------------------------
# 7. Prazo com feriado estadual SP (09/jul - Revolucao Constitucionalista)
# ---------------------------------------------------------------------------


def test_prazo_com_feriado_estadual_sp() -> None:
    """Prazo com UF=SP deve pulsar 09/jul (Revolucao Constitucionalista)."""
    # Intimacao em 07/jul/2025 (segunda)
    # Termo inicial: 08/jul (terca)
    # 09/jul = feriado estadual SP
    # Com SP: 08(1), [09 feriado], 10(2), 11(3), 14(4), 15(5) -> final=15/jul
    # Sem SP: 08(1), 09(2), 10(3), 11(4), 14(5) -> final=14/jul
    data_intimacao = datetime.date(2025, 7, 7)

    r_sp = calcular_prazo(data_intimacao=data_intimacao, dias_uteis=5, uf="SP")
    r_sem_uf = calcular_prazo(data_intimacao=data_intimacao, dias_uteis=5, uf=None)

    # Com SP o prazo deve ser 1 dia mais longo por causa do feriado estadual
    assert r_sp.data_final > r_sem_uf.data_final, (
        "Prazo com UF=SP deve terminar apos o prazo sem UF (feriado 09/jul)"
    )

    datas_sp = _datas_no_periodo(r_sp)
    assert datetime.date(2025, 7, 9) in datas_sp, "09/jul deve ser feriado no calendario SP"


# ---------------------------------------------------------------------------
# 8. UF invalida nao reconhecida: usa apenas feriados nacionais (sem erro)
#    A tool valida a UF, mas calcular_prazo aceita UF desconhecida com aviso
# ---------------------------------------------------------------------------


def test_prazo_uf_desconhecida_usa_apenas_nacionais() -> None:
    """UF desconhecida nao lanca excecao; usa feriados nacionais e registra aviso."""
    data_intimacao = datetime.date(2025, 4, 17)
    # "XX" nao existe no mapa; nao deve lancar erro
    r = calcular_prazo(data_intimacao=data_intimacao, dias_uteis=5, uf="XX")
    assert r.data_final is not None
    assert "XX" in r.aviso or "nao tem feriados" in r.aviso


# ---------------------------------------------------------------------------
# 9. Dias uteis invalidos (zero ou negativo): deve lancar ValueError
# ---------------------------------------------------------------------------


def test_dias_uteis_zero_lanca_erro() -> None:
    """dias_uteis=0 deve lancar ValueError."""
    with pytest.raises(ValueError, match="dias_uteis"):
        calcular_prazo(datetime.date(2025, 1, 10), dias_uteis=0)


def test_dias_uteis_negativo_lanca_erro() -> None:
    """dias_uteis negativo deve lancar ValueError."""
    with pytest.raises(ValueError, match="dias_uteis"):
        calcular_prazo(datetime.date(2025, 1, 10), dias_uteis=-1)


# ---------------------------------------------------------------------------
# 10. Feriado de Natal 25/dez cai durante contagem
#
# NOTA: o recesso forense comeca em 20/dez (inclusive). Portanto intimacoes
# a partir de 19/dez resultam em termo inicial dentro ou apos o recesso.
# Para testar o Natal isoladamente, usamos intimacao em 17/dez (quarta).
#
# Intimacao: 2025-12-17 (quarta)
# Termo inicial: 2025-12-18 (quinta)
# Contagem: 18(1), 19(2) -- 20/dez inicio de recesso -- suspende.
# Retomada em 21/jan/2026: 21(3), 22(4), 23(5) -> data_final = 23/jan/2026
#
# Nota: o Natal (25/dez) cai dentro do recesso, portanto aparece como
# "Recesso forense" e nao como "Christmas Day" na lista. O recesso absorve
# todos os dias 20/dez a 20/jan, incluindo o Natal.
# ---------------------------------------------------------------------------


def test_prazo_com_natal_dentro_do_recesso() -> None:
    """Natal (25/dez) cai no recesso forense e deve ser absorvido pelo recesso."""
    # Intimacao em 17/dez: 2 dias uteis antes do recesso (18 e 19/dez)
    data_intimacao = datetime.date(2025, 12, 17)  # quarta
    r = calcular_prazo(data_intimacao=data_intimacao, dias_uteis=5)

    assert r.termo_inicial == datetime.date(2025, 12, 18)
    # Deve haver dias de recesso registrados (20/dez em diante)
    assert r.dias_recesso > 0, "Dias de recesso devem ser registrados"
    # Data final deve estar em jan/2026 apos o recesso
    assert r.data_final.year == 2026
    assert r.data_final >= datetime.date(2026, 1, 21)


def test_prazo_pula_natal_fora_do_recesso() -> None:
    """25/dez como feriado nacional: verificar que esta no set de feriados."""
    # Verificar diretamente que 25/dez esta no conjunto de feriados nacionais
    from mcp_juridico_brasil.prazo.calendario import _cache

    feriados_2025 = _cache.get_feriados(None, 2025)
    assert datetime.date(2025, 12, 25) in feriados_2025, "Natal deve estar nos feriados nacionais"
    # E que dia 24/dez NAO e feriado nacional (apenas ponto facultativo em alguns tribunais)
    assert datetime.date(2025, 12, 24) not in feriados_2025


# ---------------------------------------------------------------------------
# 11. Prazo de Embargos de Declaracao (5 dias uteis) - caso canonico CPC
#
# Intimacao: 2025-02-03 (segunda)
# Termo inicial: 2025-02-04 (terca)
# 5 dias: 04(1),05(2),06(3),07(4),10(5) -> final=10/fev (segunda)
# ---------------------------------------------------------------------------


def test_embargos_declaracao_5_dias_uteis() -> None:
    """Embargos de Declaracao: 5 dias uteis sem feriados deve funcionar direto."""
    data_intimacao = datetime.date(2025, 2, 3)  # segunda
    r = calcular_prazo(data_intimacao=data_intimacao, dias_uteis=5)

    assert r.termo_inicial == datetime.date(2025, 2, 4)
    assert r.data_final == datetime.date(2025, 2, 10)
    assert r.dias_recesso == 0


# ---------------------------------------------------------------------------
# 12. Aviso sempre presente no resultado
# ---------------------------------------------------------------------------


def test_resultado_sempre_contem_aviso() -> None:
    """ResultadoCalculo deve sempre ter campo aviso nao vazio."""
    r = calcular_prazo(datetime.date(2025, 3, 10), dias_uteis=5)
    assert r.aviso
    assert len(r.aviso) > 50


# ---------------------------------------------------------------------------
# 13. Recesso: 20/jan eh o ultimo dia - prazo so pode comecar em 21/jan
# ---------------------------------------------------------------------------


def test_recesso_termina_em_20_jan_inclusive() -> None:
    """20/jan deve ser recesso (inclusive); 21/jan deve ser dia util."""
    data_intimacao = datetime.date(2026, 1, 19)  # segunda
    r = calcular_prazo(data_intimacao=data_intimacao, dias_uteis=1)

    # Dia seguinte eh 20/jan (dentro do recesso)
    # Termo inicial deve ser 21/jan
    assert r.termo_inicial == datetime.date(2026, 1, 21), (
        "20/jan eh recesso inclusive; termo inicial deve ser 21/jan"
    )
    assert r.data_final == datetime.date(2026, 1, 21)


# ---------------------------------------------------------------------------
# 14. Regressao: Dia da Consciencia Negra (20/nov) deve ser feriado em 2024+
#
# BUG corrigido: workalendar v17 nao inclui 20/nov como feriado nacional.
# Lei 14.759/2023 torna 20/nov feriado nacional a partir de 2024.
# Sem o patch manual, 20/nov seria contado como dia util, antecipando
# o prazo indevidamente.
#
# Intimacao: 2024-11-18 (segunda)
# Termo inicial: 2024-11-19 (terca)
# 20/nov = feriado (Consciencia Negra) -> deve ser pulado
# 19(1), [20 feriado], 21(2), 22(3), 25(4), 26(5) -> data_final = 2024-11-26
# ---------------------------------------------------------------------------


def test_consciencia_negra_2024_eh_feriado() -> None:
    """20/nov deve ser feriado nacional em 2024 (Lei 14.759/2023) - regressao BUG CRITICAL."""
    from mcp_juridico_brasil.prazo.calendario import _cache

    feriados_2024 = _cache.get_feriados(None, 2024)
    assert datetime.date(2024, 11, 20) in feriados_2024, (
        "20/nov/2024 deve estar nos feriados nacionais (Lei 14.759/2023)"
    )


def test_consciencia_negra_2025_eh_feriado() -> None:
    """20/nov deve ser feriado nacional em 2025 tambem."""
    from mcp_juridico_brasil.prazo.calendario import _cache

    feriados_2025 = _cache.get_feriados(None, 2025)
    assert datetime.date(2025, 11, 20) in feriados_2025, (
        "20/nov/2025 deve estar nos feriados nacionais"
    )


def test_consciencia_negra_nao_eh_feriado_antes_de_2024() -> None:
    """20/nov NAO era feriado antes de 2024 (Lei 14.759/2023 entra em vigor em 2024)."""
    from mcp_juridico_brasil.prazo.calendario import _cache

    feriados_2023 = _cache.get_feriados(None, 2023)
    assert datetime.date(2023, 11, 20) not in feriados_2023, (
        "20/nov/2023 NAO deve ser feriado nacional (lei vigente a partir de 2024)"
    )


def test_prazo_pula_consciencia_negra_no_calculo() -> None:
    """Prazo com 20/nov/2024 no periodo deve pular o feriado - regressao BUG CRITICAL."""
    # Intimacao: 2024-11-18 (segunda)
    # Termo inicial: 2024-11-19 (terca)
    # 20/nov = feriado Consciencia Negra -> pulado
    # 19(1), [20 feriado], 21(2), 22(3), 25(4), 26(5) -> data_final = 26/nov/2024
    data_intimacao = datetime.date(2024, 11, 18)
    r = calcular_prazo(data_intimacao=data_intimacao, dias_uteis=5)

    assert r.termo_inicial == datetime.date(2024, 11, 19)
    assert r.data_final == datetime.date(2024, 11, 26), (
        "Prazo deve terminar em 26/nov/2024 pois 20/nov e feriado (Consciencia Negra)"
    )
    datas_puladas = _datas_no_periodo(r)
    assert datetime.date(2024, 11, 20) in datas_puladas, (
        "20/nov/2024 deve aparecer como feriado pulado no calculo"
    )


# ---------------------------------------------------------------------------
# 15. Regressao: aviso deve mencionar Corpus Christi explicitamente
# ---------------------------------------------------------------------------


def test_aviso_menciona_corpus_christi() -> None:
    """O campo aviso deve alertar sobre Corpus Christi como ponto facultativo."""
    r = calcular_prazo(datetime.date(2025, 3, 10), dias_uteis=5)
    assert "Corpus Christi" in r.aviso, (
        "Aviso deve mencionar Corpus Christi para orientar o advogado"
    )
