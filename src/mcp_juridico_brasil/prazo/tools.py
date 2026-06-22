"""Tool MCP: calcular_proximo_prazo.

Fase 2: cálculo de prazos processuais em dias úteis com calendário forense.

Regras implementadas:
- Art. 219 CPC: prazos contados em dias úteis
- Art. 224 CPC: termo inicial no primeiro dia útil após a intimação/publicação
- Art. 220 CPC: recesso forense (20/dez a 20/jan) suspende a contagem
- Feriados nacionais via workalendar + Sexta-feira Santa
- Feriados estaduais via workalendar subregions (parâmetro uf opcional)

IMPORTANTE: Este cálculo é uma estimativa técnica de apoio ao advogado.
Não substitui a verificação no portal do tribunal nem a análise do profissional
habilitado. Feriados municipais, pontos facultativos e suspensões extraordinárias
NÃO são automaticamente considerados.
"""

from __future__ import annotations

import datetime

from mcp_juridico_brasil._core import JuridicoValidationError, get_logger
from mcp_juridico_brasil.datajud.provider import DataJudProvider
from mcp_juridico_brasil.prazo.calendario import UF_PARA_ISO, calcular_prazo
from mcp_juridico_brasil.shared.validators import normalizar_numero_cnj, validar_numero_cnj

logger = get_logger(__name__)
_provider = DataJudProvider()

# Tabela de prazos CPC mais comuns em dias uteis (art. 219 CPC)
_PRAZOS_CPC: dict[str, int] = {
    "Contestacao": 15,
    "Recurso de Apelacao": 15,
    "Agravo Regimental": 15,
    "Agravo Interno": 15,
    "Embargos de Declaracao": 5,
    "Recurso Especial": 15,
    "Recurso Extraordinario": 15,
    "Contrarrazoes": 15,
    "Manifestacao": 15,
    "Impugnacao": 15,
    "Embargos de Divergencia": 15,
    "Agravo em Recurso Especial": 15,
    "Agravo em Recurso Extraordinario": 15,
    "Reclamacao": 15,
    "Resposta": 15,
}

_PRAZO_PADRAO_DIAS = 15


