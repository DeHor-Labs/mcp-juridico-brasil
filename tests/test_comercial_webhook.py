"""Testes do handler de webhook de movimentacao processual.

Cenarios cobertos:
- Payload valido com assinatura correta -> atualiza store
- Assinatura invalida -> WebhookAssinaturaInvalidaError (antes de processar)
- Payload malformado (campos obrigatorios ausentes) -> ValueError
- Processo sigiloso no payload -> JuridicoSigiloError, store nao atualizado
- Segredo ausente -> ValueError
- Prefixo 'sha256=' no header e tratado corretamente
- Store atualizado com dados da movimentacao recebida
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import pytest

from mcp_juridico_brasil._core.errors import JuridicoSigiloError
from mcp_juridico_brasil.comercial.webhook import (
    WebhookAssinaturaInvalidaError,
    processar_webhook,
)
from mcp_juridico_brasil.monitoramento import store

# ---------------------------------------------------------------------------
# Constantes e helpers
# ---------------------------------------------------------------------------

NUMERO = "00012345620238260100"
TRIBUNAL = "TJSP"
SEGREDO = "segredo-hmac-de-teste"


def _assinar(payload_bytes: bytes, segredo: str = SEGREDO) -> str:
    """Gera assinatura HMAC-SHA256 no formato esperado pelo handler."""
    mac = hmac.new(
        key=segredo.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256,
    )
    return mac.hexdigest()


def _payload_valido(
    numero: str = NUMERO,
    tribunal: str = TRIBUNAL,
    nivel_sigilo: int = 0,
) -> dict[str, Any]:
    return {
        "numero_processo": numero,
        "tribunal": tribunal,
        "nivel_sigilo": nivel_sigilo,
        "data_ultima_atualizacao": "2024-06-01T12:00:00Z",
        "movimentacoes": [
            {
                "codigo": 22,
                "nome": "Despacho",
                "data_hora": "2024-06-01T12:00:00Z",
                "complementos": [],
            }
        ],
        "metadados_provider": {"provider": "judit", "id_notificacao": "abc123"},
    }


def _serializar(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


# ===========================================================================
# Testes de assinatura
# ===========================================================================


class TestWebhookAssinatura:
    """Testes de validacao HMAC do webhook."""

    def test_payload_valido_assinatura_correta_processa(self) -> None:
        """Payload com assinatura correta deve ser processado com sucesso."""
        payload = _payload_valido()
        payload_bytes = _serializar(payload)
        assinatura = _assinar(payload_bytes)

        resultado = processar_webhook(
            payload=payload,
            assinatura_header=assinatura,
            payload_bytes=payload_bytes,
            webhook_secret=SEGREDO,
        )

        assert resultado["processado"] is True
        assert resultado["numero_processo"] == NUMERO
        assert resultado["movimentacoes_recebidas"] == 1

    def test_prefixo_sha256_no_header_aceito(self) -> None:
        """Header no formato 'sha256=<digest>' deve ser aceito."""
        payload = _payload_valido()
        payload_bytes = _serializar(payload)
        assinatura = "sha256=" + _assinar(payload_bytes)

        resultado = processar_webhook(
            payload=payload,
            assinatura_header=assinatura,
            payload_bytes=payload_bytes,
            webhook_secret=SEGREDO,
        )

        assert resultado["processado"] is True

    def test_assinatura_errada_rejeitada(self) -> None:
        """Assinatura incorreta deve lancar WebhookAssinaturaInvalidaError."""
        payload = _payload_valido()
        payload_bytes = _serializar(payload)
        assinatura_errada = "a" * 64  # HMAC invalido

        with pytest.raises(WebhookAssinaturaInvalidaError):
            processar_webhook(
                payload=payload,
                assinatura_header=assinatura_errada,
                payload_bytes=payload_bytes,
                webhook_secret=SEGREDO,
            )

    def test_assinatura_segredo_diferente_rejeitada(self) -> None:
        """Assinatura gerada com segredo diferente deve ser rejeitada."""
        payload = _payload_valido()
        payload_bytes = _serializar(payload)
        assinatura_segredo_errado = _assinar(payload_bytes, segredo="outro-segredo")

        with pytest.raises(WebhookAssinaturaInvalidaError):
            processar_webhook(
                payload=payload,
                assinatura_header=assinatura_segredo_errado,
                payload_bytes=payload_bytes,
                webhook_secret=SEGREDO,
            )

    def test_payload_alterado_apos_assinar_rejeitado(self) -> None:
        """Payload modificado apos assinatura deve falhar na verificacao HMAC."""
        payload_original = _payload_valido()
        payload_bytes_original = _serializar(payload_original)
        assinatura = _assinar(payload_bytes_original)

        # Simula payload adulterado em transito
        payload_adulterado = {**payload_original, "tribunal": "STJ"}
        payload_bytes_adulterado = _serializar(payload_adulterado)

        with pytest.raises(WebhookAssinaturaInvalidaError):
            processar_webhook(
                payload=payload_adulterado,
                assinatura_header=assinatura,
                payload_bytes=payload_bytes_adulterado,
                webhook_secret=SEGREDO,
            )

    def test_segredo_ausente_lanca_value_error(self) -> None:
        """Sem segredo configurado, deve lancar ValueError antes de qualquer validacao."""
        payload = _payload_valido()
        payload_bytes = _serializar(payload)

        with pytest.raises(ValueError, match="JURIDICO_WEBHOOK_SECRET"):
            processar_webhook(
                payload=payload,
                assinatura_header="qualquer",
                payload_bytes=payload_bytes,
                webhook_secret=None,  # sem segredo
            )

    def test_segredo_via_env_usado_quando_parametro_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Segredo lido de JURIDICO_WEBHOOK_SECRET quando nao passado como parametro."""
        monkeypatch.setenv("JURIDICO_WEBHOOK_SECRET", SEGREDO)
        payload = _payload_valido()
        payload_bytes = _serializar(payload)
        assinatura = _assinar(payload_bytes)

        resultado = processar_webhook(
            payload=payload,
            assinatura_header=assinatura,
            payload_bytes=payload_bytes,
            webhook_secret=None,  # deve ler do env
        )

        assert resultado["processado"] is True


