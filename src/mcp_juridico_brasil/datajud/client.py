"""Cliente DataJud CNJ.

Consome a API pública Elasticsearch do DataJud (Portaria CNJ 160/2020).
Chave de acesso pública - sem cadastro. Rotacionar se o CNJ revogar.

NOTA DE SEGURANÇA: Esta implementação verifica nivel_sigilo antes de retornar
qualquer dado. Processos sigilosos lançam JuridicoSigiloError e NÃO são
armazenados em cache nem em logs detalhados.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from mcp_juridico_brasil._core import (
    HTTPClient,
    JuridicoAPIError,
    JuridicoNotFoundError,
    JuridicoSigiloError,
    get_logger,
)
from mcp_juridico_brasil._core import (
    settings as _settings,
)
from mcp_juridico_brasil.shared.schemas import Assunto, Movimentacao, OrgaoJulgador, Parte, Processo

from .tribunais import indice_para_url, listar_tribunais

logger = get_logger(__name__)


class DataJudClient:
    """Acesso à API pública DataJud com verificação de sigilo integrada."""

    def _http(self, tribunal: str) -> HTTPClient:
        url = indice_para_url(tribunal, _settings.datajud_base_url)
        if not url:
            raise JuridicoAPIError(
                source="DataJud",
                reason=f"Tribunal '{tribunal}' não suportado. "
                f"Consulte listar_tribunais() para opções válidas.",
            )
        return HTTPClient(
            base_url=url,
            headers={"Authorization": f"APIKey {_settings.datajud_api_key}"},
            timeout=_settings.juridico_http_timeout,
            max_retries=_settings.juridico_max_retries,
            cache_ttl=_settings.juridico_cache_ttl,
            rate_limit_per_second=_settings.juridico_rate_limit,
        )

    async def buscar_por_numero(self, numero_processo: str, tribunal: str) -> Processo:
        """Busca um processo pelo número CNJ em um tribunal específico.

        Raises:
            JuridicoSigiloError: Se nivel_sigilo > 0.
            JuridicoNotFoundError: Se o processo não existir no índice.
            JuridicoAPIError: Em falhas de comunicação.
        """
        query = {"query": {"match": {"numeroProcesso": numero_processo}}, "size": 1}
        async with self._http(tribunal) as client:
            data = await client.post("", json=query)

        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            raise JuridicoNotFoundError(numero_processo, tribunal)

        return self._parse_processo(hits[0].get("_source", {}), numero_processo)

    async def buscar_por_numero_multiplos_tribunais(
        self,
        numero_processo: str,
        tribunais: list[str] | None = None,
    ) -> Processo:
        """Tenta localizar o processo em múltiplos tribunais.

        Útil quando o tribunal não é conhecido de antemão.
        Itera pelos tribunais informados (ou por todos os suportados) até
        encontrar o processo.
        """
        targets = tribunais or listar_tribunais()
        last_error: Exception | None = None
        for tribunal in targets:
            try:
                return await self.buscar_por_numero(numero_processo, tribunal)
            except JuridicoSigiloError:
                raise  # Sigilo nao deve ser ignorado
            except (JuridicoNotFoundError, JuridicoAPIError) as exc:
                last_error = exc
                continue
        raise last_error or JuridicoNotFoundError(numero_processo)

    async def listar_movimentacoes(
        self, numero_processo: str, tribunal: str, limite: int = 20
    ) -> list[Movimentacao]:
        """Retorna as movimentacoes mais recentes de um processo."""
        processo = await self.buscar_por_numero(numero_processo, tribunal)
        return processo.movimentacoes[:limite]

    # ------------------------------------------------------------------
    # Parsing interno
    # ------------------------------------------------------------------

    def _parse_processo(self, src: dict[str, Any], numero_fallback: str) -> Processo:
        nivel_sigilo = int(src.get("nivelSigilo", 0))
        numero = src.get("numeroProcesso", numero_fallback)

        if nivel_sigilo > 0:
            logger.warning("processo_sigiloso_bloqueado", nivel=nivel_sigilo)
            raise JuridicoSigiloError(numero, nivel_sigilo)

        classe = src.get("classe", {})
        orgao = src.get("orgaoJulgador", {})
        assuntos_raw = src.get("assuntos", [])
        partes_raw = src.get("partes", [])
        movs_raw = src.get("movimentos", [])

        def parse_dt(value: str | None) -> datetime | None:
            if not value:
                return None
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None

        return Processo(
            numero_processo=numero,
            tribunal=src.get("tribunal", ""),
            grau=src.get("grau"),
            data_ajuizamento=parse_dt(src.get("dataAjuizamento")),
            data_ultima_atualizacao=parse_dt(src.get("dataHoraUltimaAtualizacao")),
            nivel_sigilo=nivel_sigilo,
            classe_codigo=classe.get("codigo"),
            classe_nome=classe.get("nome"),
            assuntos=[
                Assunto(
                    codigo=a.get("codigo", 0),
                    nome=a.get("nome", ""),
                    principal=a.get("principal", False),
                )
                for a in assuntos_raw
            ],
            orgao_julgador=OrgaoJulgador(
                codigo=orgao.get("codigo"),
                nome=orgao.get("nome", ""),
                codigo_municipio_ibge=orgao.get("codigoMunicipioIBGE"),
            )
            if orgao
            else None,
            partes=[
                Parte(
                    nome=p.get("nome", ""),
                    tipo=p.get("tipo", {}).get("nome", ""),
                    polo=p.get("polo"),
                )
                for p in partes_raw
            ],
            movimentacoes=[
                Movimentacao(
                    codigo=m.get("codigo"),
                    nome=m.get("nome", ""),
                    data_hora=parse_dt(m.get("dataHora"))
                    or datetime.min.replace(tzinfo=timezone.utc),
                    complementos=m.get("complementosTabelados", []),
                )
                for m in sorted(movs_raw, key=lambda x: x.get("dataHora", ""), reverse=True)
            ],
            formato=src.get("formato", {}).get("nome") if src.get("formato") else None,
            sistema=src.get("sistema", {}).get("nome") if src.get("sistema") else None,
        )


__all__ = ["DataJudClient"]
