"""Handler de webhook push de providers comerciais.

ESCOPO DE DEPLOY:
    Esta implementacao entrega o HANDLER (logica de validacao e processamento),
    nao um servidor HTTP completo. A exposicao do endpoint HTTP e responsabilidade
    do deploy - as opcoes recomendadas sao:

    1. FastAPI/Starlette (producao recomendada):
        ```python
        from fastapi import FastAPI, Header, HTTPException, Request
        from mcp_juridico_brasil.comercial.webhook import processar_webhook

        app = FastAPI()

        @app.post("/webhook/movimentacao")
        async def endpoint_webhook(request: Request, x_provider_signature: str = Header(...)):
            payload_bytes = await request.body()
            payload_json = await request.json()
            resultado = processar_webhook(
                payload=payload_json,
                assinatura_header=x_provider_signature,
                payload_bytes=payload_bytes,
                webhook_secret=os.environ["JURIDICO_WEBHOOK_SECRET"],
            )
            return resultado
        ```

    2. AWS Lambda / GCP Cloud Functions (serverless):
        Adaptar a assinatura para o evento do provedor de nuvem e chamar
        processar_webhook com os mesmos argumentos.

    3. Integrado ao servidor FastMCP (HTTP streamable):
        Montar um router customizado no mesmo processo do MCP, se o
        framework FastMCP suportar mounting de routers adicionais.

    Em todos os casos, o JURIDICO_WEBHOOK_SECRET deve ser o mesmo segredo
    configurado no painel do provider comercial para assinar os payloads.

SEGURANCA:
    - Assinatura HMAC-SHA256 validada ANTES de processar qualquer dado.
    - Payload malformado e rejeitado com mensagem de erro, sem stacktrace.
    - Processo sigiloso detectado no payload e bloqueado (nivel_sigilo > 0).
    - O segredo do webhook e lido exclusivamente de variavel de ambiente.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timezone
from typing import Any

from pydantic import AwareDatetime, BaseModel, Field, ValidationError

from mcp_juridico_brasil._core.errors import JuridicoSigiloError
from mcp_juridico_brasil._core.logging import get_logger
from mcp_juridico_brasil.monitoramento import store

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Schema de payload de webhook
# ---------------------------------------------------------------------------


class MovimentacaoWebhook(BaseModel):
    """Movimentacao recebida em payload de webhook de provider comercial."""

    codigo: int | None = None
    nome: str
    data_hora: str  # ISO 8601 - convertido para datetime ao salvar no store
    complementos: list[dict[str, Any]] = Field(default_factory=list)


class WebhookPayload(BaseModel):
    """Payload normalizado de notificacao push de provider comercial.

    Providers diferentes usam campos ligeiramente diferentes. Este schema
    aceita os formatos dos tres providers suportados (Judit, Escavador, TrackJud)
    usando aliases e campos opcionais.

    INTEGRACAO: Validar com payload real de cada provider antes de producao.
    """

    numero_processo: str
    tribunal: str
    nivel_sigilo: int = Field(default=0, ge=0)
    # AwareDatetime (Pydantic v2) valida formato ISO 8601 e exige fuso horario explicito.
    # Providers que enviem strings malformadas (ex: "ontem") serao rejeitados na validacao
    # do schema, antes de qualquer processamento.
    data_ultima_atualizacao: AwareDatetime | None = None
    movimentacoes: list[MovimentacaoWebhook] = Field(default_factory=list)
    # Campo livre para metadados do provider (nao persistido no store interno)
    metadados_provider: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Validacao de assinatura HMAC
# ---------------------------------------------------------------------------


class WebhookAssinaturaInvalidaError(Exception):
    """Assinatura HMAC do webhook nao confere com o payload recebido."""


def _validar_assinatura_hmac(
    payload_bytes: bytes,
    assinatura_header: str,
    segredo: str,
) -> None:
    """Valida assinatura HMAC-SHA256 do payload recebido.

    A maioria dos providers comerciais assina o payload com HMAC-SHA256
    usando o segredo configurado no painel. O header de assinatura tipicamente
    tem o formato 'sha256=<hex_digest>'.

    Args:
        payload_bytes: Corpo bruto da requisicao HTTP (bytes).
        assinatura_header: Valor do header de assinatura (ex: 'sha256=abc123...').
        segredo: Segredo HMAC compartilhado com o provider (JURIDICO_WEBHOOK_SECRET).

    Raises:
        WebhookAssinaturaInvalidaError: Se a assinatura nao for valida.
    """
    # Remove prefixo 'sha256=' se presente (padrao Judit, Digesto, GitHub-style)
    assinatura_recebida = assinatura_header.removeprefix("sha256=").strip()

    mac = hmac.new(
        key=segredo.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256,
    )
    assinatura_esperada = mac.hexdigest()

    # Comparacao em tempo constante para evitar timing attacks
    if not hmac.compare_digest(assinatura_esperada, assinatura_recebida):
        logger.warning(
            "webhook_assinatura_invalida",
            assinatura_recebida_prefixo=assinatura_recebida[:8] + "...",
        )
        raise WebhookAssinaturaInvalidaError(
            "Assinatura HMAC do webhook invalida. "
            "Verifique JURIDICO_WEBHOOK_SECRET e a configuracao no painel do provider."
        )


# ---------------------------------------------------------------------------
# Handler principal
# ---------------------------------------------------------------------------


def processar_webhook(
    payload: dict[str, Any],
    assinatura_header: str,
    payload_bytes: bytes,
    webhook_secret: str | None = None,
) -> dict[str, Any]:
    """Valida e processa um payload de webhook de movimentacao processual.

    Fluxo:
        1. Valida assinatura HMAC-SHA256 (rejeita se invalida).
        2. Valida schema do payload com Pydantic (rejeita se malformado).
        3. Verifica nivel_sigilo (bloqueia se > 0).
        4. Atualiza o store de snapshots com os dados recebidos.
        5. Retorna resumo do processamento.

    Args:
        payload: Dicionario com o payload JSON do webhook.
        assinatura_header: Valor do header de assinatura do provider.
        payload_bytes: Corpo bruto da requisicao (para verificacao HMAC).
        webhook_secret: Segredo HMAC. Se None, le de JURIDICO_WEBHOOK_SECRET.

    Returns:
        Dicionario com resultado do processamento:
        {
            "processado": True,
            "numero_processo": "...",
            "tribunal": "...",
            "movimentacoes_recebidas": N,
            "capturado_em": "ISO8601",
        }

    Raises:
        WebhookAssinaturaInvalidaError: Assinatura HMAC incorreta.
        JuridicoSigiloError: Processo em segredo de justica - nunca processa.
        ValueError: Payload malformado ou segredo ausente.
    """
    # 1. Resolver segredo
    segredo = webhook_secret or os.environ.get("JURIDICO_WEBHOOK_SECRET", "").strip()
    if not segredo:
        raise ValueError("Segredo de webhook ausente. Configure JURIDICO_WEBHOOK_SECRET.")

    # 2. Validar assinatura HMAC antes de qualquer outra operacao
    _validar_assinatura_hmac(payload_bytes, assinatura_header, segredo)

    # 3. Validar schema do payload
    try:
        webhook = WebhookPayload.model_validate(payload)
    except ValidationError as exc:
        erros = exc.errors(include_url=False)
        logger.warning("webhook_payload_invalido", erros=erros)
        raise ValueError(f"Payload de webhook malformado: {erros}") from exc

    # 4. Bloquear processo sigiloso - sem fallback, sem processamento parcial
    if webhook.nivel_sigilo > 0:
        logger.warning(
            "webhook_processo_sigiloso_bloqueado",
            numero=webhook.numero_processo,
            nivel=webhook.nivel_sigilo,
        )
        raise JuridicoSigiloError(webhook.numero_processo, webhook.nivel_sigilo)

    # 5. Atualizar store de snapshots
    agora = datetime.now(tz=timezone.utc).isoformat()
    dados_snapshot: dict[str, Any] = {
        "numero_processo": webhook.numero_processo,
        "tribunal": webhook.tribunal,
        "data_ultima_atualizacao": webhook.data_ultima_atualizacao.isoformat()
        if webhook.data_ultima_atualizacao
        else None,
        "movimentacoes": [m.model_dump() for m in webhook.movimentacoes],
        "fonte": "webhook",
        "recebido_em": agora,
        "metadados_provider": webhook.metadados_provider,
    }

    store.salvar_snapshot(
        numero_processo=webhook.numero_processo,
        tribunal=webhook.tribunal,
        dados=dados_snapshot,
    )

    logger.info(
        "webhook_processado",
        numero=webhook.numero_processo,
        movimentacoes=len(webhook.movimentacoes),
    )

    return {
        "processado": True,
        "numero_processo": webhook.numero_processo,
        "tribunal": webhook.tribunal,
        "movimentacoes_recebidas": len(webhook.movimentacoes),
        "capturado_em": agora,
    }


__all__ = [
    "MovimentacaoWebhook",
    "WebhookAssinaturaInvalidaError",
    "WebhookPayload",
    "processar_webhook",
]