async def calcular_proximo_prazo(
    numero_processo: str,
    tribunal: str,
    tipo_ato: str | None = None,
    uf: str | None = None,
    data_intimacao_iso: str | None = None,
) -> dict[str, object]:
    """Calcula o próximo prazo processual em dias úteis com calendário forense.

    Implementa art. 219 (dias úteis), art. 224 (termo inicial no dia seguinte)
    e art. 220 CPC (suspensão no recesso forense 20/dez a 20/jan).

    Args:
        numero_processo: Número no formato CNJ (NNNNNNN-DD.AAAA.J.TT.OOOO).
        tribunal: Sigla do tribunal (ex: 'TJSP', 'TRF1').
        tipo_ato: Tipo do ato processual para selecionar prazo CPC
                  (ex: 'Contestacao', 'Embargos de Declaracao').
                  Se omitido, usa prazo padrão de 15 dias úteis.
        uf: Sigla da UF para incluir feriados estaduais no cálculo
            (ex: 'SP', 'RJ', 'MG'). Se omitida, usa apenas feriados nacionais.
        data_intimacao_iso: Data de intimação/publicação em ISO 8601
                            (ex: '2025-01-15'). Se omitida, usa a data da
                            última movimentação disponível no DataJud.

    Returns:
        Dicionário com termo_inicial, data_final, dias_uteis, feriados
        que afetaram o cálculo e campo 'aviso' com limitações.
    """
    if not validar_numero_cnj(numero_processo):
        raise JuridicoValidationError(
            field="numero_processo",
            value=numero_processo,
            reason="Formato inválido. Use o padrão CNJ: NNNNNNN-DD.AAAA.J.TT.OOOO.",
        )

    if uf is not None and uf.upper() not in UF_PARA_ISO:
        raise JuridicoValidationError(
            field="uf",
            value=uf,
            reason=(
                f"UF '{uf}' não reconhecida. Use sigla de 2 letras (ex: 'SP', 'RJ', 'MG'). "
                f"UFs suportadas: {', '.join(sorted(UF_PARA_ISO.keys()))}"
            ),
        )

    # Validar e parsear data_intimacao_iso se fornecida
    data_intimacao_input: datetime.date | None = None
    if data_intimacao_iso is not None:
        try:
            data_intimacao_input = datetime.date.fromisoformat(
                data_intimacao_iso[:10]  # aceita datetime completo, usa só a data
            )
        except ValueError as exc:
            raise JuridicoValidationError(
                field="data_intimacao_iso",
                value=data_intimacao_iso,
                reason="Data inválida. Use formato ISO 8601: YYYY-MM-DD ou YYYY-MM-DDTHH:MM:SS",
            ) from exc

    numero_normalizado = normalizar_numero_cnj(numero_processo)
    logger.info(
        "calcular_prazo_solicitado",
        numero=numero_normalizado,
        tipo_ato=tipo_ato,
        uf=uf,
        data_intimacao=data_intimacao_iso,
    )

    # Buscar ultima movimentacao se data nao fornecida explicitamente
    data_referencia: datetime.date | None = data_intimacao_input
    fonte_data = "fornecida pelo usuario"
    ultima_mov_dict: dict[str, object] | None = None

    if data_referencia is None:
        processo = await _provider.buscar_processo(numero_normalizado, tribunal)
        ultima_mov = processo.movimentacoes[0] if processo.movimentacoes else None

        if not ultima_mov:
            return {
                "numero_processo": numero_normalizado,
                "tribunal": tribunal,
                "prazo_estimado": None,
                "motivo": "Nenhuma movimentação disponível no DataJud para calcular prazo.",
                "aviso": (
                    "AVISO: Não foi possível calcular o prazo pois o processo não "
                    "possui movimentações registradas no DataJud. Verifique o portal "
                    "do tribunal ou forneça data_intimacao_iso manualmente."
                ),
            }

        data_referencia = ultima_mov.data_hora.date()
        fonte_data = "ultima movimentacao DataJud"
        ultima_mov_dict = ultima_mov.model_dump(mode="json")

    dias = _PRAZOS_CPC.get(tipo_ato or "", _PRAZO_PADRAO_DIAS)
    if tipo_ato and tipo_ato not in _PRAZOS_CPC:
        logger.warning(
            "tipo_ato_nao_reconhecido",
            tipo_ato=tipo_ato,
            prazo_aplicado=_PRAZO_PADRAO_DIAS,
        )
    tipo_ato_desc = tipo_ato or f"padrao ({_PRAZO_PADRAO_DIAS} dias uteis)"

    resultado = calcular_prazo(
        data_intimacao=data_referencia,
        dias_uteis=dias,
        uf=uf,
    )

    feriados_lista = [
        {"data": d.isoformat(), "descricao": nome} for d, nome in resultado.feriados_no_periodo
    ]

    status_prazo = "VENCIDO" if resultado.data_final < datetime.date.today() else "EM ABERTO"

    retorno: dict[str, object] = {
        "numero_processo": numero_normalizado,
        "tribunal": tribunal,
        "tipo_ato": tipo_ato_desc,
        "dias_uteis_prazo": dias,
        "uf_considerada": uf or "nao informada (apenas feriados nacionais)",
        "fonte_data_intimacao": fonte_data,
        "data_intimacao_iso": data_referencia.isoformat(),
        "termo_inicial_iso": resultado.termo_inicial.isoformat(),
        "termo_inicial_legivel": resultado.termo_inicial.strftime("%d/%m/%Y"),
        "data_final_iso": resultado.data_final.isoformat(),
        "data_final_legivel": resultado.data_final.strftime("%d/%m/%Y"),
        "status_prazo": status_prazo,
        "feriados_e_recessos_no_periodo": feriados_lista,
        "total_feriados_e_recessos": len(feriados_lista),
        "dias_recesso_forense": resultado.dias_recesso,
        "aviso": resultado.aviso,
        "base_legal": "Art. 219, 220 e 224 do CPC/2015",
        "limitacao": (
            "Fase 2: feriados nacionais e estaduais cobertos. "
            "Feriados municipais, pontos facultativos (ex: Carnaval) e "
            "suspensões extraordinárias NÃO são considerados automaticamente. "
            "Fase 3+ ampliará a cobertura com feeds de expediente por tribunal."
        ),
    }

    if ultima_mov_dict is not None:
        retorno["ultima_movimentacao"] = ultima_mov_dict

    return retorno


__all__ = ["calcular_proximo_prazo"]
