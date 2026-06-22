"""Testes dos providers comerciais (Judit, Escavador, TrackJud) com mocks HTTP.

Todos os testes sao deterministicos e nao requerem credencial real.
Usa respx para interceptar chamadas httpx.

Cenarios cobertos por provider:
- Consulta bem-sucedida (happy path)
- Erro de autenticacao (HTTP 401)
- Timeout (httpx.TimeoutException)
- Processo nao encontrado (HTTP 404)
- Processo sigiloso (nivel_sigilo > 0 na resposta)
- verificar_atualizacao com data ISO valida (retorno True/False)
- verificar_atualizacao com data ISO invalida (JuridicoValidationError)
- _parse_movimentacao com data ausente (warning + fallback para now)
"""

from __future__ import annotations

from typing import Any

import pytest
import respx
from httpx import Response, TimeoutException

from mcp_juridico_brasil._core.errors import (
    JuridicoAPIError,
    JuridicoNotFoundError,
    JuridicoSigiloError,
    JuridicoValidationError,
)
from mcp_juridico_brasil.comercial.providers import (
    EscavadorProvider,
    JuditProvider,
    TrackJudProvider,
)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

NUMERO = "00012345620238260100"
TRIBUNAL = "TJSP"
API_KEY = "chave-fake-para-testes"

JUDIT_URL = "https://api.judit.io/v1/processos"
JUDIT_MOV_URL = "https://api.judit.io/v1/processos/movimentacoes"
ESCAVADOR_URL = "https://api.escavador.com/api/v1/processos"
ESCAVADOR_MOV_URL = "https://api.escavador.com/api/v1/processos/movimentacoes"
TRACKJUD_URL = "https://api.trackjud.com.br/v1/processos/consultar"
TRACKJUD_MOV_URL = "https://api.trackjud.com.br/v1/processos/movimentacoes"

# ---------------------------------------------------------------------------
# Fixtures de payload
# ---------------------------------------------------------------------------


def _payload_processo(
    numero: str = NUMERO,
    tribunal: str = TRIBUNAL,
    nivel_sigilo: int = 0,
) -> dict[str, Any]:
    """Payload padrao de processo publico."""
    return {
        "numero_processo": numero,
        "tribunal": tribunal,
        "nivel_sigilo": nivel_sigilo,
        "grau": "G1",
        "data_ajuizamento": "2023-01-15T00:00:00Z",
        "data_ultima_atualizacao": "2024-06-01T12:00:00Z",
        "classe_codigo": 7,
        "classe_nome": "Procedimento Comum Civel",
        "partes": [
            {"nome": "Joao Silva", "tipo": "Autor", "polo": "ativo"},
            {"nome": "Empresa Ltda", "tipo": "Reu", "polo": "passivo"},
        ],
        "assuntos": [{"codigo": 10374, "nome": "Indenizacao por Dano Moral", "principal": True}],
        "orgao_julgador": {
            "codigo": 1,
            "nome": "1a Vara Civel de Sao Paulo",
            "codigo_municipio_ibge": 3550308,
        },
        "movimentacoes": [
            {
                "codigo": 22,
                "nome": "Despacho",
                "data_hora": "2024-06-01T12:00:00Z",
                "complementos": [],
            }
        ],
        "formato": "Eletronico",
        "sistema": "eSAJ",
    }


def _payload_movimentacoes() -> dict[str, Any]:
    """Payload de lista de movimentacoes."""
    return {
        "movimentacoes": [
            {
                "codigo": 22,
                "nome": "Despacho",
                "data_hora": "2024-06-01T12:00:00Z",
                "complementos": [],
            },
            {
                "codigo": 11,
                "nome": "Distribuicao",
                "data_hora": "2023-01-15T09:00:00Z",
                "complementos": [],
            },
        ]
    }


# ===========================================================================
# JUDIT
# ===========================================================================