# ===========================================================================
# Testes de payload
# ===========================================================================


class TestWebhookPayload:
    """Testes de validacao de schema e conteudo do payload."""

    def test_payload_malformado_sem_numero_processo(self) -> None:
        """Payload sem numero_processo deve lancar ValueError apos validar assinatura."""
        payload_invalido: dict[str, Any] = {
            "tribunal": TRIBUNAL,
            # numero_processo ausente
        }
        payload_bytes = _serializar(payload_invalido)
        assinatura = _assinar(payload_bytes)

        with pytest.raises(ValueError, match="malformado"):
            processar_webhook(
                payload=payload_invalido,
                assinatura_header=assinatura,
                payload_bytes=payload_bytes,
                webhook_secret=SEGREDO,
            )

    def test_payload_malformado_sem_tribunal(self) -> None:
        """Payload sem tribunal deve lancar ValueError."""
        payload_invalido: dict[str, Any] = {
            "numero_processo": NUMERO,
            # tribunal ausente
        }
        payload_bytes = _serializar(payload_invalido)
        assinatura = _assinar(payload_bytes)

        with pytest.raises(ValueError, match="malformado"):
            processar_webhook(
                payload=payload_invalido,
                assinatura_header=assinatura,
                payload_bytes=payload_bytes,
                webhook_secret=SEGREDO,
            )

    def test_processo_sigiloso_bloqueado(self) -> None:
        """Payload com nivel_sigilo > 0 deve lancar JuridicoSigiloError."""
        payload = _payload_valido(nivel_sigilo=1)
        payload_bytes = _serializar(payload)
        assinatura = _assinar(payload_bytes)

        with pytest.raises(JuridicoSigiloError):
            processar_webhook(
                payload=payload,
                assinatura_header=assinatura,
                payload_bytes=payload_bytes,
                webhook_secret=SEGREDO,
            )

    def test_processo_sigiloso_nao_atualiza_store(self) -> None:
        """Processo sigiloso nao deve ser salvo no store, mesmo com assinatura valida."""
        numero_sigiloso = "99999999920238260100"
        # Garantir que nao existe snapshot antes
        store.remover_snapshot(numero_sigiloso)

        payload = _payload_valido(numero=numero_sigiloso, nivel_sigilo=2)
        payload_bytes = _serializar(payload)
        assinatura = _assinar(payload_bytes)

        with pytest.raises(JuridicoSigiloError):
            processar_webhook(
                payload=payload,
                assinatura_header=assinatura,
                payload_bytes=payload_bytes,
                webhook_secret=SEGREDO,
            )

        snapshot = store.obter_snapshot(numero_sigiloso)
        assert snapshot is None, "Store nao deve conter processo sigiloso"

    def test_payload_sem_movimentacoes_processado(self) -> None:
        """Payload valido sem movimentacoes deve ser aceito (lista vazia permitida)."""
        payload: dict[str, Any] = {
            "numero_processo": NUMERO,
            "tribunal": TRIBUNAL,
            "nivel_sigilo": 0,
            "movimentacoes": [],
        }
        payload_bytes = _serializar(payload)
        assinatura = _assinar(payload_bytes)

        resultado = processar_webhook(
            payload=payload,
            assinatura_header=assinatura,
            payload_bytes=payload_bytes,
            webhook_secret=SEGREDO,
        )

        assert resultado["processado"] is True
        assert resultado["movimentacoes_recebidas"] == 0

    def test_data_ultima_atualizacao_formato_invalido_rejeitado(self) -> None:
        """Regressao MEDIUM-5: data_ultima_atualizacao malformada deve ser rejeitada
        pelo schema Pydantic (AwareDatetime) antes de qualquer processamento."""
        payload: dict[str, Any] = {
            "numero_processo": NUMERO,
            "tribunal": TRIBUNAL,
            "nivel_sigilo": 0,
            "data_ultima_atualizacao": "ontem",  # formato invalido
            "movimentacoes": [],
        }
        payload_bytes = _serializar(payload)
        assinatura = _assinar(payload_bytes)

        with pytest.raises(ValueError, match="malformado"):
            processar_webhook(
                payload=payload,
                assinatura_header=assinatura,
                payload_bytes=payload_bytes,
                webhook_secret=SEGREDO,
            )

    def test_data_ultima_atualizacao_iso_valida_aceita(self) -> None:
        """Data ISO 8601 com fuso horario deve ser aceita pelo schema AwareDatetime."""
        payload: dict[str, Any] = {
            "numero_processo": NUMERO,
            "tribunal": TRIBUNAL,
            "nivel_sigilo": 0,
            "data_ultima_atualizacao": "2024-06-01T12:00:00+00:00",
            "movimentacoes": [],
        }
        payload_bytes = _serializar(payload)
        assinatura = _assinar(payload_bytes)

        resultado = processar_webhook(
            payload=payload,
            assinatura_header=assinatura,
            payload_bytes=payload_bytes,
            webhook_secret=SEGREDO,
        )

        assert resultado["processado"] is True


