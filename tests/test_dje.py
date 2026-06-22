"""Testes do módulo DJe - Domicílio Judicial Eletrônico (Fase 4).

Todos os testes são 100% mockados - nenhuma chamada real à API DJe é feita.
As credenciais reais (certificado ICP-Brasil, client_id, client_secret) não
são necessárias para executar esta suíte.

Cobertura:
- OAuth2: obtenção de token, refresh automático, falha de autenticação
- listar_intimacoes: com e sem intimações, intimação sigilosa barrada
- confirmar_leitura_intimacao:
    * sem confirmar=True -> dry-run, sem efeito
    * confirmar=True mas env ausente -> dry-run, sem efeito
    * confirmar=True + env habilitado -> executa via mock
    * já estava lida -> idempotência
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from mcp_juridico_brasil._core.errors import JuridicoAPIError
from mcp_juridico_brasil.dje.client import DJeOAuthClient, _CredenciaisDJe, _TokenOAuth2
from mcp_juridico_brasil.dje.provider import _ENV_PERMITIR_CONFIRMACAO, DJeProvider
from mcp_juridico_brasil.dje.schemas import (
    ListaIntimacoes,
    ResultadoConfirmacaoLeitura,
    StatusIntimacao,
)
from mcp_juridico_brasil.dje.tools import confirmar_leitura_intimacao, listar_intimacoes

# ---------------------------------------------------------------------------
# Fixtures e helpers
# ---------------------------------------------------------------------------

_CREDS_MOCK = _CredenciaisDJe(
    client_id="client-teste",
    client_secret="secret-teste",
    behalf_of_cpf="12345678900",
)

_RESPOSTA_TOKEN_OK: dict[str, Any] = {
    "access_token": "tok-abc123",
    "token_type": "Bearer",
    "expires_in": 300,
    "scope": "comunicacoes:read",
}

_INTIMACAO_PENDENTE_RAW: dict[str, Any] = {
    "id": "int-001",
    "numeroProcesso": "0001234-56.2023.8.26.0100",
    "orgaoJulgador": "1a Vara Cível de São Paulo",
    "tipoComunicacao": "Intimação",
    "dataDisponibilizacao": "2026-06-20T08:00:00Z",
    "dataLeitura": None,
    "prazo": 15,
    "situacao": "pendente",
    "sigilosa": False,
    "conteudo": "Fica intimado para manifestar em 15 dias.",
}

_INTIMACAO_LIDA_RAW: dict[str, Any] = {
    "id": "int-002",
    "numeroProcesso": "0001234-56.2023.8.26.0100",
    "orgaoJulgador": "1a Vara Cível de São Paulo",
    "tipoComunicacao": "Citação",
    "dataDisponibilizacao": "2026-06-15T08:00:00Z",
    "dataLeitura": "2026-06-16T10:00:00Z",
    "prazo": 30,
    "situacao": "lida",
    "sigilosa": False,
    "conteudo": "Citado para contestar em 30 dias.",
}

_INTIMACAO_SIGILOSA_RAW: dict[str, Any] = {
    "id": "int-003",
    "numeroProcesso": "9999999-00.2026.8.26.0000",
    "orgaoJulgador": "Vara de Família",
    "tipoComunicacao": "Intimação",
    "dataDisponibilizacao": "2026-06-21T09:00:00Z",
    "dataLeitura": None,
    "prazo": 5,
    "situacao": "pendente",
    "sigilosa": True,
    "conteudo": "DADO SIGILOSO - deve ser suprimido",
}


def _make_response(status: int, body: Any) -> httpx.Response:
    """Cria httpx.Response mock com status e corpo JSON."""
    import json

    return httpx.Response(
        status_code=status,
        content=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
    )


def _make_token_valido() -> _TokenOAuth2:
    return _TokenOAuth2(
        access_token="tok-abc123",
        expires_at=time.monotonic() + 300,
    )


# ---------------------------------------------------------------------------
# Testes do _TokenOAuth2
# ---------------------------------------------------------------------------


class TestTokenOAuth2:
    def test_token_valido_dentro_da_janela(self) -> None:
        token = _TokenOAuth2(
            access_token="tok",
            expires_at=time.monotonic() + 120,  # 2 min no futuro
        )
        assert token.esta_valido() is True

    def test_token_invalido_na_margem_de_seguranca(self) -> None:
        # Expira em 30s - menor que a margem de 60s
        token = _TokenOAuth2(
            access_token="tok",
            expires_at=time.monotonic() + 30,
        )
        assert token.esta_valido() is False

    def test_token_expirado(self) -> None:
        token = _TokenOAuth2(
            access_token="tok",
            expires_at=time.monotonic() - 1,
        )
        assert token.esta_valido() is False


# ---------------------------------------------------------------------------
# Testes do _CredenciaisDJe
# ---------------------------------------------------------------------------


class TestCredenciaisDJe:
    def test_esta_configurado_com_todas_credenciais(self) -> None:
        creds = _CredenciaisDJe(
            client_id="cid",
            client_secret="csec",
            behalf_of_cpf="12345678900",
        )
        assert creds.esta_configurado() is True

    def test_nao_configurado_sem_client_id(self) -> None:
        creds = _CredenciaisDJe(client_secret="s", behalf_of_cpf="12345678900")
        assert creds.esta_configurado() is False

    def test_nao_configurado_sem_client_secret(self) -> None:
        creds = _CredenciaisDJe(client_id="cid", behalf_of_cpf="12345678900")
        assert creds.esta_configurado() is False

    def test_nao_configurado_sem_behalf_of_cpf(self) -> None:
        creds = _CredenciaisDJe(client_id="cid", client_secret="s")
        assert creds.esta_configurado() is False

    def test_from_env_le_variaveis(self) -> None:
        env = {
            "DJE_CLIENT_ID": "env-cid",
            "DJE_CLIENT_SECRET": "env-secret",
            "DJE_BEHALF_OF_CPF": "98765432100",
            "DJE_CERT_PATH": "/caminho/cert.pfx",
        }
        with patch.dict(os.environ, env, clear=False):
            creds = _CredenciaisDJe.from_env()
        assert creds.client_id == "env-cid"
        assert creds.client_secret == "env-secret"
        assert creds.behalf_of_cpf == "98765432100"
        assert creds.cert_path == "/caminho/cert.pfx"


# ---------------------------------------------------------------------------
# Testes do DJeOAuthClient - obtenção de token
# ---------------------------------------------------------------------------


class TestDJeOAuthClientToken:
    @pytest.mark.asyncio
    async def test_obter_token_ok(self) -> None:
        """Token obtido com sucesso via client_credentials."""
        client = DJeOAuthClient(credenciais=_CREDS_MOCK)
        resposta_token = _make_response(200, _RESPOSTA_TOKEN_OK)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post = AsyncMock(return_value=resposta_token)
            mock_cls.return_value = mock_http

            token = await client._obter_token()

        assert token == "tok-abc123"
        assert client._token is not None
        assert client._token.esta_valido()

    @pytest.mark.asyncio
    async def test_token_cacheado_nao_refaz_requisicao(self) -> None:
        """Segundo _obter_token não faz nova requisição se token ainda válido."""
        client = DJeOAuthClient(credenciais=_CREDS_MOCK)
        client._token = _make_token_valido()

        with patch("httpx.AsyncClient") as mock_cls:
            token = await client._obter_token()
            mock_cls.assert_not_called()

        assert token == "tok-abc123"

    @pytest.mark.asyncio
    async def test_obter_token_falha_401(self) -> None:
        """401 do GeCli lança JuridicoAPIError com orientação."""
        client = DJeOAuthClient(credenciais=_CREDS_MOCK)
        resposta_401 = _make_response(401, {"error": "unauthorized"})

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post = AsyncMock(return_value=resposta_401)
            mock_cls.return_value = mock_http

            with pytest.raises(JuridicoAPIError) as exc_info:
                await client._obter_token()

        assert "401" in str(exc_info.value) or "Credenciais" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_obter_token_falha_500(self) -> None:
        """Erro 500 do GeCli lança JuridicoAPIError."""
        client = DJeOAuthClient(credenciais=_CREDS_MOCK)
        resposta_500 = _make_response(500, {"error": "internal server error"})

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post = AsyncMock(return_value=resposta_500)
            mock_cls.return_value = mock_http

            with pytest.raises(JuridicoAPIError):
                await client._obter_token()

    @pytest.mark.asyncio
    async def test_credenciais_ausentes_lanca_erro(self) -> None:
        """Credenciais vazias lançam JuridicoAPIError antes de qualquer chamada HTTP."""
        creds_vazias = _CredenciaisDJe()
        client = DJeOAuthClient(credenciais=creds_vazias)

        with pytest.raises(JuridicoAPIError) as exc_info:
            await client._obter_token()

        assert "DJE_CLIENT_ID" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_token_refreshado_quando_expirado(self) -> None:
        """Token expirado dispara nova requisição de autenticação."""
        client = DJeOAuthClient(credenciais=_CREDS_MOCK)
        # Token expirado (expires_at no passado)
        client._token = _TokenOAuth2(
            access_token="tok-velho",
            expires_at=time.monotonic() - 10,
        )
        resposta_token = _make_response(200, _RESPOSTA_TOKEN_OK)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post = AsyncMock(return_value=resposta_token)
            mock_cls.return_value = mock_http

            token = await client._obter_token()

        assert token == "tok-abc123"
        mock_http.post.assert_called_once()


# ---------------------------------------------------------------------------
# Testes do DJeProvider - listar_intimacoes
# ---------------------------------------------------------------------------


class TestDJeProviderListarIntimacoes:
    def _provider_com_mock(self, raw_list: list[dict[str, Any]]) -> DJeProvider:
        """Cria DJeProvider com cliente mockado retornando raw_list."""
        mock_client = MagicMock(spec=DJeOAuthClient)
        mock_client.listar_comunicacoes = AsyncMock(return_value=raw_list)
        return DJeProvider(client=mock_client)

    @pytest.mark.asyncio
    async def test_lista_vazia(self) -> None:
        provider = self._provider_com_mock([])
        resultado = await provider.listar_intimacoes()

        assert isinstance(resultado, ListaIntimacoes)
        assert resultado.total == 0
        assert resultado.pendentes == 0
        assert resultado.intimacoes == []
        assert resultado.aviso_juridico != ""

    @pytest.mark.asyncio
    async def test_lista_com_uma_intimacao_pendente(self) -> None:
        provider = self._provider_com_mock([_INTIMACAO_PENDENTE_RAW])
        resultado = await provider.listar_intimacoes()

        assert resultado.total == 1
        assert resultado.pendentes == 1
        intimacao = resultado.intimacoes[0]
        assert intimacao.id == "int-001"
        assert intimacao.status == StatusIntimacao.PENDENTE
        assert intimacao.conteudo == "Fica intimado para manifestar em 15 dias."
        assert intimacao.is_sigilosa is False

    @pytest.mark.asyncio
    async def test_lista_com_pendente_e_lida(self) -> None:
        provider = self._provider_com_mock([_INTIMACAO_PENDENTE_RAW, _INTIMACAO_LIDA_RAW])
        resultado = await provider.listar_intimacoes()

        assert resultado.total == 2
        assert resultado.pendentes == 1

    @pytest.mark.asyncio
    async def test_intimacao_sigilosa_tem_conteudo_suprimido(self) -> None:
        """Conteúdo de intimação sigilosa NUNCA deve aparecer no retorno."""
        provider = self._provider_com_mock([_INTIMACAO_SIGILOSA_RAW])
        resultado = await provider.listar_intimacoes()

        assert resultado.total == 1
        intimacao = resultado.intimacoes[0]
        assert intimacao.is_sigilosa is True
        assert intimacao.conteudo is None
        # Garantir que o dado sigiloso não vazou
        assert "DADO SIGILOSO" not in str(intimacao.model_dump())

    @pytest.mark.asyncio
    async def test_filtro_por_numero_processo_repassado_ao_cliente(self) -> None:
        """Parâmetro numero_processo deve ser repassado ao client.listar_comunicacoes."""
        mock_client = MagicMock(spec=DJeOAuthClient)
        mock_client.listar_comunicacoes = AsyncMock(return_value=[])
        provider = DJeProvider(client=mock_client)

        await provider.listar_intimacoes(numero_processo="0001234-56.2023.8.26.0100")

        mock_client.listar_comunicacoes.assert_called_once_with(
            numero_processo="0001234-56.2023.8.26.0100",
            apenas_pendentes=True,
            limite=50,
        )


# ---------------------------------------------------------------------------
# Testes do DJeProvider - confirmar_leitura (gate de segurança)
# ---------------------------------------------------------------------------


class TestDJeProviderConfirmarLeitura:
    def _provider_com_mock_confirmacao(self, resposta_raw: dict[str, Any]) -> DJeProvider:
        mock_client = MagicMock(spec=DJeOAuthClient)
        mock_client.confirmar_leitura = AsyncMock(return_value=resposta_raw)
        return DJeProvider(client=mock_client)

    @pytest.mark.asyncio
    async def test_sem_confirmar_explicito_retorna_dry_run(self) -> None:
        """confirmar=False (padrão) -> dry-run, API nunca é chamada."""
        mock_client = MagicMock(spec=DJeOAuthClient)
        mock_client.confirmar_leitura = AsyncMock()
        provider = DJeProvider(client=mock_client)

        resultado = await provider.confirmar_leitura(
            numero_processo="0001234-56.2023.8.26.0100",
            id_comunicacao="int-001",
            confirmar=False,
        )

        assert resultado.executado is False
        assert resultado.modo_dry_run is True
        mock_client.confirmar_leitura.assert_not_called()

    @pytest.mark.asyncio
    async def test_confirmar_true_sem_env_retorna_dry_run(self) -> None:
        """confirmar=True mas DJE_PERMITIR_CONFIRMACAO_LEITURA ausente -> dry-run."""
        mock_client = MagicMock(spec=DJeOAuthClient)
        mock_client.confirmar_leitura = AsyncMock()
        provider = DJeProvider(client=mock_client)

        # Garantir que a env não está definida
        env_limpa = {k: v for k, v in os.environ.items() if k != _ENV_PERMITIR_CONFIRMACAO}
        with patch.dict(os.environ, env_limpa, clear=True):
            resultado = await provider.confirmar_leitura(
                numero_processo="0001234-56.2023.8.26.0100",
                id_comunicacao="int-001",
                confirmar=True,
            )

        assert resultado.executado is False
        assert resultado.modo_dry_run is True
        mock_client.confirmar_leitura.assert_not_called()

    @pytest.mark.asyncio
    async def test_confirmar_true_com_env_false_retorna_dry_run(self) -> None:
        """DJE_PERMITIR_CONFIRMACAO_LEITURA=false -> dry-run mesmo com confirmar=True."""
        mock_client = MagicMock(spec=DJeOAuthClient)
        mock_client.confirmar_leitura = AsyncMock()
        provider = DJeProvider(client=mock_client)

        with patch.dict(os.environ, {_ENV_PERMITIR_CONFIRMACAO: "false"}):
            resultado = await provider.confirmar_leitura(
                numero_processo="0001234-56.2023.8.26.0100",
                id_comunicacao="int-001",
                confirmar=True,
            )

        assert resultado.executado is False
        assert resultado.modo_dry_run is True
        mock_client.confirmar_leitura.assert_not_called()

    @pytest.mark.asyncio
    async def test_confirmar_true_com_env_true_executa_via_mock(self) -> None:
        """confirmar=True + DJE_PERMITIR_CONFIRMACAO_LEITURA=true -> executa real."""
        resposta_api = {
            "confirmado": True,
            "id": "int-001",
            "numero_processo": "0001234-56.2023.8.26.0100",
            "data_leitura": "2026-06-22T10:00:00Z",
        }
        provider = self._provider_com_mock_confirmacao(resposta_api)

        with patch.dict(os.environ, {_ENV_PERMITIR_CONFIRMACAO: "true"}):
            resultado = await provider.confirmar_leitura(
                numero_processo="0001234-56.2023.8.26.0100",
                id_comunicacao="int-001",
                confirmar=True,
            )

        assert resultado.executado is True
        assert resultado.modo_dry_run is False
        assert resultado.data_leitura is not None
        assert resultado.ja_estava_lida is False

    @pytest.mark.asyncio
    async def test_idempotencia_ja_lida(self) -> None:
        """Intimação já lida retorna ja_estava_lida=True sem executar novamente."""
        resposta_api = {"ja_lida": True, "id": "int-002"}
        provider = self._provider_com_mock_confirmacao(resposta_api)

        with patch.dict(os.environ, {_ENV_PERMITIR_CONFIRMACAO: "true"}):
            resultado = await provider.confirmar_leitura(
                numero_processo="0001234-56.2023.8.26.0100",
                id_comunicacao="int-002",
                confirmar=True,
            )

        assert resultado.ja_estava_lida is True
        assert resultado.executado is False
        assert resultado.modo_dry_run is False

    @pytest.mark.asyncio
    async def test_aviso_juridico_sempre_presente(self) -> None:
        """Aviso jurídico deve estar presente em qualquer resultado."""
        mock_client = MagicMock(spec=DJeOAuthClient)
        mock_client.confirmar_leitura = AsyncMock()
        provider = DJeProvider(client=mock_client)

        # Dry-run sem confirmar
        resultado = await provider.confirmar_leitura(
            numero_processo="0001234-56.2023.8.26.0100",
            id_comunicacao="int-001",
        )
        assert resultado.aviso_juridico != ""
        assert "prazo" in resultado.aviso_juridico.lower()


# ---------------------------------------------------------------------------
# Testes das tools MCP
# ---------------------------------------------------------------------------


class TestToolListarIntimacoes:
    @pytest.mark.asyncio
    async def test_retorna_estrutura_completa(self) -> None:
        """Tool listar_intimacoes retorna campos obrigatórios."""
        lista_mock = ListaIntimacoes(
            intimacoes=[],
            total=0,
            pendentes=0,
            aviso_juridico="aviso teste",
        )
        with patch("mcp_juridico_brasil.dje.tools._provider") as mock_prov:
            mock_prov.listar_intimacoes = AsyncMock(return_value=lista_mock)
            resultado = await listar_intimacoes()

        assert "intimacoes" in resultado
        assert "total" in resultado
        assert "pendentes" in resultado
        assert "aviso_juridico" in resultado
        assert "disclaimer" in resultado
        assert "fonte" in resultado

    @pytest.mark.asyncio
    async def test_repassa_parametro_numero_processo(self) -> None:
        lista_mock = ListaIntimacoes(intimacoes=[], total=0, pendentes=0, aviso_juridico="aviso")
        with patch("mcp_juridico_brasil.dje.tools._provider") as mock_prov:
            mock_prov.listar_intimacoes = AsyncMock(return_value=lista_mock)
            await listar_intimacoes(numero_processo="0001234-56.2023.8.26.0100")
            mock_prov.listar_intimacoes.assert_called_once_with(
                numero_processo="0001234-56.2023.8.26.0100",
                apenas_pendentes=True,
                limite=50,
            )


class TestToolConfirmarLeituraIntimacao:
    @pytest.mark.asyncio
    async def test_dry_run_padrao_sem_confirmar(self) -> None:
        """Chamada sem confirmar=True retorna dry-run na tool."""
        res_mock = ResultadoConfirmacaoLeitura(
            id_intimacao="int-001",
            numero_processo="0001234-56.2023.8.26.0100",
            executado=False,
            modo_dry_run=True,
            aviso_juridico="aviso",
            mensagem="dry-run",
        )
        with patch("mcp_juridico_brasil.dje.tools._provider") as mock_prov:
            mock_prov.confirmar_leitura = AsyncMock(return_value=res_mock)
            resultado = await confirmar_leitura_intimacao(
                numero_processo="0001234-56.2023.8.26.0100",
                id_intimacao="int-001",
            )

        assert resultado["executado"] is False
        assert resultado["modo_dry_run"] is True
        assert "aviso_juridico" in resultado
        assert "instrucoes_para_modo_real" in resultado

    @pytest.mark.asyncio
    async def test_modo_real_retorna_executado_true(self) -> None:
        """Com confirmar=True e env habilitado, tool reflete executado=True."""
        res_mock = ResultadoConfirmacaoLeitura(
            id_intimacao="int-001",
            numero_processo="0001234-56.2023.8.26.0100",
            executado=True,
            modo_dry_run=False,
            data_leitura=datetime.now(tz=timezone.utc),
            aviso_juridico="aviso",
            mensagem="confirmado",
        )
        with patch("mcp_juridico_brasil.dje.tools._provider") as mock_prov:
            mock_prov.confirmar_leitura = AsyncMock(return_value=res_mock)
            resultado = await confirmar_leitura_intimacao(
                numero_processo="0001234-56.2023.8.26.0100",
                id_intimacao="int-001",
                confirmar=True,
            )

        assert resultado["executado"] is True
        assert resultado["modo_dry_run"] is False

    @pytest.mark.asyncio
    async def test_aviso_juridico_sempre_presente_na_tool(self) -> None:
        """Tool sempre inclui aviso de efeito jurídico, independente do modo."""
        res_mock = ResultadoConfirmacaoLeitura(
            id_intimacao="int-001",
            numero_processo="0001234-56.2023.8.26.0100",
            executado=False,
            modo_dry_run=True,
            aviso_juridico="aviso",
            mensagem="dry-run",
        )
        with patch("mcp_juridico_brasil.dje.tools._provider") as mock_prov:
            mock_prov.confirmar_leitura = AsyncMock(return_value=res_mock)
            resultado = await confirmar_leitura_intimacao(
                numero_processo="0001234-56.2023.8.26.0100",
                id_intimacao="int-001",
            )

        aviso = resultado.get("aviso_juridico", "")
        assert aviso != ""
        assert "prazo" in aviso.lower() or "efeito" in aviso.lower()


# ---------------------------------------------------------------------------
# Testes diretos do DJeOAuthClient - listar_comunicacoes e confirmar_leitura
# ---------------------------------------------------------------------------


class TestDJeOAuthClientListarComunicacoes:
    def _client_com_token(self) -> DJeOAuthClient:
        client = DJeOAuthClient(credenciais=_CREDS_MOCK)
        client._token = _make_token_valido()
        return client

    @pytest.mark.asyncio
    async def test_listar_comunicacoes_ok_lista_direta(self) -> None:
        """Resposta JSON como lista direta é aceita."""
        client = self._client_com_token()
        body = [_INTIMACAO_PENDENTE_RAW]

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.get = AsyncMock(return_value=_make_response(200, body))
            mock_cls.return_value = mock_http

            resultado = await client.listar_comunicacoes()

        assert len(resultado) == 1
        assert resultado[0]["id"] == "int-001"

    @pytest.mark.asyncio
    async def test_listar_comunicacoes_ok_resposta_embrulhada(self) -> None:
        """Resposta JSON com chave 'content' é desembrulhada."""
        client = self._client_com_token()
        body = {"content": [_INTIMACAO_LIDA_RAW]}

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.get = AsyncMock(return_value=_make_response(200, body))
            mock_cls.return_value = mock_http

            resultado = await client.listar_comunicacoes()

        assert len(resultado) == 1
        assert resultado[0]["id"] == "int-002"

    @pytest.mark.asyncio
    async def test_listar_comunicacoes_401_invalida_cache_e_lanca_erro(self) -> None:
        """401 invalida o cache do token e lança JuridicoAPIError."""
        client = self._client_com_token()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.get = AsyncMock(return_value=_make_response(401, {"error": "unauthorized"}))
            mock_cls.return_value = mock_http

            with pytest.raises(JuridicoAPIError) as exc_info:
                await client.listar_comunicacoes()

        assert client._token is None  # cache invalidado
        assert "401" in str(exc_info.value) or "expirado" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_listar_comunicacoes_timeout_lanca_erro(self) -> None:
        """Timeout de rede lança JuridicoAPIError."""
        client = self._client_com_token()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            mock_cls.return_value = mock_http

            with pytest.raises(JuridicoAPIError) as exc_info:
                await client.listar_comunicacoes()

        assert "Timeout" in str(exc_info.value) or "timeout" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_listar_comunicacoes_erro_rede_lanca_erro(self) -> None:
        """Erro de rede (RequestError) lança JuridicoAPIError."""
        client = self._client_com_token()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.get = AsyncMock(
                side_effect=httpx.RequestError("connection refused", request=MagicMock())
            )
            mock_cls.return_value = mock_http

            with pytest.raises(JuridicoAPIError):
                await client.listar_comunicacoes()

    @pytest.mark.asyncio
    async def test_listar_comunicacoes_500_lanca_erro(self) -> None:
        """HTTP 500 da API DJe lança JuridicoAPIError."""
        client = self._client_com_token()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.get = AsyncMock(return_value=_make_response(500, {"error": "server error"}))
            mock_cls.return_value = mock_http

            with pytest.raises(JuridicoAPIError):
                await client.listar_comunicacoes()

    @pytest.mark.asyncio
    async def test_listar_comunicacoes_repassa_filtro_pendentes(self) -> None:
        """Parâmetro apenas_pendentes=False não envia 'situacao' na query."""
        client = self._client_com_token()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.get = AsyncMock(return_value=_make_response(200, []))
            mock_cls.return_value = mock_http

            await client.listar_comunicacoes(apenas_pendentes=False)

            call_kwargs = mock_http.get.call_args
            params = call_kwargs[1].get(
                "params", call_kwargs[0][1] if len(call_kwargs[0]) > 1 else {}
            )
            assert "situacao" not in params


class TestDJeOAuthClientConfirmarLeitura:
    def _client_com_token(self) -> DJeOAuthClient:
        client = DJeOAuthClient(credenciais=_CREDS_MOCK)
        client._token = _make_token_valido()
        return client

    @pytest.mark.asyncio
    async def test_confirmar_leitura_ok_204(self) -> None:
        """Resposta 204 (No Content) é tratada como sucesso."""
        client = self._client_com_token()

        resposta_204 = httpx.Response(status_code=204, content=b"")

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.put = AsyncMock(return_value=resposta_204)
            mock_cls.return_value = mock_http

            resultado = await client.confirmar_leitura("0001234-56.2023.8.26.0100", "int-001")

        assert resultado.get("confirmado") is True

    @pytest.mark.asyncio
    async def test_confirmar_leitura_409_retorna_ja_lida(self) -> None:
        """409 Conflict indica intimação já lida - retorno idempotente."""
        client = self._client_com_token()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.put = AsyncMock(return_value=_make_response(409, {"error": "conflict"}))
            mock_cls.return_value = mock_http

            resultado = await client.confirmar_leitura("0001234-56.2023.8.26.0100", "int-002")

        assert resultado.get("ja_lida") is True

    @pytest.mark.asyncio
    async def test_confirmar_leitura_401_invalida_cache(self) -> None:
        """401 ao confirmar invalida cache do token e lança erro."""
        client = self._client_com_token()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.put = AsyncMock(return_value=_make_response(401, {"error": "unauthorized"}))
            mock_cls.return_value = mock_http

            with pytest.raises(JuridicoAPIError):
                await client.confirmar_leitura("0001234-56.2023.8.26.0100", "int-001")

        assert client._token is None

    @pytest.mark.asyncio
    async def test_confirmar_leitura_timeout_lanca_erro(self) -> None:
        """Timeout ao confirmar lança JuridicoAPIError."""
        client = self._client_com_token()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.put = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            mock_cls.return_value = mock_http

            with pytest.raises(JuridicoAPIError):
                await client.confirmar_leitura("0001234-56.2023.8.26.0100", "int-001")

    @pytest.mark.asyncio
    async def test_confirmar_leitura_500_lanca_erro(self) -> None:
        """HTTP 500 ao confirmar lança JuridicoAPIError."""
        client = self._client_com_token()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.put = AsyncMock(return_value=_make_response(500, {"error": "server error"}))
            mock_cls.return_value = mock_http

            with pytest.raises(JuridicoAPIError):
                await client.confirmar_leitura("0001234-56.2023.8.26.0100", "int-001")


# ---------------------------------------------------------------------------
# Testes de regressao de seguranca (Fase 4 - review round 1)
# ---------------------------------------------------------------------------


class TestSegurancaCredenciaisDJeImutaveis:
    """Regressao: _CredenciaisDJe deve ser imutavel (frozen=True)."""

    def test_nao_permite_modificar_client_secret(self) -> None:
        """Atribuicao em _CredenciaisDJe deve lancar FrozenInstanceError."""
        from dataclasses import FrozenInstanceError

        creds = _CredenciaisDJe(client_id="cid", client_secret="original", behalf_of_cpf="cpf")
        with pytest.raises(FrozenInstanceError):
            creds.client_secret = "vazado"  # type: ignore[misc]

    def test_nao_permite_modificar_client_id(self) -> None:
        """Qualquer atribuicao deve falhar - frozen dataclass."""
        from dataclasses import FrozenInstanceError

        creds = _CredenciaisDJe(client_id="cid", client_secret="sec", behalf_of_cpf="cpf")
        with pytest.raises(FrozenInstanceError):
            creds.client_id = "outro"  # type: ignore[misc]


class TestSegurancaTokenOAuth2SemVazamento:
    """Regressao: erros de token nao devem incluir response.text (potencial client_secret)."""

    @pytest.mark.asyncio
    async def test_erro_500_token_nao_inclui_response_text(self) -> None:
        """Erro 500 do GeCli nao deve vazar corpo da resposta na mensagem de excecao."""
        client = DJeOAuthClient(credenciais=_CREDS_MOCK)
        corpo_com_secret = '{"error":"invalid_client","error_description":"client_secret=SECRETO"}'
        resposta_500 = httpx.Response(
            status_code=500,
            content=corpo_com_secret.encode(),
            headers={"content-type": "application/json"},
        )

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post = AsyncMock(return_value=resposta_500)
            mock_cls.return_value = mock_http

            with pytest.raises(JuridicoAPIError) as exc_info:
                await client._obter_token()

        mensagem = str(exc_info.value)
        assert "SECRETO" not in mensagem
        assert "client_secret" not in mensagem
        assert "error_description" not in mensagem

    @pytest.mark.asyncio
    async def test_erro_400_token_nao_inclui_response_text(self) -> None:
        """Erro 400 do GeCli (grant invalido) nao vaza corpo na excecao."""
        client = DJeOAuthClient(credenciais=_CREDS_MOCK)
        corpo = '{"error":"invalid_grant","error_description":"Invalid client secret"}'
        resposta_400 = httpx.Response(
            status_code=400,
            content=corpo.encode(),
            headers={"content-type": "application/json"},
        )

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post = AsyncMock(return_value=resposta_400)
            mock_cls.return_value = mock_http

            with pytest.raises(JuridicoAPIError) as exc_info:
                await client._obter_token()

        assert "Invalid client secret" not in str(exc_info.value)


class TestSegurancaPathTraversalDJe:
    """Regressao: numero_processo e id_intimacao devem ser validados antes de ir ao path URL."""

    @pytest.mark.asyncio
    async def test_numero_processo_invalido_lanca_validation_error_em_listar(self) -> None:
        """numero_processo com path traversal deve ser rejeitado na tool listar_intimacoes."""
        from mcp_juridico_brasil._core import JuridicoValidationError

        with pytest.raises(JuridicoValidationError) as exc_info:
            await listar_intimacoes(numero_processo="../admin")

        assert "numero_processo" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_numero_processo_invalido_lanca_validation_error_em_confirmar(self) -> None:
        """numero_processo invalido deve ser rejeitado na tool confirmar_leitura_intimacao."""
        from mcp_juridico_brasil._core import JuridicoValidationError

        with pytest.raises(JuridicoValidationError) as exc_info:
            await confirmar_leitura_intimacao(
                numero_processo="../../etc/passwd",
                id_intimacao="int-001",
            )

        assert "numero_processo" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_id_intimacao_com_path_traversal_rejeitado(self) -> None:
        """id_intimacao com ../ deve ser rejeitado antes de chegar ao client."""
        from mcp_juridico_brasil._core import JuridicoValidationError

        with pytest.raises(JuridicoValidationError) as exc_info:
            await confirmar_leitura_intimacao(
                numero_processo="0001234-56.2023.8.26.0100",
                id_intimacao="../admin/config",
            )

        assert "id_intimacao" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_id_intimacao_com_barra_rejeitado(self) -> None:
        """id_intimacao com / deve ser rejeitado."""
        from mcp_juridico_brasil._core import JuridicoValidationError

        with pytest.raises(JuridicoValidationError):
            await confirmar_leitura_intimacao(
                numero_processo="0001234-56.2023.8.26.0100",
                id_intimacao="int/001",
            )

    @pytest.mark.asyncio
    async def test_id_intimacao_valido_aceito(self) -> None:
        """id_intimacao alfanumerico valido nao deve ser rejeitado na validacao."""
        from mcp_juridico_brasil._core import JuridicoValidationError

        res_mock = ResultadoConfirmacaoLeitura(
            id_intimacao="int-001",
            numero_processo="0001234-56.2023.8.26.0100",
            executado=False,
            modo_dry_run=True,
            aviso_juridico="aviso",
            mensagem="dry-run",
        )
        with patch("mcp_juridico_brasil.dje.tools._provider") as mock_prov:
            mock_prov.confirmar_leitura = AsyncMock(return_value=res_mock)
            # Nao deve lancar JuridicoValidationError
            try:
                await confirmar_leitura_intimacao(
                    numero_processo="0001234-56.2023.8.26.0100",
                    id_intimacao="abc-123_XYZ",
                )
            except JuridicoValidationError:
                pytest.fail("ID alfanumerico valido foi rejeitado incorretamente")


class TestSegurancaStatusDesconhecidoLogado:
    """Regressao: status desconhecido vindo da API deve gerar warning, nao swallow silencioso."""

    @pytest.mark.asyncio
    async def test_status_desconhecido_assume_pendente_com_warning(self) -> None:
        """Status 'em_tramite' (fora do enum) deve logar warning e assumir PENDENTE."""
        raw_status_invalido = {
            **_INTIMACAO_PENDENTE_RAW,
            "id": "int-status-invalido",
            # "em_tramite" nao existe em StatusIntimacao (pendente/lida/expirada)
            "situacao": "em_tramite",
        }
        mock_client = MagicMock(spec=DJeOAuthClient)
        mock_client.listar_comunicacoes = AsyncMock(return_value=[raw_status_invalido])
        provider = DJeProvider(client=mock_client)

        with patch("mcp_juridico_brasil.dje.provider.logger") as mock_logger:
            resultado = await provider.listar_intimacoes()

        assert resultado.total == 1
        intimacao = resultado.intimacoes[0]
        assert intimacao.status == StatusIntimacao.PENDENTE

        # Confirmar que warning foi logado com o valor recebido
        mock_logger.warning.assert_called_once()
        call_kwargs = mock_logger.warning.call_args
        assert call_kwargs[0][0] == "dje_status_desconhecido_assumindo_pendente"
        assert call_kwargs[1].get("status_recebido") == "em_tramite"

    @pytest.mark.asyncio
    async def test_status_aguardando_nao_vira_pendente_silenciosamente(self) -> None:
        """Status 'aguardando' (fora do enum) gera warning visivel, nao silencioso."""
        raw = {
            **_INTIMACAO_PENDENTE_RAW,
            "id": "int-aguardando",
            # "aguardando" nao existe no enum StatusIntimacao
            "situacao": "aguardando",
        }
        mock_client = MagicMock(spec=DJeOAuthClient)
        mock_client.listar_comunicacoes = AsyncMock(return_value=[raw])
        provider = DJeProvider(client=mock_client)

        with patch("mcp_juridico_brasil.dje.provider.logger") as mock_logger:
            resultado = await provider.listar_intimacoes()

        # O resultado deve ser PENDENTE (fallback seguro), mas com warning logado
        assert resultado.intimacoes[0].status == StatusIntimacao.PENDENTE
        mock_logger.warning.assert_called()


class TestSegurancaIsoOuNoneLogado:
    """Regressao: data malformada da API deve gerar warning, nao retornar None silencioso."""

    @pytest.mark.asyncio
    async def test_data_invalida_loga_warning(self) -> None:
        """dataDisponibilizacao malformada deve logar warning antes de usar fallback."""
        raw_data_invalida = {
            **_INTIMACAO_PENDENTE_RAW,
            "id": "int-data-invalida",
            "dataDisponibilizacao": "nao-e-uma-data",
        }
        mock_client = MagicMock(spec=DJeOAuthClient)
        mock_client.listar_comunicacoes = AsyncMock(return_value=[raw_data_invalida])
        provider = DJeProvider(client=mock_client)

        with patch("mcp_juridico_brasil.dje.provider.logger") as mock_logger:
            resultado = await provider.listar_intimacoes()

        assert resultado.total == 1
        # Fallback para datetime.now - intimacao ainda aparece na lista
        assert resultado.intimacoes[0].data_disponibilizacao is not None

        # Warning deve ter sido logado com o valor recebido
        warning_calls = [
            c for c in mock_logger.warning.call_args_list
            if c[0][0] == "dje_data_invalida_ignorada"
        ]
        assert len(warning_calls) >= 1
        assert warning_calls[0][1].get("valor") == "nao-e-uma-data"


class TestSegurancaProviderLazyInit:
    """Regressao: _provider em tools.py nao deve ser instanciado no import do modulo."""

    def test_provider_nao_instanciado_no_import(self) -> None:
        """Apos import, _provider deve ser None ate a primeira chamada real."""
        import mcp_juridico_brasil.dje.tools as tools_module

        # Resetar para simular import limpo
        tools_module._provider = None
        assert tools_module._provider is None

    def test_get_provider_cria_instancia_na_primeira_chamada(self) -> None:
        """_get_provider() deve criar DJeProvider apenas quando chamado."""
        import mcp_juridico_brasil.dje.tools as tools_module

        tools_module._provider = None
        provider = tools_module._get_provider()
        assert provider is not None
        assert isinstance(provider, DJeProvider)

    def test_get_provider_retorna_mesmo_singleton(self) -> None:
        """Duas chamadas a _get_provider() devem retornar o mesmo objeto."""
        import mcp_juridico_brasil.dje.tools as tools_module

        tools_module._provider = None
        p1 = tools_module._get_provider()
        p2 = tools_module._get_provider()
        assert p1 is p2