class TestJuditProviderBuscarProcesso:
    """Testes de buscar_processo para o JuditProvider."""

    @pytest.mark.asyncio
    async def test_consulta_ok_retorna_processo(self) -> None:
        """Happy path: retorna Processo com dados corretos."""
        with respx.mock:
            respx.get(JUDIT_URL).mock(return_value=Response(200, json=_payload_processo()))
            provider = JuditProvider(api_key=API_KEY)
            processo = await provider.buscar_processo(NUMERO, TRIBUNAL)

        assert processo.numero_processo == NUMERO
        assert processo.tribunal == TRIBUNAL
        assert processo.nivel_sigilo == 0
        assert len(processo.partes) == 2
        assert processo.partes[0].nome == "Joao Silva"
        assert len(processo.movimentacoes) == 1

    @pytest.mark.asyncio
    async def test_erro_auth_lanca_juridico_api_error(self) -> None:
        """HTTP 401 deve lancar JuridicoAPIError com status_code 401."""
        with respx.mock:
            respx.get(JUDIT_URL).mock(return_value=Response(401, json={"error": "Unauthorized"}))
            provider = JuditProvider(api_key=API_KEY)
            with pytest.raises(JuridicoAPIError) as exc_info:
                await provider.buscar_processo(NUMERO, TRIBUNAL)

        assert exc_info.value.detail.get("status_code") == 401
        assert "Judit" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_timeout_lanca_juridico_api_error(self) -> None:
        """Timeout deve lancar JuridicoAPIError."""
        with respx.mock:
            respx.get(JUDIT_URL).mock(side_effect=TimeoutException("timeout"))
            provider = JuditProvider(api_key=API_KEY)
            with pytest.raises(JuridicoAPIError) as exc_info:
                await provider.buscar_processo(NUMERO, TRIBUNAL)

        assert "Timeout" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_processo_nao_encontrado_lanca_not_found(self) -> None:
        """HTTP 404 deve lancar JuridicoNotFoundError."""
        with respx.mock:
            respx.get(JUDIT_URL).mock(return_value=Response(404, json={"error": "Not found"}))
            provider = JuditProvider(api_key=API_KEY)
            with pytest.raises(JuridicoNotFoundError):
                await provider.buscar_processo(NUMERO, TRIBUNAL)

    @pytest.mark.asyncio
    async def test_processo_sigiloso_lanca_sigilo_error(self) -> None:
        """Payload com nivel_sigilo > 0 deve lancar JuridicoSigiloError."""
        payload = _payload_processo(nivel_sigilo=1)
        with respx.mock:
            respx.get(JUDIT_URL).mock(return_value=Response(200, json=payload))
            provider = JuditProvider(api_key=API_KEY)
            with pytest.raises(JuridicoSigiloError):
                await provider.buscar_processo(NUMERO, TRIBUNAL)

    @pytest.mark.asyncio
    async def test_erro_500_lanca_api_error(self) -> None:
        """HTTP 500 deve lancar JuridicoAPIError."""
        with respx.mock:
            respx.get(JUDIT_URL).mock(return_value=Response(500, text="Internal Server Error"))
            provider = JuditProvider(api_key=API_KEY)
            with pytest.raises(JuridicoAPIError):
                await provider.buscar_processo(NUMERO, TRIBUNAL)


class TestJuditProviderListarMovimentacoes:
    """Testes de listar_movimentacoes para o JuditProvider."""

    @pytest.mark.asyncio
    async def test_lista_movimentacoes_ok(self) -> None:
        """Happy path: retorna lista de Movimentacao."""
        with respx.mock:
            respx.get(JUDIT_MOV_URL).mock(return_value=Response(200, json=_payload_movimentacoes()))
            provider = JuditProvider(api_key=API_KEY)
            movs = await provider.listar_movimentacoes(NUMERO, TRIBUNAL, limite=20)

        assert len(movs) == 2
        assert movs[0].nome == "Despacho"

    @pytest.mark.asyncio
    async def test_movimentacoes_auth_error(self) -> None:
        """HTTP 401 em movimentacoes deve lancar JuridicoAPIError."""
        with respx.mock:
            respx.get(JUDIT_MOV_URL).mock(return_value=Response(401))
            provider = JuditProvider(api_key=API_KEY)
            with pytest.raises(JuridicoAPIError):
                await provider.listar_movimentacoes(NUMERO, TRIBUNAL)

    @pytest.mark.asyncio
    async def test_movimentacoes_timeout(self) -> None:
        """Timeout em movimentacoes deve lancar JuridicoAPIError."""
        with respx.mock:
            respx.get(JUDIT_MOV_URL).mock(side_effect=TimeoutException("timeout"))
            provider = JuditProvider(api_key=API_KEY)
            with pytest.raises(JuridicoAPIError):
                await provider.listar_movimentacoes(NUMERO, TRIBUNAL)