# ===========================================================================
# Testes de atualizacao do store
# ===========================================================================


class TestWebhookStore:
    """Testes de integracao entre webhook handler e store de snapshots."""

    def test_payload_valido_atualiza_store(self) -> None:
        """Apos processar webhook, snapshot deve estar no store com dados corretos."""
        numero_teste = "11111111120238260100"
        store.remover_snapshot(numero_teste)

        payload = _payload_valido(numero=numero_teste)
        payload_bytes = _serializar(payload)
        assinatura = _assinar(payload_bytes)

        processar_webhook(
            payload=payload,
            assinatura_header=assinatura,
            payload_bytes=payload_bytes,
            webhook_secret=SEGREDO,
        )

        snapshot = store.obter_snapshot(numero_teste)
        assert snapshot is not None
        assert snapshot["numero_processo"] == numero_teste
        assert snapshot["tribunal"] == TRIBUNAL
        assert snapshot["dados"]["fonte"] == "webhook"
        assert len(snapshot["dados"]["movimentacoes"]) == 1

    def test_webhook_subsequente_sobrescreve_snapshot(self) -> None:
        """Segundo webhook para o mesmo processo substitui o snapshot anterior."""
        numero_teste = "22222222220238260100"
        store.remover_snapshot(numero_teste)

        # Primeiro webhook - 1 movimentacao
        payload1 = _payload_valido(numero=numero_teste)
        bytes1 = _serializar(payload1)
        processar_webhook(
            payload=payload1,
            assinatura_header=_assinar(bytes1),
            payload_bytes=bytes1,
            webhook_secret=SEGREDO,
        )

        # Segundo webhook - 2 movimentacoes
        payload2 = {
            **_payload_valido(numero=numero_teste),
            "movimentacoes": [
                {"nome": "Sentenca", "data_hora": "2024-07-01T10:00:00Z"},
                {"nome": "Despacho", "data_hora": "2024-06-01T12:00:00Z"},
            ],
        }
        bytes2 = _serializar(payload2)
        processar_webhook(
            payload=payload2,
            assinatura_header=_assinar(bytes2),
            payload_bytes=bytes2,
            webhook_secret=SEGREDO,
        )

        snapshot = store.obter_snapshot(numero_teste)
        assert snapshot is not None
        assert len(snapshot["dados"]["movimentacoes"]) == 2

    def test_metadados_provider_persistidos_no_store(self) -> None:
        """Metadados do provider devem ser salvos no snapshot para rastreabilidade."""
        numero_teste = "33333333320238260100"
        store.remover_snapshot(numero_teste)

        payload = _payload_valido(numero=numero_teste)
        payload["metadados_provider"] = {"provider": "judit", "id_notificacao": "xyz789"}
        payload_bytes = _serializar(payload)

        processar_webhook(
            payload=payload,
            assinatura_header=_assinar(payload_bytes),
            payload_bytes=payload_bytes,
            webhook_secret=SEGREDO,
        )

        snapshot = store.obter_snapshot(numero_teste)
        assert snapshot is not None
        meta = snapshot["dados"].get("metadados_provider", {})
        assert meta.get("id_notificacao") == "xyz789"

    def test_assinatura_invalida_nao_atualiza_store(self) -> None:
        """Com assinatura invalida, store nao deve ser modificado."""
        numero_teste = "44444444420238260100"
        store.remover_snapshot(numero_teste)

        payload = _payload_valido(numero=numero_teste)
        payload_bytes = _serializar(payload)

        with pytest.raises(WebhookAssinaturaInvalidaError):
            processar_webhook(
                payload=payload,
                assinatura_header="assinatura-invalida",
                payload_bytes=payload_bytes,
                webhook_secret=SEGREDO,
            )

        assert store.obter_snapshot(numero_teste) is None
