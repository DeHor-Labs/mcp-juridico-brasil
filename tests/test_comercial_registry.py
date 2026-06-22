"""Testes do seletor de provider por configuracao de ambiente e do FallbackProvider.

Cenarios cobertos:
- JURIDICO_PROVIDER ausente ou "datajud" -> DataJudProvider
- JURIDICO_PROVIDER=judit com chave -> FallbackProvider(Judit, DataJud)
- JURIDICO_PROVIDER=escavador com chave -> FallbackProvider(Escavador, DataJud)
- JURIDICO_PROVIDER=trackjud com chave -> FallbackProvider(TrackJud, DataJud)
- JURIDICO_PROVIDER=judit sem chave -> DataJudProvider (fallback silencioso)
- JURIDICO_PROVIDER=desconhecido -> ValueError
- FallbackProvider: provider primario falha -> secundario responde
- FallbackProvider: JuridicoSigiloError do primario propagada sem fallback
- Regressao HIGH-1: JuridicoAPIError na instanciacao degrada para DataJud (esperado)
- Regressao HIGH-1: Exception generica na instanciacao tambem degrada (com log.exception)
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_juridico_brasil._core.errors import JuridicoAPIError, JuridicoSigiloError
from mcp_juridico_brasil.comercial.registry import FallbackProvider, selecionar_provider
from mcp_juridico_brasil.datajud.provider import DataJudProvider
from mcp_juridico_brasil.shared.schemas import Movimentacao, Processo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NUMERO = "00012345620238260100"
TRIBUNAL = "TJSP"


def _processo_fake(numero: str = NUMERO) -> Processo:
    """Retorna um Processo minimo para uso nos testes."""
    return Processo(
        numero_processo=numero,
        tribunal=TRIBUNAL,
        nivel_sigilo=0,
        data_ultima_atualizacao=datetime(2024, 6, 1, tzinfo=timezone.utc),
    )


def _movimentacao_fake() -> Movimentacao:
    return Movimentacao(
        codigo=22,
        nome="Despacho",
        data_hora=datetime(2024, 6, 1, tzinfo=timezone.utc),
    )


def _mock_provider(
    processo: Processo | None = None,
    movimentacoes: list[Movimentacao] | None = None,
    verificar_resultado: bool = False,
    raise_exc: Exception | None = None,
) -> MagicMock:
    """Cria um provider mock com comportamentos configurados."""
    provider = MagicMock()
    if raise_exc:
        provider.buscar_processo = AsyncMock(side_effect=raise_exc)
        provider.listar_movimentacoes = AsyncMock(side_effect=raise_exc)
        provider.verificar_atualizacao = AsyncMock(side_effect=raise_exc)
    else:
        provider.buscar_processo = AsyncMock(return_value=processo or _processo_fake())
        provider.listar_movimentacoes = AsyncMock(
            return_value=movimentacoes or [_movimentacao_fake()]
        )
        provider.verificar_atualizacao = AsyncMock(return_value=verificar_resultado)
    return provider


# ===========================================================================
# Testes do seletor selecionar_provider
# ===========================================================================


class TestSelecionarProvider:
    """Testes unitarios do seletor por variavel de ambiente."""

    def test_sem_env_retorna_datajud(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Sem JURIDICO_PROVIDER, deve retornar DataJudProvider."""
        monkeypatch.delenv("JURIDICO_PROVIDER", raising=False)
        provider = selecionar_provider()
        assert isinstance(provider, DataJudProvider)

    def test_datajud_explicito_retorna_datajud(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """JURIDICO_PROVIDER=datajud deve retornar DataJudProvider."""
        monkeypatch.setenv("JURIDICO_PROVIDER", "datajud")
        provider = selecionar_provider()
        assert isinstance(provider, DataJudProvider)

    def test_datajud_uppercase_retorna_datajud(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Valor em uppercase deve ser aceito (case-insensitive)."""
        monkeypatch.setenv("JURIDICO_PROVIDER", "DATAJUD")
        provider = selecionar_provider()
        assert isinstance(provider, DataJudProvider)

    def test_judit_com_chave_retorna_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """JURIDICO_PROVIDER=judit com chave deve retornar FallbackProvider."""
        monkeypatch.setenv("JURIDICO_PROVIDER", "judit")
        monkeypatch.setenv("JURIDICO_PROVIDER_API_KEY", "chave-fake")
        provider = selecionar_provider()
        assert isinstance(provider, FallbackProvider)

    def test_escavador_com_chave_retorna_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """JURIDICO_PROVIDER=escavador com chave deve retornar FallbackProvider."""
        monkeypatch.setenv("JURIDICO_PROVIDER", "escavador")
        monkeypatch.setenv("JURIDICO_PROVIDER_API_KEY", "chave-fake")
        provider = selecionar_provider()
        assert isinstance(provider, FallbackProvider)

    def test_trackjud_com_chave_retorna_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """JURIDICO_PROVIDER=trackjud com chave deve retornar FallbackProvider."""
        monkeypatch.setenv("JURIDICO_PROVIDER", "trackjud")
        monkeypatch.setenv("JURIDICO_PROVIDER_API_KEY", "chave-fake")
        provider = selecionar_provider()
        assert isinstance(provider, FallbackProvider)

    def test_judit_sem_chave_degrada_para_datajud(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """JURIDICO_PROVIDER=judit sem chave deve degradar para DataJudProvider."""
        monkeypatch.setenv("JURIDICO_PROVIDER", "judit")
        monkeypatch.delenv("JURIDICO_PROVIDER_API_KEY", raising=False)
        provider = selecionar_provider()
        # Sem chave, deve usar DataJud silenciosamente
        assert isinstance(provider, DataJudProvider)

    def test_provider_desconhecido_lanca_value_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """JURIDICO_PROVIDER com valor invalido deve lancar ValueError."""
        monkeypatch.setenv("JURIDICO_PROVIDER", "desconhecido")
        with pytest.raises(ValueError, match="desconhecido"):
            selecionar_provider()

    def test_env_com_espacos_e_tratado(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Espacos ao redor do valor devem ser ignorados."""
        monkeypatch.setenv("JURIDICO_PROVIDER", "  datajud  ")
        provider = selecionar_provider()
        assert isinstance(provider, DataJudProvider)

    def test_juridico_api_error_na_instanciacao_degrada_para_datajud(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regressao HIGH-1: JuridicoAPIError durante instanciacao do provider comercial
        deve degradar silenciosamente para DataJudProvider (caso esperado - chave invalida)."""
        monkeypatch.setenv("JURIDICO_PROVIDER", "judit")
        monkeypatch.setenv("JURIDICO_PROVIDER_API_KEY", "chave-invalida")
        with patch(
            "mcp_juridico_brasil.comercial.providers.JuditProvider.__init__",
            side_effect=JuridicoAPIError("Judit", reason="Credencial invalida"),
        ):
            provider = selecionar_provider()

        # Deve degradar para DataJud, nao lancar excecao
        assert isinstance(provider, DataJudProvider)

    def test_exception_generica_na_instanciacao_degrada_para_datajud(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regressao HIGH-1: Exception inesperada durante instanciacao do provider comercial
        deve tambem degradar para DataJudProvider (sem silenciar o bug - usa logger.exception)."""
        monkeypatch.setenv("JURIDICO_PROVIDER", "judit")
        monkeypatch.setenv("JURIDICO_PROVIDER_API_KEY", "chave-qualquer")
        with patch(
            "mcp_juridico_brasil.comercial.providers.JuditProvider.__init__",
            side_effect=RuntimeError("bug inesperado"),
        ):
            provider = selecionar_provider()

        # Deve degradar para DataJud mesmo em caso de bug
        assert isinstance(provider, DataJudProvider)


# ===========================================================================
# Testes do FallbackProvider
# ===========================================================================


class TestFallbackProvider:
    """Testes do mecanismo de fallback automatico."""

    @pytest.mark.asyncio
    async def test_primario_ok_nao_usa_secundario(self) -> None:
        """Quando primario responde, secundario nao e chamado."""
        primario = _mock_provider(processo=_processo_fake())
        secundario = _mock_provider()
        fp = FallbackProvider(primario, secundario)

        resultado = await fp.buscar_processo(NUMERO, TRIBUNAL)

        assert resultado.numero_processo == NUMERO
        primario.buscar_processo.assert_called_once()
        secundario.buscar_processo.assert_not_called()

    @pytest.mark.asyncio
    async def test_primario_falha_usa_secundario(self) -> None:
        """Quando primario lanca JuridicoAPIError, secundario responde."""
        primario = _mock_provider(raise_exc=JuridicoAPIError("Judit", 503))
        secundario = _mock_provider(processo=_processo_fake())
        fp = FallbackProvider(primario, secundario)

        resultado = await fp.buscar_processo(NUMERO, TRIBUNAL)

        assert resultado.numero_processo == NUMERO
        secundario.buscar_processo.assert_called_once()

    @pytest.mark.asyncio
    async def test_primario_timeout_usa_secundario(self) -> None:
        """Timeout no primario ativa o secundario."""
        from httpx import TimeoutException

        primario = _mock_provider(raise_exc=TimeoutException("timeout"))
        secundario = _mock_provider(processo=_processo_fake())
        fp = FallbackProvider(primario, secundario)

        resultado = await fp.buscar_processo(NUMERO, TRIBUNAL)
        assert resultado.numero_processo == NUMERO

    @pytest.mark.asyncio
    async def test_sigilo_primario_propagado_sem_fallback(self) -> None:
        """JuridicoSigiloError do primario NUNCA e silenciada pelo fallback."""
        primario = _mock_provider(raise_exc=JuridicoSigiloError(NUMERO, nivel_sigilo=1))
        secundario = _mock_provider(processo=_processo_fake())
        fp = FallbackProvider(primario, secundario)

        with pytest.raises(JuridicoSigiloError):
            await fp.buscar_processo(NUMERO, TRIBUNAL)

        # Secundario NUNCA deve ser chamado quando sigilo e detectado
        secundario.buscar_processo.assert_not_called()

    @pytest.mark.asyncio
    async def test_listar_movimentacoes_primario_ok(self) -> None:
        """listar_movimentacoes usa primario quando disponivel."""
        movs = [_movimentacao_fake()]
        primario = _mock_provider(movimentacoes=movs)
        secundario = _mock_provider()
        fp = FallbackProvider(primario, secundario)

        resultado = await fp.listar_movimentacoes(NUMERO, TRIBUNAL)
        assert len(resultado) == 1
        secundario.listar_movimentacoes.assert_not_called()

    @pytest.mark.asyncio
    async def test_listar_movimentacoes_fallback_ativo(self) -> None:
        """listar_movimentacoes ativa fallback quando primario falha."""
        movs = [_movimentacao_fake()]
        primario = _mock_provider(raise_exc=JuridicoAPIError("Judit", 500))
        secundario = _mock_provider(movimentacoes=movs)
        fp = FallbackProvider(primario, secundario)

        resultado = await fp.listar_movimentacoes(NUMERO, TRIBUNAL)
        assert len(resultado) == 1
        secundario.listar_movimentacoes.assert_called_once()

    @pytest.mark.asyncio
    async def test_listar_movimentacoes_sigilo_propagado(self) -> None:
        """JuridicoSigiloError em listar_movimentacoes nao tem fallback."""
        primario = _mock_provider(raise_exc=JuridicoSigiloError(NUMERO, nivel_sigilo=2))
        secundario = _mock_provider()
        fp = FallbackProvider(primario, secundario)

        with pytest.raises(JuridicoSigiloError):
            await fp.listar_movimentacoes(NUMERO, TRIBUNAL)

        secundario.listar_movimentacoes.assert_not_called()

    @pytest.mark.asyncio
    async def test_verificar_atualizacao_primario_ok(self) -> None:
        """verificar_atualizacao usa primario quando disponivel."""
        primario = _mock_provider(verificar_resultado=True)
        secundario = _mock_provider(verificar_resultado=False)
        fp = FallbackProvider(primario, secundario)

        resultado = await fp.verificar_atualizacao(NUMERO, TRIBUNAL, "2024-01-01T00:00:00Z")
        assert resultado is True
        secundario.verificar_atualizacao.assert_not_called()

    @pytest.mark.asyncio
    async def test_verificar_atualizacao_fallback_ativo(self) -> None:
        """verificar_atualizacao ativa fallback quando primario falha."""
        primario = _mock_provider(raise_exc=JuridicoAPIError("Judit", 503))
        secundario = _mock_provider(verificar_resultado=True)
        fp = FallbackProvider(primario, secundario)

        resultado = await fp.verificar_atualizacao(NUMERO, TRIBUNAL, "2024-01-01T00:00:00Z")
        assert resultado is True

    @pytest.mark.asyncio
    async def test_verificar_atualizacao_sigilo_propagado(self) -> None:
        """JuridicoSigiloError em verificar_atualizacao nao tem fallback."""
        primario = _mock_provider(raise_exc=JuridicoSigiloError(NUMERO, nivel_sigilo=1))
        secundario = _mock_provider(verificar_resultado=True)
        fp = FallbackProvider(primario, secundario)

        with pytest.raises(JuridicoSigiloError):
            await fp.verificar_atualizacao(NUMERO, TRIBUNAL, "2024-01-01T00:00:00Z")

        secundario.verificar_atualizacao.assert_not_called()