class TestJuditProviderVerificarAtualizacao:
    """Testes de verificar_atualizacao para o JuditProvider."""

    @pytest.mark.asyncio
    async def test_processo_atualizado_apos_data(self) -> None:
        """Retorna True quando data_ultima_atualizacao e posterior a desde_iso."""
        with respx.mock:
            respx.get(JUDIT_URL).mock(return_value=Response(200, json=_payload_processo()))
            provider = JuditProvider(api_key=API_KEY)
            resultado = await provider.verificar_atualizacao(
                NUMERO, TRIBUNAL, "2024-01-01T00:00:00Z"
            )

        assert resultado is True

    @pytest.mark.asyncio
    async def test_processo_nao_atualizado(self) -> None:
        """Retorna False quando data_ultima_atualizacao e anterior a desde_iso."""
        with respx.mock:
            respx.get(JUDIT_URL).mock(return_value=Response(200, json=_payload_processo()))
            provider = JuditProvider(api_key=API_KEY)
            resultado = await provider.verificar_atualizacao(
                NUMERO, TRIBUNAL, "2025-01-01T00:00:00Z"
            )

        assert resultado is False


# ===========================================================================
# ESCAVADOR
# ===========================================================================


class TestEscavadorProviderBuscarProcesso:
    """Testes de buscar_processo para o EscavadorProvider."""

    @pytest.mark.asyncio
    async def test_consulta_ok_retorna_processo(self) -> None:
        """Happy path com wrapper em 'items'."""
        payload_escavador = {
            "items": [
                {
                    **_payload_processo(),
                    "classe": {"codigo": 7, "nome": "Procedimento Comum Civel"},
                }
            ]
        }
        with respx.mock:
            respx.get(ESCAVADOR_URL).mock(return_value=Response(200, json=payload_escavador))
            provider = EscavadorProvider(api_key=API_KEY)
            processo = await provider.buscar_processo(NUMERO, TRIBUNAL)

        assert processo.numero_processo == NUMERO
        assert processo.nivel_sigilo == 0

    @pytest.mark.asyncio
    async def test_erro_auth_lanca_api_error(self) -> None:
        """HTTP 401 deve lancar JuridicoAPIError."""
        with respx.mock:
            respx.get(ESCAVADOR_URL).mock(return_value=Response(401))
            provider = EscavadorProvider(api_key=API_KEY)
            with pytest.raises(JuridicoAPIError) as exc_info:
                await provider.buscar_processo(NUMERO, TRIBUNAL)

        assert exc_info.value.detail.get("status_code") == 401

    @pytest.mark.asyncio
    async def test_timeout_lanca_api_error(self) -> None:
        """Timeout deve lancar JuridicoAPIError."""
        with respx.mock:
            respx.get(ESCAVADOR_URL).mock(side_effect=TimeoutException("timeout"))
            provider = EscavadorProvider(api_key=API_KEY)
            with pytest.raises(JuridicoAPIError):
                await provider.buscar_processo(NUMERO, TRIBUNAL)

    @pytest.mark.asyncio
    async def test_processo_nao_encontrado(self) -> None:
        """HTTP 404 deve lancar JuridicoNotFoundError."""
        with respx.mock:
            respx.get(ESCAVADOR_URL).mock(return_value=Response(404))
            provider = EscavadorProvider(api_key=API_KEY)
            with pytest.raises(JuridicoNotFoundError):
                await provider.buscar_processo(NUMERO, TRIBUNAL)

    @pytest.mark.asyncio
    async def test_processo_sigiloso_bloqueado(self) -> None:
        """nivel_sigilo > 0 deve lancar JuridicoSigiloError."""
        payload = {"items": [_payload_processo(nivel_sigilo=2)]}
        with respx.mock:
            respx.get(ESCAVADOR_URL).mock(return_value=Response(200, json=payload))
            provider = EscavadorProvider(api_key=API_KEY)
            with pytest.raises(JuridicoSigiloError):
                await provider.buscar_processo(NUMERO, TRIBUNAL)


