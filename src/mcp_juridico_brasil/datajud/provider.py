"""Interface abstrata ProcessoProvider e implementacao DataJudProvider.

O design de provider abstrato permite trocar a fonte de dados sem alterar
as tools MCP. Em producao, um provider comercial (Judit, Escavador) pode
substituir o DataJud para tribunais com maior defasagem ou para consultas
por CPF/CNPJ.

Fase 1 usa exclusivamente DataJudProvider.
Fase 3 adiciona ComercialProvider que delega ao configurado em JURIDICO_PROVIDER_COMERCIAL.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from mcp_juridico_brasil._core.errors import JuridicoValidationError
from mcp_juridico_brasil.shared.schemas import Movimentacao, Processo

from .client import DataJudClient


class ProcessoProvider(ABC):
    """Interface que toda fonte de dados processual deve implementar."""

    @abstractmethod
    async def buscar_processo(self, numero_processo: str, tribunal: str | None = None) -> Processo:
        """Retorna os dados completos de um processo."""
        ...

    @abstractmethod
    async def listar_movimentacoes(
        self, numero_processo: str, tribunal: str, limite: int = 20
    ) -> list[Movimentacao]:
        """Retorna as movimentacoes mais recentes."""
        ...

    async def verificar_atualizacao(
        self, numero_processo: str, tribunal: str, desde_iso: str
    ) -> bool:
        """Retorna True se o processo teve atualizacao apos a data informada.

        Implementacao padrao: delega para buscar_processo e compara datas.
        Providers com endpoint dedicado de check-update podem sobrescrever.

        Args:
            numero_processo: Numero CNJ do processo.
            tribunal: Sigla do tribunal.
            desde_iso: Data de corte em formato ISO 8601 (ex: '2024-06-01T00:00:00Z').

        Raises:
            JuridicoValidationError: Se desde_iso nao for uma data ISO 8601 valida.
        """
        try:
            desde = datetime.fromisoformat(desde_iso)
        except ValueError as exc:
            raise JuridicoValidationError(
                "desde_iso",
                desde_iso,
                "Formato ISO 8601 esperado (ex: '2024-06-01T00:00:00Z').",
            ) from exc
        if desde.tzinfo is None:
            desde = desde.replace(tzinfo=timezone.utc)

        processo = await self.buscar_processo(numero_processo, tribunal)
        if not processo.data_ultima_atualizacao:
            return False
        return processo.data_ultima_atualizacao > desde


class DataJudProvider(ProcessoProvider):
    """Provider concreto baseado na API publica DataJud (CNJ).

    Cobertura: 91 tribunais. Zero custo. Sem webhook (polling).
    Defasagem: T+1 a T+7 dias dependendo do tribunal.
    """

    def __init__(self) -> None:
        self._client = DataJudClient()

    async def buscar_processo(self, numero_processo: str, tribunal: str | None = None) -> Processo:
        if tribunal:
            return await self._client.buscar_por_numero(numero_processo, tribunal)
        return await self._client.buscar_por_numero_multiplos_tribunais(numero_processo)

    async def listar_movimentacoes(
        self, numero_processo: str, tribunal: str, limite: int = 20
    ) -> list[Movimentacao]:
        return await self._client.listar_movimentacoes(numero_processo, tribunal, limite)


__all__ = ["DataJudProvider", "ProcessoProvider"]
