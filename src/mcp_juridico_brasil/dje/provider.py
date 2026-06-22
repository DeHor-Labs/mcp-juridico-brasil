"""Provider DJe - camada de domínio entre o cliente HTTP e as tools MCP.

Converte respostas raw da API Comunica para os schemas Pydantic do módulo DJe,
aplica regras de compliance (sigilo, LGPD) e encapsula o gate de confirmacao
de leitura com todos os seus requisitos de segurança.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from mcp_juridico_brasil._core.logging import get_logger
from mcp_juridico_brasil.dje.client import DJeOAuthClient
from mcp_juridico_brasil.dje.schemas import (
    Intimacao,
    ListaIntimacoes,
    ResultadoConfirmacaoLeitura,
    StatusIntimacao,
)

logger = get_logger(__name__)

_AVISO_JURIDICO = (
    "AVISO DE EFEITO JURÍDICO: A confirmação de leitura de uma intimação no "
    "Domicílio Judicial Eletrônico inicia a contagem oficial do prazo processual. "
    "Esta operação é IRREVERSÍVEL. Verifique sempre no portal do tribunal antes "
    "de confirmar. Não constitui consultoria jurídica - responsabilidade do "
    "advogado habilitado (OAB Recomendação 001/2024)."
)

_ENV_PERMITIR_CONFIRMACAO = "DJE_PERMITIR_CONFIRMACAO_LEITURA"


def _modo_real_habilitado() -> bool:
    """Retorna True apenas se DJE_PERMITIR_CONFIRMACAO_LEITURA=true no ambiente."""
    return os.environ.get(_ENV_PERMITIR_CONFIRMACAO, "").strip().lower() == "true"


def _iso_ou_none(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        logger.warning("dje_data_invalida_ignorada", valor=valor)
        return None


class DJeProvider:
    """Provedor de intimações do Domicílio Judicial Eletrônico.

    Responsável por:
    - Converter respostas raw da API Comunica para schemas Pydantic.
    - Suprimir conteúdo de intimações sigilosas.
    - Implementar o gate de segurança da confirmação de leitura.
    """

    def __init__(self, client: DJeOAuthClient | None = None) -> None:
        self._client = client or DJeOAuthClient()

    # ------------------------------------------------------------------
    # Parsing interno
    # ------------------------------------------------------------------

    def _parse_intimacao(self, raw: dict[str, Any]) -> Intimacao:
        """Converte item raw da API Comunica para schema Intimacao.

        INTEGRACAO: Nomes de campo seguem documentacao pública do DJe (jun/2026).
        Ajustar conforme resposta real após credenciamento.
        """
        status_raw = str(raw.get("situacao", raw.get("status", "pendente"))).lower()
        try:
            status = StatusIntimacao(status_raw)
        except ValueError:
            logger.warning(
                "dje_status_desconhecido_assumindo_pendente",
                status_recebido=status_raw,
                id=raw.get("id"),
            )
            status = StatusIntimacao.PENDENTE

        is_sigilosa = bool(raw.get("sigilosa", raw.get("segredoJustica", False)))

        # COMPLIANCE: Suprimir conteúdo de intimações sigilosas
        conteudo: str | None = None
        if not is_sigilosa:
            conteudo = raw.get("conteudo", raw.get("texto"))

        return Intimacao(
            id=str(raw.get("id", raw.get("idComunicacao", ""))),
            numero_processo=str(raw.get("numeroProcesso", raw.get("numero_processo", ""))),
            orgao_julgador=str(raw.get("orgaoJulgador", raw.get("orgao_julgador", ""))),
            tipo_comunicacao=str(raw.get("tipoComunicacao", raw.get("tipo", "Intimação"))),
            data_disponibilizacao=(
                _iso_ou_none(raw.get("dataDisponibilizacao", raw.get("data_disponibilizacao")))
                or datetime.now(tz=timezone.utc)
            ),
            data_leitura=_iso_ou_none(raw.get("dataLeitura", raw.get("data_leitura"))),
            prazo_em_dias=raw.get("prazo", raw.get("prazo_em_dias")),
            status=status,
            is_sigilosa=is_sigilosa,
            conteudo=conteudo,
        )

    # ------------------------------------------------------------------
    # Operações públicas
    # ------------------------------------------------------------------

    async def listar_intimacoes(
        self,
        numero_processo: str | None = None,
        apenas_pendentes: bool = True,
        limite: int = 50,
    ) -> ListaIntimacoes:
        """Lista comunicações processuais do Domicílio Judicial Eletrônico.

        Operação somente leitura - sem efeito jurídico.

        Args:
            numero_processo: Filtrar por número CNJ (opcional).
            apenas_pendentes: Se True, retorna apenas comunicações não lidas.
            limite: Número máximo de registros.

        Returns:
            ListaIntimacoes com aviso jurídico embutido.

        Raises:
            JuridicoAPIError: Falha de comunicação com a API DJe.
        """
        raw_list = await self._client.listar_comunicacoes(
            numero_processo=numero_processo,
            apenas_pendentes=apenas_pendentes,
            limite=limite,
        )

        intimacoes: list[Intimacao] = []
        sigilosas_omitidas = 0

        for raw in raw_list:
            intimacao = self._parse_intimacao(raw)
            if intimacao.is_sigilosa:
                sigilosas_omitidas += 1
                logger.warning(
                    "dje_intimacao_sigilosa_conteudo_suprimido",
                    id=intimacao.id,
                    processo=intimacao.numero_processo,
                )
            intimacoes.append(intimacao)

        pendentes = sum(1 for i in intimacoes if i.status == StatusIntimacao.PENDENTE)

        if sigilosas_omitidas:
            logger.info(
                "dje_intimacoes_sigilosas_omitidas_na_listagem",
                quantidade=sigilosas_omitidas,
            )

        return ListaIntimacoes(
            intimacoes=intimacoes,
            total=len(intimacoes),
            pendentes=pendentes,
            aviso_juridico=_AVISO_JURIDICO,
        )

    async def confirmar_leitura(
        self,
        numero_processo: str,
        id_comunicacao: str,
        confirmar: bool = False,
    ) -> ResultadoConfirmacaoLeitura:
        """Confirma leitura de uma intimação no DJe.

        GATE DE SEGURANÇA - TRÊS CAMADAS:

        1. Parâmetro explícito: confirmar=True deve ser passado intencionalmente.
           Chamadas sem este parâmetro retornam dry-run sem qualquer efeito.

        2. Variável de ambiente: DJE_PERMITIR_CONFIRMACAO_LEITURA=true deve
           estar definida no ambiente. Ausente ou qualquer outro valor = dry-run.

        3. Verificação de estado: Intimação já lida retorna resultado idempotente
           sem nova chamada à API.

        EFEITO JURÍDICO IRREVERSÍVEL quando executado=True:
        - Registra ciência oficial no sistema do CNJ.
        - Inicia contagem do prazo processual.
        - Não pode ser desfeito via API.

        Args:
            numero_processo: Número CNJ do processo.
            id_comunicacao: ID da comunicação no DJe.
            confirmar: Deve ser True explicitamente para habilitar a operação.
                       False por padrão - proteção contra acionamento acidental.

        Returns:
            ResultadoConfirmacaoLeitura descrevendo o que ocorreu (e se ocorreu).
        """
        modo_dry_run = not confirmar or not _modo_real_habilitado()

        if not confirmar:
            logger.info(
                "dje_confirmacao_leitura_sem_confirmar_explicito",
                id=id_comunicacao,
                processo=numero_processo,
            )
            return ResultadoConfirmacaoLeitura(
                id_intimacao=id_comunicacao,
                numero_processo=numero_processo,
                executado=False,
                modo_dry_run=True,
                aviso_juridico=_AVISO_JURIDICO,
                mensagem=(
                    "Operação NÃO executada (modo seguro). "
                    "Para confirmar a leitura com efeito jurídico real, passe "
                    "confirmar=True E defina DJE_PERMITIR_CONFIRMACAO_LEITURA=true "
                    "no ambiente. ATENÇÃO: esta operação inicia o prazo processual."
                ),
            )

        if modo_dry_run:
            logger.info(
                "dje_confirmacao_leitura_dry_run",
                id=id_comunicacao,
                processo=numero_processo,
                env_habilitado=False,
            )
            return ResultadoConfirmacaoLeitura(
                id_intimacao=id_comunicacao,
                numero_processo=numero_processo,
                executado=False,
                modo_dry_run=True,
                aviso_juridico=_AVISO_JURIDICO,
                mensagem=(
                    f"Modo dry-run: confirmar=True recebido, mas "
                    f"{_ENV_PERMITIR_CONFIRMACAO} não está definida como 'true' "
                    "no ambiente. Nenhuma marcação foi feita na API DJe. "
                    "ATENÇÃO: Ao habilitar, a operação terá efeito jurídico real "
                    "e iniciará a contagem do prazo processual."
                ),
            )

        # Modo real: ambas as condições satisfeitas
        logger.info(
            "dje_confirmacao_leitura_modo_real",
            id=id_comunicacao,
            processo=numero_processo,
        )

        resultado_raw = await self._client.confirmar_leitura(
            numero_processo=numero_processo,
            id_comunicacao=id_comunicacao,
        )

        ja_estava_lida = bool(resultado_raw.get("ja_lida", False))
        data_leitura = _iso_ou_none(str(resultado_raw.get("data_leitura", "") or ""))

        if ja_estava_lida:
            return ResultadoConfirmacaoLeitura(
                id_intimacao=id_comunicacao,
                numero_processo=numero_processo,
                executado=False,
                modo_dry_run=False,
                ja_estava_lida=True,
                aviso_juridico=_AVISO_JURIDICO,
                mensagem="Intimação já havia sido confirmada anteriormente (idempotência).",
            )

        return ResultadoConfirmacaoLeitura(
            id_intimacao=id_comunicacao,
            numero_processo=numero_processo,
            executado=True,
            modo_dry_run=False,
            data_leitura=data_leitura or datetime.now(tz=timezone.utc),
            aviso_juridico=_AVISO_JURIDICO,
            mensagem=(
                "Leitura confirmada com sucesso no Domicílio Judicial Eletrônico. "
                "A contagem do prazo processual foi iniciada. "
                "Verifique o prazo aplicável no portal do tribunal."
            ),
        )


__all__ = ["DJeProvider"]