class TestEscavadorProviderListarMovimentacoes:
    """Testes de listar_movimentacoes para o EscavadorProvider."""

    @pytest.mark.asyncio
    async def test_lista_ok(self) -> None:
        """Happy path em formato Escavador com 'items'."""
        payload = {
            "items": [
                {"codigo_tpu": 22, "tipo": "Despacho", "data": "2024-06-01T12:00:00Z"},
                {"codigo_tpu": 11, "tipo": "Distribuicao", "data": "2023-01-15T09:00:00Z"},
            ]
        }
        with respx.mock:
            respx.get(ESCAVADOR_MOV_URL).mock(return_value=Response(200, json=payload))
            provider = EscavadorProvider(api_key=API_KEY)
            movs = await provider.listar_movimentacoes(NUMERO, TRIBUNAL)

        assert len(movs) == 2
        assert movs[0].nome == "Despacho"

    @pytest.mark.asyncio
    async def test_auth_error(self) -> None:
        """HTTP 401 deve lancar JuridicoAPIError."""
        with respx.mock:
            respx.get(ESCAVADOR_MOV_URL).mock(return_value=Response(401))
            provider = EscavadorProvider(api_key=API_KEY)
            with pytest.raises(JuridicoAPIError):
                await provider.listar_movimentacoes(NUMERO, TRIBUNAL)

    @pytest.mark.asyncio
    async def test_timeout(self) -> None:
        """Timeout deve lancar JuridicoAPIError."""
        with respx.mock:
            respx.get(ESCAVADOR_MOV_URL).mock(side_effect=TimeoutException("timeout"))
            provider = EscavadorProvider(api_key=API_KEY)
            with pytest.raises(JuridicoAPIError):
                await provider.listar_movimentacoes(NUMERO, TRIBUNAL)


# ===========================================================================
# TRACKJUD
# ===========================================================================


class TestTrackJudProviderBuscarProcesso:
    """Testes de buscar_processo para o TrackJudProvider."""

    @pytest.mark.asyncio
    async def test_consulta_ok_retorna_processo(self) -> None:
        """Happy path: TrackJud usa POST com corpo JSON."""
        with respx.mock:
            respx.post(TRACKJUD_URL).mock(return_value=Response(200, json=_payload_processo()))
            provider = TrackJudProvider(api_key=API_KEY)
            processo = await provider.buscar_processo(NUMERO, TRIBUNAL)

        assert processo.numero_processo == NUMERO
        assert processo.tribunal == TRIBUNAL

    @pytest.mark.asyncio
    async def test_erro_auth_lanca_api_error(self) -> None:
        """HTTP 401 deve lancar JuridicoAPIError."""
        with respx.mock:
            respx.post(TRACKJUD_URL).mock(return_value=Response(401))
            provider = TrackJudProvider(api_key=API_KEY)
            with pytest.raises(JuridicoAPIError) as exc_info:
                await provider.buscar_processo(NUMERO, TRIBUNAL)

        assert exc_info.value.detail.get("status_code") == 401

    @pytest.mark.asyncio
    async def test_timeout_lanca_api_error(self) -> None:
        """Timeout deve lancar JuridicoAPIError."""
        with respx.mock:
            respx.post(TRACKJUD_URL).mock(side_effect=TimeoutException("timeout"))
            provider = TrackJudProvider(api_key=API_KEY)
            with pytest.raises(JuridicoAPIError):
                await provider.buscar_processo(NUMERO, TRIBUNAL)

    @pytest.mark.asyncio
    async def test_processo_nao_encontrado(self) -> None:
        """HTTP 404 deve lancar JuridicoNotFoundError."""
        with respx.mock:
            respx.post(TRACKJUD_URL).mock(return_value=Response(404))
            provider = TrackJudProvider(api_key=API_KEY)
            with pytest.raises(JuridicoNotFoundError):
                await provider.buscar_processo(NUMERO, TRIBUNAL)

    @pytest.mark.asyncio
    async def test_processo_sigiloso_bloqueado(self) -> None:
        """nivel_sigilo > 0 deve lancar JuridicoSigiloError."""
        with respx.mock:
            respx.post(TRACKJUD_URL).mock(
                return_value=Response(200, json=_payload_processo(nivel_sigilo=1))
            )
            provider = TrackJudProvider(api_key=API_KEY)
            with pytest.raises(JuridicoSigiloError):
                await provider.buscar_processo(NUMERO, TRIBUNAL)


