"""Providers comerciais mock-ready para o MCP Juridico Brasil.

Cada provider implementa ProcessoProvider usando a documentacao publica
da API correspondente. A autenticacao e feita exclusivamente via variavel
de ambiente JURIDICO_PROVIDER_API_KEY - nunca hardcoded.

ATENCAO SEGURANCA: As URLs base e paths de cada provider sao constantes
fixadas no codigo. A construcao de URL nao interpola dados externos para
evitar SSRF (Server-Side Request Forgery). Parametros de busca vao sempre
como query params ou corpo JSON, jamais interpolados na URL base.

NOTA DE INTEGRACAO: Cada provider tem marcacao explicita dos pontos que
exigem validacao com credencial real antes de ir para producao. A estrutura
de request/response segue a documentacao publica disponivel em junho de 2026.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx

from mcp_juridico_brasil._core.errors import (
    JuridicoAPIError,
    JuridicoNotFoundError,
    JuridicoSigiloError,
)
from mcp_juridico_brasil._core.logging import get_logger
from mcp_juridico_brasil.datajud.provider import ProcessoProvider
from mcp_juridico_brasil.shared.schemas import Assunto, Movimentacao, OrgaoJulgador, Parte, Processo

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constantes de URL (fixas - sem interpolacao de dados externos)
# ---------------------------------------------------------------------------

_JUDIT_BASE_URL = "https://api.judit.io"
_ESCAVADOR_BASE_URL = "https://api.escavador.com"
_TRACKJUD_BASE_URL = "https://api.trackjud.com.br"

# Tempo maximo de espera por resposta dos providers (segundos)
_TIMEOUT_COMERCIAL = 30.0


# ---------------------------------------------------------------------------
# Helpers de autenticacao
# ---------------------------------------------------------------------------


def _exigir_api_key(provider_nome: str) -> str:
    """Retorna JURIDICO_PROVIDER_API_KEY ou lanca erro informativo.

    SEGURANCA: Chaves de API nunca tem valor default. O erro orienta o
    operador a configurar a variavel de ambiente correta.
    """
    api_key = os.environ.get("JURIDICO_PROVIDER_API_KEY", "").strip()
    if not api_key:
        raise JuridicoAPIError(
            source=provider_nome,
            reason=(
                "Chave de API ausente. Configure JURIDICO_PROVIDER_API_KEY "
                f"com sua chave do {provider_nome}."
            ),
        )
    return api_key


# ---------------------------------------------------------------------------
# Parser generico de resposta
# ---------------------------------------------------------------------------


def _iso_ou_none(valor: str | None) -> datetime | None:
    """Converte string ISO 8601 para datetime com fuso UTC ou retorna None."""
    if not valor:
        return None
    try:
        dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# JuditProvider
# ---------------------------------------------------------------------------


class JuditProvider(ProcessoProvider):
    """Provider baseado na API judit.io.

    INTEGRACAO PENDENTE DE VALIDACAO COM CREDENCIAL REAL.
    Esta implementacao segue a documentacao publica do judit.io (junho de 2026).
    Antes de usar em producao, validar:
    - Formato exato do header de autenticacao (Bearer vs Api-Key)
    - Schema da resposta de buscar_processo (campos podem diferir)
    - Endpoint de listar movimentacoes (pode ser separado ou embutido no processo)
    - Rate limits e politica de retry da API Judit

    Referencia: https://judit.io/planos/ e documentacao privada do plano contratado.

    Autenticacao:
        Header: Authorization: Bearer <JURIDICO_PROVIDER_API_KEY>

    Cobertura declarada: 100% dos tribunais, +450 mi processos (2026).
    Webhook: suportado nos planos anuais com SLA contratual.
    """

    # Paths de endpoint (sem interpolacao de dados externos na URL base)
    _PATH_PROCESSO = "/v1/processos"
    _PATH_MOVIMENTACOES_SUFIXO = "/movimentacoes"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or _exigir_api_key("Judit")
        self._base_url = _JUDIT_BASE_URL

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def buscar_processo(self, numero_processo: str, tribunal: str | None = None) -> Processo:
        """Consulta processo na API Judit pelo numero CNJ.

        O numero e enviado como parametro de query, nunca interpolado na URL base.
        """
        params: dict[str, str] = {"numero": numero_processo}
        if tribunal:
            params["tribunal"] = tribunal

        url = self._base_url + self._PATH_PROCESSO
        logger.info("judit_buscar_processo", numero=numero_processo, tribunal=tribunal)

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_COMERCIAL) as client:
                response = await client.get(url, params=params, headers=self._headers())
        except httpx.TimeoutException as exc:
            raise JuridicoAPIError(source="Judit", reason="Timeout na consulta") from exc
        except httpx.RequestError as exc:
            raise JuridicoAPIError(source="Judit", reason=f"Erro de rede: {exc}") from exc

        if response.status_code == 401:
            raise JuridicoAPIError(
                source="Judit",
                status_code=401,
                reason="Credencial invalida. Verifique JURIDICO_PROVIDER_API_KEY.",
            )
        if response.status_code == 404:
            raise JuridicoNotFoundError(numero_processo, tribunal)
        if response.status_code != 200:
            raise JuridicoAPIError(
                source="Judit",
                status_code=response.status_code,
                reason=response.text[:200],
            )

        data: dict[str, Any] = response.json()
        return self._parse_processo(data, tribunal or "")

    async def listar_movimentacoes(
        self, numero_processo: str, tribunal: str, limite: int = 20
    ) -> list[Movimentacao]:
        """Lista movimentacoes de um processo via Judit."""
        url = self._base_url + self._PATH_PROCESSO + self._PATH_MOVIMENTACOES_SUFIXO
        params: dict[str, Any] = {"numero": numero_processo, "tribunal": tribunal, "limit": limite}

        logger.info("judit_listar_movimentacoes", numero=numero_processo)

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_COMERCIAL) as client:
                response = await client.get(url, params=params, headers=self._headers())
        except httpx.TimeoutException as exc:
            raise JuridicoAPIError(
                source="Judit", reason="Timeout ao listar movimentacoes"
            ) from exc
        except httpx.RequestError as exc:
            raise JuridicoAPIError(source="Judit", reason=f"Erro de rede: {exc}") from exc

        if response.status_code == 401:
            raise JuridicoAPIError(source="Judit", status_code=401, reason="Credencial invalida.")
        if response.status_code == 404:
            raise JuridicoNotFoundError(numero_processo, tribunal)
        if response.status_code != 200:
            raise JuridicoAPIError(source="Judit", status_code=response.status_code)

        data = response.json()
        items: list[dict[str, Any]] = data.get(
            "movimentacoes", data if isinstance(data, list) else []
        )
        return [self._parse_movimentacao(m) for m in items[:limite]]

    # ------------------------------------------------------------------
    # Parsers internos
    # ------------------------------------------------------------------

    def _parse_processo(self, data: dict[str, Any], tribunal_fallback: str) -> Processo:
        """Converte resposta Judit para o schema Processo interno.

        INTEGRACAO: Os nomes de campo abaixo seguem a documentacao publica do Judit.
        Podem precisar de ajuste apos validacao com credencial real.
        """
        nivel_sigilo = int(data.get("nivel_sigilo", data.get("nivelSigilo", 0)))
        numero = str(data.get("numero_processo", data.get("numero", "")))
        if nivel_sigilo > 0:
            raise JuridicoSigiloError(numero, nivel_sigilo)

        partes = [
            Parte(
                nome=str(p.get("nome", "")),
                tipo=str(p.get("tipo", "")),
                polo=p.get("polo"),
            )
            for p in data.get("partes", [])
        ]
        assuntos = [
            Assunto(
                codigo=int(a.get("codigo", 0)),
                nome=str(a.get("nome", "")),
                principal=bool(a.get("principal", False)),
            )
            for a in data.get("assuntos", [])
        ]
        orgao_raw: dict[str, Any] | None = data.get("orgao_julgador")
        orgao = (
            OrgaoJulgador(
                codigo=orgao_raw.get("codigo"),
                nome=str(orgao_raw.get("nome", "")),
                codigo_municipio_ibge=orgao_raw.get("codigo_municipio_ibge"),
            )
            if orgao_raw
            else None
        )
        movs = [self._parse_movimentacao(m) for m in data.get("movimentacoes", [])]

        return Processo(
            numero_processo=numero,
            tribunal=str(data.get("tribunal", tribunal_fallback)),
            grau=data.get("grau"),
            data_ajuizamento=_iso_ou_none(data.get("data_ajuizamento")),
            data_ultima_atualizacao=_iso_ou_none(
                data.get("data_ultima_atualizacao", data.get("data_atualizacao"))
            ),
            nivel_sigilo=nivel_sigilo,
            classe_codigo=data.get("classe_codigo"),
            classe_nome=data.get("classe_nome"),
            assuntos=assuntos,
            orgao_julgador=orgao,
            partes=partes,
            movimentacoes=movs,
            formato=data.get("formato"),
            sistema=data.get("sistema"),
        )

    def _parse_movimentacao(self, data: dict[str, Any]) -> Movimentacao:
        """Converte item de movimentacao Judit para schema interno."""
        data_raw = data.get("data_hora", data.get("dataHora", data.get("data", "")))
        dt = _iso_ou_none(str(data_raw))
        if dt is None:
            logger.warning(
                "movimentacao_sem_data_usando_now",
                provider="judit",
                codigo=data.get("codigo"),
            )
            dt = datetime.now(tz=timezone.utc)
        return Movimentacao(
            codigo=data.get("codigo"),
            nome=str(data.get("nome", data.get("descricao", ""))),
            data_hora=dt,
            complementos=data.get("complementos", []),
        )


# ---------------------------------------------------------------------------
# EscavadorProvider
# ---------------------------------------------------------------------------


class EscavadorProvider(ProcessoProvider):
    """Provider baseado na API escavador.com/business/api.

    INTEGRACAO PENDENTE DE VALIDACAO COM CREDENCIAL REAL.
    Esta implementacao segue a documentacao publica do Escavador (junho de 2026).
    Antes de usar em producao, validar:
    - Fluxo de autenticacao OAuth2 (client_credentials) para a API Business
    - Formato e campos do endpoint de busca por numero CNJ
    - Paginacao e estrutura de movimentacoes
    - Limites de credito e comportamento ao esgotar cota

    O Escavador disponibiliza SDK Python oficial no GitHub. Esta implementacao
    usa httpx diretamente para manter a dependencia minima do projeto.

    Referencia: https://www.escavador.com/business/api

    Autenticacao:
        Header: Authorization: Bearer <JURIDICO_PROVIDER_API_KEY>
        (token obtido via OAuth2 client_credentials - a presente implementacao
        usa o token diretamente; em producao, implementar refresh automatico)
    """

    _PATH_PROCESSO = "/api/v1/processos"
    _PATH_MOVIMENTACOES_SUFIXO = "/movimentacoes"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or _exigir_api_key("Escavador")
        self._base_url = _ESCAVADOR_BASE_URL

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }

    async def buscar_processo(self, numero_processo: str, tribunal: str | None = None) -> Processo:
        """Busca processo por numero CNJ na API Escavador."""
        params: dict[str, str] = {"numero_processo": numero_processo}
        if tribunal:
            params["tribunal"] = tribunal

        url = self._base_url + self._PATH_PROCESSO
        logger.info("escavador_buscar_processo", numero=numero_processo)

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_COMERCIAL) as client:
                response = await client.get(url, params=params, headers=self._headers())
        except httpx.TimeoutException as exc:
            raise JuridicoAPIError(source="Escavador", reason="Timeout na consulta") from exc
        except httpx.RequestError as exc:
            raise JuridicoAPIError(source="Escavador", reason=f"Erro de rede: {exc}") from exc

        if response.status_code == 401:
            raise JuridicoAPIError(
                source="Escavador",
                status_code=401,
                reason="Credencial invalida. Verifique JURIDICO_PROVIDER_API_KEY.",
            )
        if response.status_code == 404:
            raise JuridicoNotFoundError(numero_processo, tribunal)
        if response.status_code != 200:
            raise JuridicoAPIError(
                source="Escavador",
                status_code=response.status_code,
                reason=response.text[:200],
            )

        data = response.json()
        # INTEGRACAO: O Escavador retorna lista em 'items' ou objeto direto
        item: dict[str, Any] = data.get("items", [data])[0] if isinstance(data, dict) else data
        return self._parse_processo(item, tribunal or "")

    async def listar_movimentacoes(
        self, numero_processo: str, tribunal: str, limite: int = 20
    ) -> list[Movimentacao]:
        """Lista movimentacoes via Escavador."""
        # INTEGRACAO: Endpoint pode variar - validar com credencial real
        url = self._base_url + self._PATH_PROCESSO + self._PATH_MOVIMENTACOES_SUFIXO
        params: dict[str, Any] = {
            "numero_processo": numero_processo,
            "tribunal": tribunal,
            "per_page": limite,
        }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_COMERCIAL) as client:
                response = await client.get(url, params=params, headers=self._headers())
        except httpx.TimeoutException as exc:
            raise JuridicoAPIError(
                source="Escavador", reason="Timeout ao listar movimentacoes"
            ) from exc
        except httpx.RequestError as exc:
            raise JuridicoAPIError(source="Escavador", reason=f"Erro de rede: {exc}") from exc

        if response.status_code == 401:
            raise JuridicoAPIError(
                source="Escavador", status_code=401, reason="Credencial invalida."
            )
        if response.status_code == 404:
            raise JuridicoNotFoundError(numero_processo, tribunal)
        if response.status_code != 200:
            raise JuridicoAPIError(source="Escavador", status_code=response.status_code)

        data = response.json()
        items: list[dict[str, Any]] = data.get("items", data if isinstance(data, list) else [])
        return [self._parse_movimentacao(m) for m in items[:limite]]

    def _parse_processo(self, data: dict[str, Any], tribunal_fallback: str) -> Processo:
        """Converte resposta Escavador para schema Processo interno.

        INTEGRACAO: Nomes de campo seguem documentacao publica do Escavador.
        Validar com credencial real antes de producao.
        """
        nivel_sigilo = int(data.get("nivel_sigilo", 0))
        numero = str(data.get("numero_processo", data.get("numero", "")))
        if nivel_sigilo > 0:
            raise JuridicoSigiloError(numero, nivel_sigilo)

        partes = [
            Parte(
                nome=str(p.get("nome", "")),
                tipo=str(p.get("tipo_participacao", p.get("tipo", ""))),
                polo=p.get("polo"),
            )
            for p in data.get("partes", [])
        ]
        # LGPD: Campo cpf/cnpj ignorado propositalmente mesmo se presente na resposta
        assuntos = [
            Assunto(
                codigo=int(a.get("codigo", 0)),
                nome=str(a.get("nome", "")),
                principal=bool(a.get("principal", False)),
            )
            for a in data.get("assuntos", [])
        ]
        orgao_raw: dict[str, Any] | None = data.get("orgao_julgador")
        orgao = (
            OrgaoJulgador(
                codigo=orgao_raw.get("codigo"),
                nome=str(orgao_raw.get("nome", "")),
            )
            if orgao_raw
            else None
        )

        return Processo(
            numero_processo=numero,
            tribunal=str(data.get("tribunal", tribunal_fallback)),
            grau=data.get("grau"),
            data_ajuizamento=_iso_ou_none(data.get("data_ajuizamento")),
            data_ultima_atualizacao=_iso_ou_none(data.get("data_ultima_atualizacao")),
            nivel_sigilo=nivel_sigilo,
            classe_codigo=data.get("classe", {}).get("codigo")
            if isinstance(data.get("classe"), dict)
            else None,
            classe_nome=data.get("classe", {}).get("nome")
            if isinstance(data.get("classe"), dict)
            else None,
            assuntos=assuntos,
            orgao_julgador=orgao,
            partes=partes,
            movimentacoes=[self._parse_movimentacao(m) for m in data.get("movimentacoes", [])],
            formato=data.get("formato"),
            sistema=data.get("sistema"),
        )

    def _parse_movimentacao(self, data: dict[str, Any]) -> Movimentacao:
        """Converte item de movimentacao Escavador para schema interno."""
        data_raw = data.get("data", data.get("data_hora", ""))
        dt = _iso_ou_none(str(data_raw))
        if dt is None:
            logger.warning(
                "movimentacao_sem_data_usando_now",
                provider="escavador",
                codigo=data.get("codigo_tpu"),
            )
            dt = datetime.now(tz=timezone.utc)
        return Movimentacao(
            codigo=data.get("codigo_tpu"),
            nome=str(data.get("tipo", data.get("nome", ""))),
            data_hora=dt,
            complementos=data.get("complementos", []),
        )


# ---------------------------------------------------------------------------
# TrackJudProvider
# ---------------------------------------------------------------------------


class TrackJudProvider(ProcessoProvider):
    """Provider baseado na API trackjud.com.br.

    INTEGRACAO PENDENTE DE VALIDACAO COM CREDENCIAL REAL.
    Esta implementacao segue a documentacao publica do TrackJud (junho de 2026),
    incluindo a especificacao OpenAPI 3.1 disponivel no site.
    Antes de usar em producao, validar:
    - Endpoints exatos (documentacao OpenAPI pode ter diferido desde junho/2026)
    - Formato de autenticacao (Bearer token ou Api-Key customizado)
    - Cobertura real de tribunais (declarado: 10 estados - SP, RJ, PE, AM, DF +)
    - Comportamento ao extrapolar cota (R$ 0,10/consulta/tribunal)

    LIMITACAO CONHECIDA: TrackJud cobre parcialmente os tribunais (10 estados
    declarados em junho de 2026, sem cobertura nacional completa). Ideal para
    MVP/prototipo. Para producao com cobertura nacional, prefira Judit.

    Referencia: https://trackjud.com.br/pricing e documentacao OpenAPI 3.1.

    Autenticacao:
        Header: X-Api-Key: <JURIDICO_PROVIDER_API_KEY>
    """

    _PATH_PROCESSO = "/v1/processos/consultar"
    _PATH_MOVIMENTACOES = "/v1/processos/movimentacoes"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or _exigir_api_key("TrackJud")
        self._base_url = _TRACKJUD_BASE_URL

    def _headers(self) -> dict[str, str]:
        # INTEGRACAO: TrackJud usa X-Api-Key conforme documentacao OpenAPI 3.1
        return {
            "X-Api-Key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def buscar_processo(self, numero_processo: str, tribunal: str | None = None) -> Processo:
        """Consulta processo na API TrackJud.

        O TrackJud aceita POST com corpo JSON contendo o numero CNJ.
        """
        url = self._base_url + self._PATH_PROCESSO
        body: dict[str, Any] = {"numero_processo": numero_processo}
        if tribunal:
            body["tribunal"] = tribunal

        logger.info("trackjud_buscar_processo", numero=numero_processo)

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_COMERCIAL) as client:
                response = await client.post(url, json=body, headers=self._headers())
        except httpx.TimeoutException as exc:
            raise JuridicoAPIError(source="TrackJud", reason="Timeout na consulta") from exc
        except httpx.RequestError as exc:
            raise JuridicoAPIError(source="TrackJud", reason=f"Erro de rede: {exc}") from exc

        if response.status_code == 401:
            raise JuridicoAPIError(
                source="TrackJud",
                status_code=401,
                reason="Credencial invalida. Verifique JURIDICO_PROVIDER_API_KEY.",
            )
        if response.status_code == 404:
            raise JuridicoNotFoundError(numero_processo, tribunal)
        if response.status_code != 200:
            raise JuridicoAPIError(
                source="TrackJud",
                status_code=response.status_code,
                reason=response.text[:200],
            )

        data = response.json()
        return self._parse_processo(data, tribunal or "")

    async def listar_movimentacoes(
        self, numero_processo: str, tribunal: str, limite: int = 20
    ) -> list[Movimentacao]:
        """Lista movimentacoes via TrackJud."""
        url = self._base_url + self._PATH_MOVIMENTACOES
        body: dict[str, Any] = {
            "numero_processo": numero_processo,
            "tribunal": tribunal,
            "limite": limite,
        }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_COMERCIAL) as client:
                response = await client.post(url, json=body, headers=self._headers())
        except httpx.TimeoutException as exc:
            raise JuridicoAPIError(
                source="TrackJud", reason="Timeout ao listar movimentacoes"
            ) from exc
        except httpx.RequestError as exc:
            raise JuridicoAPIError(source="TrackJud", reason=f"Erro de rede: {exc}") from exc

        if response.status_code == 401:
            raise JuridicoAPIError(
                source="TrackJud", status_code=401, reason="Credencial invalida."
            )
        if response.status_code == 404:
            raise JuridicoNotFoundError(numero_processo, tribunal)
        if response.status_code != 200:
            raise JuridicoAPIError(source="TrackJud", status_code=response.status_code)

        data = response.json()
        items: list[dict[str, Any]] = data.get(
            "movimentacoes", data if isinstance(data, list) else []
        )
        return [self._parse_movimentacao(m) for m in items[:limite]]

    def _parse_processo(self, data: dict[str, Any], tribunal_fallback: str) -> Processo:
        """Converte resposta TrackJud para schema Processo interno.

        INTEGRACAO: Nomes de campo baseados na documentacao OpenAPI 3.1 do TrackJud.
        Validar com credencial real antes de producao.
        """
        nivel_sigilo = int(data.get("nivel_sigilo", 0))
        numero = str(data.get("numero_processo", data.get("numero", "")))
        if nivel_sigilo > 0:
            raise JuridicoSigiloError(numero, nivel_sigilo)

        partes = [
            Parte(
                nome=str(p.get("nome", "")),
                tipo=str(p.get("tipo", "")),
                polo=p.get("polo"),
            )
            for p in data.get("partes", [])
        ]
        orgao_raw: dict[str, Any] | None = data.get("orgao_julgador", data.get("orgao"))
        orgao = (
            OrgaoJulgador(
                codigo=orgao_raw.get("codigo"),
                nome=str(orgao_raw.get("nome", "")),
                codigo_municipio_ibge=orgao_raw.get("codigo_municipio_ibge"),
            )
            if orgao_raw
            else None
        )

        return Processo(
            numero_processo=numero,
            tribunal=str(data.get("tribunal", tribunal_fallback)),
            grau=data.get("grau"),
            data_ajuizamento=_iso_ou_none(data.get("data_ajuizamento")),
            data_ultima_atualizacao=_iso_ou_none(data.get("data_ultima_atualizacao")),
            nivel_sigilo=nivel_sigilo,
            classe_codigo=data.get("classe_codigo"),
            classe_nome=data.get("classe_nome"),
            assuntos=[],
            orgao_julgador=orgao,
            partes=partes,
            movimentacoes=[self._parse_movimentacao(m) for m in data.get("movimentacoes", [])],
            formato=data.get("formato"),
            sistema=data.get("sistema"),
        )

    def _parse_movimentacao(self, data: dict[str, Any]) -> Movimentacao:
        """Converte item de movimentacao TrackJud para schema interno."""
        data_raw = data.get("data_hora", data.get("data", ""))
        dt = _iso_ou_none(str(data_raw))
        if dt is None:
            logger.warning(
                "movimentacao_sem_data_usando_now",
                provider="trackjud",
                codigo=data.get("codigo"),
            )
            dt = datetime.now(tz=timezone.utc)
        return Movimentacao(
            codigo=data.get("codigo"),
            nome=str(data.get("nome", data.get("descricao", ""))),
            data_hora=dt,
            complementos=data.get("complementos", []),
        )


__all__ = ["EscavadorProvider", "JuditProvider", "TrackJudProvider"]
