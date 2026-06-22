"""Seletor de provider por configuracao de ambiente.

Variaveis relevantes:
- JURIDICO_PROVIDER: datajud | judit | escavador | trackjud  (default: datajud)
- JURIDICO_PROVIDER_API_KEY: chave do provider comercial (obrigatoria se != datajud)

Logica de selecao:
1. Le JURIDICO_PROVIDER (case-insensitive).
2. Se for "datajud" ou vazio, instancia DataJudProvider diretamente.
3. Se for um provider comercial, instancia o provider correspondente com a chave
   lida de JURIDICO_PROVIDER_API_KEY.
4. Se a chave estiver ausente ou o provider comercial falhar ao ser instanciado,
   o caller pode usar FallbackProvider para degradacao transparente para DataJud.

O FallbackProvider e o mecanismo de degradacao automatica descrito na Fase 3.
Ele envolve um provider comercial e, em caso de qualquer excecao (timeout, auth,
erro de API), chama o DataJudProvider silenciosamente com log de aviso.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from mcp_juridico_brasil._core.errors import JuridicoAPIError, JuridicoSigiloError
from mcp_juridico_brasil._core.logging import get_logger
from mcp_juridico_brasil.datajud.provider import DataJudProvider, ProcessoProvider
from mcp_juridico_brasil.shared.schemas import Movimentacao, Processo

logger = get_logger(__name__)

# Nomes aceitos de providers
_PROVIDERS_COMERCIAIS = {"judit", "escavador", "trackjud"}


def selecionar_provider() -> ProcessoProvider:
    """Retorna o provider ativo com base na configuracao de ambiente.

    Leitura de JURIDICO_PROVIDER e JURIDICO_PROVIDER_API_KEY feita em
    tempo de chamada (permite trocar sem reiniciar em testes).

    Returns:
        ProcessoProvider: instancia pronta para uso, com fallback embutido
        se o provider selecionado for comercial.

    Raises:
        ValueError: se JURIDICO_PROVIDER tiver valor desconhecido.
    """
    nome = os.environ.get("JURIDICO_PROVIDER", "datajud").strip().lower()

    if nome in ("datajud", ""):
        logger.info("provider_selecionado", provider="datajud")
        return DataJudProvider()

    if nome not in _PROVIDERS_COMERCIAIS:
        raise ValueError(
            f"Provider desconhecido: {nome!r}. "
            f"Valores aceitos: datajud, {', '.join(sorted(_PROVIDERS_COMERCIAIS))}."
        )

    api_key = os.environ.get("JURIDICO_PROVIDER_API_KEY", "").strip()
    comercial = _instanciar_comercial(nome, api_key)

    if comercial is None:
        logger.warning(
            "provider_comercial_indisponivel_usando_datajud",
            provider_solicitado=nome,
            motivo="Chave ausente ou provider nao instanciado",
        )
        return DataJudProvider()

    logger.info("provider_selecionado", provider=nome, com_fallback=True)
    return FallbackProvider(comercial, DataJudProvider())


def _instanciar_comercial(nome: str, api_key: str) -> ProcessoProvider | None:
    """Tenta instanciar o provider comercial.

    Retorna None se a chave estiver ausente (em vez de lancar excecao),
    para que o seletor possa degradar para DataJud automaticamente.
    """
    # Importacao local para evitar ciclo e manter modulo registry leve
    from mcp_juridico_brasil.comercial.providers import (
        EscavadorProvider,
        JuditProvider,
        TrackJudProvider,
    )

    if not api_key:
        return None

    _mapa: dict[str, Callable[[], ProcessoProvider]] = {
        "judit": lambda: JuditProvider(api_key=api_key),
        "escavador": lambda: EscavadorProvider(api_key=api_key),
        "trackjud": lambda: TrackJudProvider(api_key=api_key),
    }
    fabrica = _mapa.get(nome)
    # O seletor ja validou 'nome' contra _PROVIDERS_COMERCIAIS antes de chamar esta funcao.
    # Se fabrica for None aqui, ha inconsistencia interna entre os dois dicts.
    assert fabrica is not None, (
        f"Provider {nome!r} esta em _PROVIDERS_COMERCIAIS mas ausente do _mapa interno. "
        "Adicione a fabrica correspondente."
    )
    try:
        return fabrica()
    except JuridicoAPIError:
        # Caso esperado: chave ausente ou invalida. O seletor degrada para DataJud.
        logger.warning("provider_comercial_chave_invalida", provider=nome)
        return None
    except Exception as exc:
        # Bug inesperado na instanciacao - logar com traceback completo para diagnostico.
        logger.exception(
            "provider_comercial_instancia_erro_inesperado",
            provider=nome,
            tipo_erro=type(exc).__name__,
        )
        return None


# ---------------------------------------------------------------------------
# FallbackProvider
# ---------------------------------------------------------------------------


class FallbackProvider(ProcessoProvider):
    """Envolve um provider primario e degrada para o secundario em caso de falha.

    O fallback e transparente para as tools MCP: elas nao sabem qual provider
    respondeu. Um log de aviso e emitido quando o fallback e ativado.

    ATENCAO: JuridicoSigiloError do provider primario NUNCA e silenciado.
    Sigilo e definitivo e nao deve ser contornado tentando outro provider.
    """

    def __init__(self, primario: ProcessoProvider, secundario: ProcessoProvider) -> None:
        self._primario = primario
        self._secundario = secundario

    async def buscar_processo(self, numero_processo: str, tribunal: str | None = None) -> Processo:
        """Busca com fallback automatico."""
        try:
            return await self._primario.buscar_processo(numero_processo, tribunal)
        except JuridicoSigiloError:
            # Sigilo nao tem fallback - propaga imediatamente
            raise
        except Exception as exc:
            logger.warning(
                "provider_primario_falhou_usando_fallback",
                numero=numero_processo,
                erro=type(exc).__name__,
                detalhe=str(exc)[:200],
            )
            return await self._secundario.buscar_processo(numero_processo, tribunal)

    async def listar_movimentacoes(
        self, numero_processo: str, tribunal: str, limite: int = 20
    ) -> list[Movimentacao]:
        """Lista movimentacoes com fallback automatico."""
        try:
            return await self._primario.listar_movimentacoes(numero_processo, tribunal, limite)
        except JuridicoSigiloError:
            raise
        except Exception as exc:
            logger.warning(
                "provider_primario_falhou_usando_fallback",
                numero=numero_processo,
                erro=type(exc).__name__,
                detalhe=str(exc)[:200],
            )
            return await self._secundario.listar_movimentacoes(numero_processo, tribunal, limite)

    async def verificar_atualizacao(
        self, numero_processo: str, tribunal: str, desde_iso: str
    ) -> bool:
        """Verifica atualizacao com fallback automatico."""
        try:
            return await self._primario.verificar_atualizacao(numero_processo, tribunal, desde_iso)
        except JuridicoSigiloError:
            raise
        except Exception as exc:
            logger.warning(
                "provider_primario_falhou_usando_fallback",
                numero=numero_processo,
                erro=type(exc).__name__,
                detalhe=str(exc)[:200],
            )
            return await self._secundario.verificar_atualizacao(
                numero_processo, tribunal, desde_iso
            )


__all__ = ["FallbackProvider", "selecionar_provider"]