class TestTrackJudProviderListarMovimentacoes:
    """Testes de listar_movimentacoes para o TrackJudProvider."""

    @pytest.mark.asyncio
    async def test_lista_ok(self) -> None:
        """Happy path: retorna movimentacoes via POST."""
        with respx.mock:
            respx.post(TRACKJUD_MOV_URL).mock(
                return_value=Response(200, json=_payload_movimentacoes())
            )
            provider = TrackJudProvider(api_key=API_KEY)
            movs = await provider.listar_movimentacoes(NUMERO, TRIBUNAL)

        assert len(movs) == 2

    @pytest.mark.asyncio
    async def test_auth_error(self) -> None:
        """HTTP 401 deve lancar JuridicoAPIError."""
        with respx.mock:
            respx.post(TRACKJUD_MOV_URL).mock(return_value=Response(401))
            provider = TrackJudProvider(api_key=API_KEY)
            with pytest.raises(JuridicoAPIError):
                await provider.listar_movimentacoes(NUMERO, TRIBUNAL)

    @pytest.mark.asyncio
    async def test_timeout(self) -> None:
        """Timeout deve lancar JuridicoAPIError."""
        with respx.mock:
            respx.post(TRACKJUD_MOV_URL).mock(side_effect=TimeoutException("timeout"))
            provider = TrackJudProvider(api_key=API_KEY)
            with pytest.raises(JuridicoAPIError):
                await provider.listar_movimentacoes(NUMERO, TRIBUNAL)


# ===========================================================================
# Chave ausente
# ===========================================================================


