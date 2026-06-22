"""Cliente OAuth2 para o Domicílio Judicial Eletrônico (DJe) - API Comunica PDPJ/CNJ.

Implementa a estrutura do fluxo OAuth2 client_credentials via GeCli.
Fundamento: Resolução CNJ 455/2022 e Manual DJe 3a Edição (2025).

CREDENCIAMENTO REAL - O QUE FALTA PARA PRODUCAO:
1. Obter client_id e client_secret junto ao portal DJe (exige certificado ICP-Brasil).
2. Configurar o caminho do certificado digital em DJE_CERT_PATH e senha em DJE_CERT_SENHA.
3. Validar que o endpoint de token do GeCli é o correto para o ambiente (homologacao vs producao).
4. Verificar se a versao atual da API (pós-migração obrigatória de 31/03/2026) usa
   o mesmo fluxo client_credentials ou se houve mudança para PKCE/device-flow.
5. Confirmar formato do header On-behalf-Of (CPF com ou sem pontuacao).
6. Testar refresh de token com credencial real - o DJe usa expires_in padrao OAuth2.

SEGURANCA:
- Credenciais exclusivamente via variavel de ambiente (nunca em codigo ou log).
- Tokens de acesso nunca aparecem em logs (nivel DEBUG ou superior).
- O campo DJE_BEHALF_OF_CPF e obrigatorio para auditoria - cada requisicao
  carrega este header para rastreabilidade.
- URLs base sao constantes fixas; parametros de busca nunca sao interpolados
  na URL base para evitar SSRF.

NOTA DE INTEGRACAO: Esta implementacao e mock-ready. O DJeOAuthClient aceita
um parametro `_httpx_client` nos metodos para injecao de mock nos testes.
Em producao, o httpx.AsyncClient e criado internamente com as credenciais reais.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from mcp_juridico_brasil._core.errors import JuridicoAPIError
from mcp_juridico_brasil._core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constantes de URL (fixas - sem interpolacao de dados externos)
# ---------------------------------------------------------------------------

# URL de token do GeCli (ambiente de producao)
# INTEGRACAO: Confirmar endpoint correto pos-migracao 31/03/2026.
# O endpoint de homologacao pode ser diferente - consultar Manual DJe 3a Ed.
_GECLI_TOKEN_URL = "https://gecli.cnj.jus.br/auth/realms/pdpj/protocol/openid-connect/token"

# URL base da API Comunica (DJe producao)
# INTEGRACAO: Confirmar URL pos-migracao. Pode ter mudado para api.pdpj.jus.br.
_DJE_BASE_URL = "https://domicilio-eletronico.pdpj.jus.br"

# Paths fixos da API Comunica
_PATH_EU = "/api/v1/eu"
_PATH_COMUNICACOES = "/comunicacoes"
_PATH_PROCESSO_COMUNICACOES = "/processos/{numero}/comunicacoes/{id}"
_PATH_PROCESSO_LOGS = "/processos/{numero}/logs"

# Margem de seguranca para renovar token antes de expirar (segundos)
_TOKEN_REFRESH_MARGIN_S = 60


# ---------------------------------------------------------------------------
# Token OAuth2
# ---------------------------------------------------------------------------


@dataclass
class _TokenOAuth2:
    """Token de acesso OAuth2 com controle de expiração."""

    access_token: str
    expires_at: float  # timestamp Unix
    token_type: str = "Bearer"
    scope: str = ""

    def esta_valido(self) -> bool:
        """Retorna True se o token ainda e valido (com margem de seguranca)."""
        return time.monotonic() < self.expires_at - _TOKEN_REFRESH_MARGIN_S


@dataclass(frozen=True)
class _CredenciaisDJe:
    """Credenciais OAuth2 do DJe carregadas exclusivamente de variaveis de ambiente.

    SEGURANCA: Os campos sao carregados sob demanda de os.environ para que
    nao fiquem em memoria alem do necessario. O client_secret nunca e logado.
    O dataclass e imutavel (frozen=True) para impedir modificacao acidental
    apos a carga das credenciais.

    INTEGRACAO PENDENTE:
    - dje_cert_path: caminho do certificado ICP-Brasil em formato PFX/P12.
      Em producao, o GeCli pode exigir mTLS com o certificado digital.
      Verificar com o portal DJe se client_credentials usa apenas secret
      ou se exige certificado no handshake TLS.
    - dje_cert_senha: senha do certificado (obrigatoria se cert_path configurado).
    """

    client_id: str = ""
    client_secret: str = ""
    behalf_of_cpf: str = ""
    cert_path: str = ""
    cert_senha: str = ""

    @classmethod
    def from_env(cls) -> _CredenciaisDJe:
        """Carrega credenciais das variaveis de ambiente.

        Variaveis esperadas:
            DJE_CLIENT_ID        - client_id do OAuth2 no GeCli
            DJE_CLIENT_SECRET    - client_secret do OAuth2 no GeCli (NUNCA logar)
            DJE_BEHALF_OF_CPF    - CPF do responsavel (sem pontuacao) para auditoria
            DJE_CERT_PATH        - (opcional) caminho do certificado ICP-Brasil PFX/P12
            DJE_CERT_SENHA       - (opcional) senha do certificado

        INTEGRACAO: Confirmar nomes exatos das variaveis com o portal DJe.
        """
        return cls(
            client_id=os.environ.get("DJE_CLIENT_ID", ""),
            client_secret=os.environ.get("DJE_CLIENT_SECRET", ""),
            behalf_of_cpf=os.environ.get("DJE_BEHALF_OF_CPF", ""),
            cert_path=os.environ.get("DJE_CERT_PATH", ""),
            cert_senha=os.environ.get("DJE_CERT_SENHA", ""),
        )

    def esta_configurado(self) -> bool:
        """Retorna True se as credenciais minimas estao presentes."""
        return bool(self.client_id and self.client_secret and self.behalf_of_cpf)


# ---------------------------------------------------------------------------
# Cliente OAuth2 principal
# ---------------------------------------------------------------------------


class DJeOAuthClient:
    """Cliente HTTP autenticado para a API Comunica do Domicílio Judicial Eletrônico.

    Gerencia o ciclo de vida do token OAuth2 (obtencao e refresh automatico).
    Todas as requisicoes carregam o header On-behalf-Of para auditoria no CNJ.

    Uso em producao:
        client = DJeOAuthClient()
        comunicacoes = await client.listar_comunicacoes()

    Uso com mock (testes):
        mock_httpx = respx.MockTransport(...)
        client = DJeOAuthClient(_httpx_transport=mock_httpx)

    INTEGRACAO PENDENTE:
    - Validar fluxo de refresh - a API DJe pode exigir novo token a cada sessao.
    - Verificar se o GeCli suporta refresh_token ou apenas client_credentials puro.
    - Confirmar se o certificado ICP-Brasil e necessario no handshake mTLS.
    """

    def __init__(
        self,
        credenciais: _CredenciaisDJe | None = None,
        base_url: str = _DJE_BASE_URL,
        token_url: str = _GECLI_TOKEN_URL,
        _httpx_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._creds = credenciais or _CredenciaisDJe.from_env()
        self._base_url = base_url
        self._token_url = token_url
        self._token: _TokenOAuth2 | None = None
        # _httpx_transport permite injecao de mock nos testes sem tocar em rede real
        self._transport = _httpx_transport

    def _exigir_credenciais(self) -> None:
        """Lanca JuridicoAPIError se as credenciais minimas nao estiverem configuradas."""
        if not self._creds.esta_configurado():
            raise JuridicoAPIError(
                source="DJe",
                reason=(
                    "Credenciais do Domicílio Judicial Eletrônico ausentes. "
                    "Configure DJE_CLIENT_ID, DJE_CLIENT_SECRET e DJE_BEHALF_OF_CPF "
                    "nas variáveis de ambiente. O credenciamento exige certificado "
                    "digital ICP-Brasil - consulte o portal do DJe para instruções."
                ),
            )

    def _httpx_client(self) -> httpx.AsyncClient:
        """Cria AsyncClient com transporte opcional para testes."""
        kwargs: dict[str, Any] = {"timeout": 30.0}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    def _headers_autenticados(self, token: str) -> dict[str, str]:
        """Monta headers padrao com autenticacao e header de auditoria On-behalf-Of.

        INTEGRACAO: Confirmar formato exato do header On-behalf-Of.
        O Manual DJe 3a Ed. descreve CPF sem pontuacao (11 digitos).
        """
        return {
            "Authorization": f"Bearer {token}",
            "On-behalf-Of": self._creds.behalf_of_cpf,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _obter_token(self) -> str:
        """Obtém ou renova o token OAuth2 via GeCli (client_credentials).

        O token e armazenado em cache ate expirar (com margem de seguranca).
        Em caso de erro de autenticacao, lanca JuridicoAPIError com orientacao.

        INTEGRACAO PENDENTE COM CREDENCIAL REAL:
        - Confirmar que o grant_type 'client_credentials' e suportado pelo GeCli
          na versao pos-migracao 31/03/2026.
        - Se o GeCli exigir certificado no handshake (mTLS), adicionar ssl_context
          aqui com o certificado ICP-Brasil carregado de DJE_CERT_PATH.
        - Validar campo 'scope' necessario para acesso a /comunicacoes.
        - O response pode incluir 'refresh_token' - implementar refresh se disponivel
          para evitar nova autenticacao a cada expiracao.

        Returns:
            Token de acesso (string Bearer). NUNCA registrar em log.
        """
        self._exigir_credenciais()

        # Verificar cache
        if self._token is not None and self._token.esta_valido():
            return self._token.access_token

        logger.info("dje_oauth_obtendo_token", client_id=self._creds.client_id)

        payload = {
            "grant_type": "client_credentials",
            "client_id": self._creds.client_id,
            "client_secret": self._creds.client_secret,
            # INTEGRACAO: scope pode ser necessario - confirmar com documentacao DJe
            # "scope": "comunicacoes:read comunicacoes:write",
        }

        try:
            async with self._httpx_client() as http:
                response = await http.post(
                    self._token_url,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.TimeoutException as exc:
            raise JuridicoAPIError(
                source="DJe/GeCli", reason="Timeout ao obter token OAuth2"
            ) from exc
        except httpx.RequestError as exc:
            raise JuridicoAPIError(
                source="DJe/GeCli", reason=f"Erro de rede ao obter token: {exc}"
            ) from exc

        if response.status_code == 401:
            raise JuridicoAPIError(
                source="DJe/GeCli",
                status_code=401,
                reason=(
                    "Credenciais DJe inválidas (401). Verifique DJE_CLIENT_ID e "
                    "DJE_CLIENT_SECRET. O credenciamento exige certificado ICP-Brasil "
                    "registrado no portal do Domicílio Judicial Eletrônico."
                ),
            )
        if response.status_code != 200:
            # SEGURANCA: Nao incluir response.text no erro - o Keycloak em modo debug
            # pode refletir os parametros da requisicao (incluindo client_secret) no corpo.
            raise JuridicoAPIError(
                source="DJe/GeCli",
                status_code=response.status_code,
                reason="Falha ao obter token OAuth2. Verifique as credenciais configuradas.",
            )

        data: dict[str, Any] = response.json()
        access_token: str = data.get("access_token", "")
        if not access_token:
            raise JuridicoAPIError(
                source="DJe/GeCli",
                reason="Resposta de token OAuth2 sem 'access_token'.",
            )

        expires_in = int(data.get("expires_in", 300))
        self._token = _TokenOAuth2(
            access_token=access_token,
            expires_at=time.monotonic() + expires_in,
            token_type=data.get("token_type", "Bearer"),
            scope=data.get("scope", ""),
        )

        # SEGURANCA: Nunca logar o token em nivel algum
        logger.info(
            "dje_oauth_token_obtido",
            expires_in=expires_in,
            token_type=self._token.token_type,
        )
        return self._token.access_token

    async def obter_tenant_id(self) -> str:
        """Recupera o tenant_id associado ao credencial configurado.

        Endpoint: GET /api/v1/eu

        O tenant_id e o identificador do cadastrado no DJe (empresa/pessoa).
        Necessario para filtrar comunicacoes corretamente.

        INTEGRACAO: Confirmar estrutura da resposta com credencial real.
        O campo retornado pode ser 'id', 'tenantId' ou 'cnpj'.

        Returns:
            tenant_id como string.
        """
        token = await self._obter_token()
        url = self._base_url + _PATH_EU

        try:
            async with self._httpx_client() as http:
                response = await http.get(url, headers=self._headers_autenticados(token))
        except httpx.RequestError as exc:
            raise JuridicoAPIError(source="DJe", reason=f"Erro de rede: {exc}") from exc

        if response.status_code == 401:
            self._token = None  # invalidar cache
            raise JuridicoAPIError(
                source="DJe",
                status_code=401,
                reason="Token expirado ou inválido ao consultar /eu.",
            )
        if response.status_code != 200:
            raise JuridicoAPIError(
                source="DJe",
                status_code=response.status_code,
                reason="Falha ao consultar /eu. Verifique as credenciais e permissoes do cadastrado.",
            )

        data = response.json()
        # INTEGRACAO: Ajustar campo 'id' conforme resposta real do /api/v1/eu
        tenant_id: str = str(data.get("id", data.get("tenantId", data.get("cnpj", ""))))
        logger.info("dje_tenant_obtido", tenant_id=tenant_id)
        return tenant_id

    async def listar_comunicacoes(
        self,
        numero_processo: str | None = None,
        apenas_pendentes: bool = True,
        limite: int = 50,
    ) -> list[dict[str, Any]]:
        """Lista comunicações do DJe para o cadastrado.

        Endpoint: GET /comunicacoes

        Args:
            numero_processo: Filtrar por numero CNJ (opcional).
            apenas_pendentes: Se True, retorna apenas comunicacoes nao lidas.
            limite: Numero maximo de registros (max recomendado pela API: 7 dias).

        INTEGRACAO PENDENTE COM CREDENCIAL REAL:
        - Confirmar nomes dos parametros de query (pode ser 'situacao', 'status', 'lida').
        - Verificar paginacao (offset/limit ou cursor).
        - Confirmar se 'apenas_pendentes' corresponde a situacao='pendente' ou lida=false.
        - Validar estrutura de cada item retornado (campos 'id', 'processo', 'tipo', etc.).

        Returns:
            Lista de dicionarios raw da API (parsing feito no DJeProvider).
        """
        token = await self._obter_token()
        url = self._base_url + _PATH_COMUNICACOES

        params: dict[str, Any] = {"limit": limite}
        if numero_processo:
            # Parametro de query - nunca interpolado na URL base (anti-SSRF)
            params["numeroProcesso"] = numero_processo
        if apenas_pendentes:
            # INTEGRACAO: confirmar nome do parametro de status na API real
            params["situacao"] = "pendente"

        try:
            async with self._httpx_client() as http:
                response = await http.get(
                    url,
                    params=params,
                    headers=self._headers_autenticados(token),
                )
        except httpx.TimeoutException as exc:
            raise JuridicoAPIError(source="DJe", reason="Timeout ao listar comunicações") from exc
        except httpx.RequestError as exc:
            raise JuridicoAPIError(source="DJe", reason=f"Erro de rede: {exc}") from exc

        if response.status_code == 401:
            self._token = None
            raise JuridicoAPIError(
                source="DJe",
                status_code=401,
                reason="Token expirado. Tente novamente.",
            )
        if response.status_code != 200:
            raise JuridicoAPIError(
                source="DJe",
                status_code=response.status_code,
                reason="Falha ao listar comunicacoes. Verifique as credenciais e permissoes.",
            )

        data = response.json()
        # INTEGRACAO: A resposta pode ser lista direta ou embrulhada em 'content'/'items'
        if isinstance(data, list):
            items: list[dict[str, Any]] = data
        else:
            items = data.get("content", data.get("items", data.get("comunicacoes", [])))

        logger.info("dje_comunicacoes_listadas", total=len(items))
        return items[:limite]

    async def confirmar_leitura(
        self,
        numero_processo: str,
        id_comunicacao: str,
    ) -> dict[str, Any]:
        """Confirma leitura de uma comunicação no DJe.

        Endpoint: PUT /processos/{numero}/comunicacoes/{id}

        ATENCAO - EFEITO JURIDICO IRREVERSIVEL:
        Esta operacao confirma oficialmente a ciência da comunicacao no
        Domicilio Judicial Eletronico. A confirmacao:
        - Fica registrada com timestamp imutavel no sistema do CNJ.
        - INICIA a contagem do prazo processual correspondente.
        - NAO pode ser desfeita via API.

        Este metodo e chamado apenas pelo DJeProvider quando TODAS as
        seguintes condicoes forem satisfeitas:
        1. O parametro confirmar=True foi explicitamente passado pela tool.
        2. A variavel de ambiente DJE_PERMITIR_CONFIRMACAO_LEITURA=true esta definida.
        3. A intimacao tem status PENDENTE (pode_ser_confirmada=True).

        INTEGRACAO PENDENTE COM CREDENCIAL REAL:
        - Confirmar metodo HTTP (PUT vs PATCH) no endpoint real.
        - Verificar se e necessario corpo JSON ou requisicao sem corpo.
        - Confirmar estrutura da resposta de sucesso (codigo 200 ou 204).
        - Verificar campo de timestamp retornado ('dataLeitura' vs 'ciencia_em').

        Args:
            numero_processo: Numero CNJ do processo (sem formatacao).
            id_comunicacao: ID unico da comunicacao no DJe.

        Returns:
            Dicionario com dados da confirmacao (incluindo timestamp).
        """
        token = await self._obter_token()

        # Path com identificadores - nao sao dados externos arbitrarios,
        # mas IDs validados pelo DJeProvider antes de chegar aqui.
        # Anti-SSRF: a URL base e constante; apenas o path varia com IDs proprios.
        path = _PATH_PROCESSO_COMUNICACOES.format(
            numero=numero_processo,
            id=id_comunicacao,
        )
        url = self._base_url + path

        # INTEGRACAO: Verificar se PUT precisa de corpo. Alguns endpoints aceitam
        # corpo vazio ou {"lida": true}. Usar corpo minimo por seguranca.
        corpo: dict[str, Any] = {}

        try:
            async with self._httpx_client() as http:
                response = await http.put(
                    url,
                    json=corpo,
                    headers=self._headers_autenticados(token),
                )
        except httpx.TimeoutException as exc:
            raise JuridicoAPIError(source="DJe", reason="Timeout ao confirmar leitura") from exc
        except httpx.RequestError as exc:
            raise JuridicoAPIError(source="DJe", reason=f"Erro de rede: {exc}") from exc

        if response.status_code == 401:
            self._token = None
            raise JuridicoAPIError(
                source="DJe",
                status_code=401,
                reason="Token expirado ao confirmar leitura.",
            )
        if response.status_code == 409:
            # Conflito - comunicacao ja foi lida (idempotencia)
            logger.info(
                "dje_confirmacao_leitura_ja_lida",
                id=id_comunicacao,
                processo=numero_processo,
            )
            return {"ja_lida": True, "id": id_comunicacao}

        if response.status_code not in (200, 204):
            raise JuridicoAPIError(
                source="DJe",
                status_code=response.status_code,
                reason="Falha ao confirmar leitura. Verifique as credenciais e o id da comunicacao.",
            )

        # Resposta 204 (No Content) e valida para PUT bem-sucedido
        result: dict[str, Any] = {}
        if response.status_code == 200 and response.content:
            result = response.json()

        logger.info(
            "dje_confirmacao_leitura_realizada",
            id=id_comunicacao,
            processo=numero_processo,
        )
        return {
            "confirmado": True,
            "id": id_comunicacao,
            "numero_processo": numero_processo,
            # INTEGRACAO: Ajustar campo de timestamp conforme resposta real
            "data_leitura": result.get("dataLeitura", result.get("ciencia_em")),
        }


__all__ = ["DJeOAuthClient"]
