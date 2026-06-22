"""Módulo DJe - Domicílio Judicial Eletrônico (Fase 4).

Acesso às comunicações processuais oficiais via API Comunica (PDPJ/CNJ).
Fundamento: Resolução CNJ 455/2022.

AVISO DE EFEITO JURÍDICO: A confirmação de leitura de uma intimação por esta
API tem efeito jurídico real e inicia a contagem oficial do prazo processual.
Nenhuma operação destrutiva é executada sem confirmação explícita do operador
E habilitação explícita via variável de ambiente DJE_PERMITIR_CONFIRMACAO_LEITURA.

CREDENCIAMENTO: A autenticação OAuth2 do DJe exige certificado digital ICP-Brasil
(e-CNPJ ou e-CPF). O credenciamento é feito via portal do Domicílio Judicial
Eletrônico. As credenciais são configuradas exclusivamente via variáveis de
ambiente - nunca em código-fonte.
"""

from mcp_juridico_brasil.dje.client import DJeOAuthClient
from mcp_juridico_brasil.dje.provider import DJeProvider
from mcp_juridico_brasil.dje.schemas import (
    Intimacao,
    ListaIntimacoes,
    ResultadoConfirmacaoLeitura,
    StatusIntimacao,
)

__all__ = [
    "DJeOAuthClient",
    "DJeProvider",
    "Intimacao",
    "ListaIntimacoes",
    "ResultadoConfirmacaoLeitura",
    "StatusIntimacao",
]