class TestChaveAusente:
    """Testes de comportamento quando JURIDICO_PROVIDER_API_KEY nao e configurada."""

    def test_judit_sem_chave_lanca_api_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Instanciar JuditProvider sem chave deve lancar JuridicoAPIError."""
        monkeypatch.delenv("JURIDICO_PROVIDER_API_KEY", raising=False)
        with pytest.raises(JuridicoAPIError) as exc_info:
            JuditProvider()  # sem api_key explicita

        assert "JURIDICO_PROVIDER_API_KEY" in str(exc_info.value)

    def test_escavador_sem_chave_lanca_api_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Instanciar EscavadorProvider sem chave deve lancar JuridicoAPIError."""
        monkeypatch.delenv("JURIDICO_PROVIDER_API_KEY", raising=False)
        with pytest.raises(JuridicoAPIError):
            EscavadorProvider()

    def test_trackjud_sem_chave_lanca_api_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Instanciar TrackJudProvider sem chave deve lancar JuridicoAPIError."""
        monkeypatch.delenv("JURIDICO_PROVIDER_API_KEY", raising=False)
        with pytest.raises(JuridicoAPIError):
            TrackJudProvider()


# ===========================================================================
# Regressao: verificar_atualizacao com data invalida (HIGH-3)
# ===========================================================================


class TestVerificarAtualizacaoDataInvalida:
    """Regressao HIGH-3: desde_iso malformado deve lancar JuridicoValidationError
    (nao ValueError cru) em todos os providers.
    """

    @pytest.mark.asyncio
    async def test_judit_data_invalida_lanca_validation_error(self) -> None:
        """JuditProvider.verificar_atualizacao com data malformada lanca JuridicoValidationError."""
        with respx.mock:
            respx.get(JUDIT_URL).mock(return_value=Response(200, json=_payload_processo()))
            provider = JuditProvider(api_key=API_KEY)
            with pytest.raises(JuridicoValidationError) as exc_info:
                await provider.verificar_atualizacao(NUMERO, TRIBUNAL, "hoje")

        assert "desde_iso" in str(exc_info.value)
        assert "ISO 8601" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_escavador_data_invalida_lanca_validation_error(self) -> None:
        """EscavadorProvider.verificar_atualizacao com data malformada lanca JuridicoValidationError."""
        payload_escavador = {"items": [_payload_processo()]}
        with respx.mock:
            respx.get(ESCAVADOR_URL).mock(return_value=Response(200, json=payload_escavador))
            provider = EscavadorProvider(api_key=API_KEY)
            with pytest.raises(JuridicoValidationError):
                await provider.verificar_atualizacao(NUMERO, TRIBUNAL, "2024/06/01")

    @pytest.mark.asyncio
    async def test_trackjud_data_invalida_lanca_validation_error(self) -> None:
        """TrackJudProvider.verificar_atualizacao com data malformada lanca JuridicoValidationError."""
        with respx.mock:
            respx.post(TRACKJUD_URL).mock(return_value=Response(200, json=_payload_processo()))
            provider = TrackJudProvider(api_key=API_KEY)
            with pytest.raises(JuridicoValidationError):
                await provider.verificar_atualizacao(NUMERO, TRIBUNAL, "nao-e-uma-data")


# ===========================================================================
# Regressao: verificar_atualizacao para Escavador e TrackJud (MEDIUM-3)
# ===========================================================================


class TestEscavadorProviderVerificarAtualizacao:
    """Testes de verificar_atualizacao para o EscavadorProvider (cobertura MEDIUM-3)."""

    @pytest.mark.asyncio
    async def test_processo_atualizado_apos_data(self) -> None:
        """Retorna True quando data_ultima_atualizacao e posterior a desde_iso."""
        payload_escavador = {"items": [_payload_processo()]}
        with respx.mock:
            respx.get(ESCAVADOR_URL).mock(return_value=Response(200, json=payload_escavador))
            provider = EscavadorProvider(api_key=API_KEY)
            resultado = await provider.verificar_atualizacao(
                NUMERO, TRIBUNAL, "2024-01-01T00:00:00Z"
            )

        assert resultado is True

    @pytest.mark.asyncio
    async def test_processo_nao_atualizado(self) -> None:
        """Retorna False quando data_ultima_atualizacao e anterior a desde_iso."""
        payload_escavador = {"items": [_payload_processo()]}
        with respx.mock:
            respx.get(ESCAVADOR_URL).mock(return_value=Response(200, json=payload_escavador))
            provider = EscavadorProvider(api_key=API_KEY)
            resultado = await provider.verificar_atualizacao(
                NUMERO, TRIBUNAL, "2025-01-01T00:00:00Z"
            )

        assert resultado is False

    @pytest.mark.asyncio
    async def test_sem_data_ultima_atualizacao_retorna_false(self) -> None:
        """Retorna False quando data_ultima_atualizacao e None no processo."""
        payload_sem_data = {
            "items": [
                {
                    **_payload_processo(),
                    "data_ultima_atualizacao": None,
                }
            ]
        }
        with respx.mock:
            respx.get(ESCAVADOR_URL).mock(return_value=Response(200, json=payload_sem_data))
            provider = EscavadorProvider(api_key=API_KEY)
            resultado = await provider.verificar_atualizacao(
                NUMERO, TRIBUNAL, "2024-01-01T00:00:00Z"
            )

        assert resultado is False


class TestTrackJudProviderVerificarAtualizacao:
    """Testes de verificar_atualizacao para o TrackJudProvider (cobertura MEDIUM-3)."""

    @pytest.mark.asyncio
    async def test_processo_atualizado_apos_data(self) -> None:
        """Retorna True quando data_ultima_atualizacao e posterior a desde_iso."""
        with respx.mock:
            respx.post(TRACKJUD_URL).mock(return_value=Response(200, json=_payload_processo()))
            provider = TrackJudProvider(api_key=API_KEY)
            resultado = await provider.verificar_atualizacao(
                NUMERO, TRIBUNAL, "2024-01-01T00:00:00Z"
            )

        assert resultado is True

    @pytest.mark.asyncio
    async def test_processo_nao_atualizado(self) -> None:
        """Retorna False quando data_ultima_atualizacao e anterior a desde_iso."""
        with respx.mock:
            respx.post(TRACKJUD_URL).mock(return_value=Response(200, json=_payload_processo()))
            provider = TrackJudProvider(api_key=API_KEY)
            resultado = await provider.verificar_atualizacao(
                NUMERO, TRIBUNAL, "2025-01-01T00:00:00Z"
            )

        assert resultado is False

    @pytest.mark.asyncio
    async def test_sem_data_ultima_atualizacao_retorna_false(self) -> None:
        """Retorna False quando data_ultima_atualizacao e None no processo."""
        payload_sem_data = {**_payload_processo(), "data_ultima_atualizacao": None}
        with respx.mock:
            respx.post(TRACKJUD_URL).mock(return_value=Response(200, json=payload_sem_data))
            provider = TrackJudProvider(api_key=API_KEY)
            resultado = await provider.verificar_atualizacao(
                NUMERO, TRIBUNAL, "2024-01-01T00:00:00Z"
            )

        assert resultado is False


# ===========================================================================
# Regressao: _parse_movimentacao com data ausente (MEDIUM-2)
# ===========================================================================


class TestParseMovimentacaoDataAusente:
    """Regressao MEDIUM-2: movimentacao sem data usa datetime.now() com warning."""

    @pytest.mark.asyncio
    async def test_judit_movimentacao_sem_data_usa_fallback(self) -> None:
        """Movimentacao Judit sem data deve usar datetime.now() e emitir warning."""
        payload = _payload_processo()
        # Substituir data por campo ausente
        payload["movimentacoes"] = [{"codigo": 99, "nome": "Sem Data"}]
        with respx.mock:
            respx.get(JUDIT_URL).mock(return_value=Response(200, json=payload))
            provider = JuditProvider(api_key=API_KEY)
            processo = await provider.buscar_processo(NUMERO, TRIBUNAL)

        # Deve ter retornado sem lancar excecao; a movimentacao tem data definida
        assert len(processo.movimentacoes) == 1
        assert processo.movimentacoes[0].data_hora is not None

    @pytest.mark.asyncio
    async def test_escavador_movimentacao_sem_data_usa_fallback(self) -> None:
        """Movimentacao Escavador sem data deve usar datetime.now() sem lancar excecao."""
        payload = {"items": [{**_payload_processo(), "movimentacoes": [{"tipo": "Audiencia"}]}]}
        with respx.mock:
            respx.get(ESCAVADOR_URL).mock(return_value=Response(200, json=payload))
            provider = EscavadorProvider(api_key=API_KEY)
            processo = await provider.buscar_processo(NUMERO, TRIBUNAL)

        assert len(processo.movimentacoes) == 1
        assert processo.movimentacoes[0].data_hora is not None

    @pytest.mark.asyncio
    async def test_trackjud_movimentacao_sem_data_usa_fallback(self) -> None:
        """Movimentacao TrackJud sem data deve usar datetime.now() sem lancar excecao."""
        payload = {**_payload_processo(), "movimentacoes": [{"nome": "Conclusao"}]}
        with respx.mock:
            respx.post(TRACKJUD_URL).mock(return_value=Response(200, json=payload))
            provider = TrackJudProvider(api_key=API_KEY)
            processo = await provider.buscar_processo(NUMERO, TRIBUNAL)

        assert len(processo.movimentacoes) == 1
        assert processo.movimentacoes[0].data_hora is not None
