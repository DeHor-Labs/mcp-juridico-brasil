"""Modulo de providers comerciais para o MCP Juridico Brasil.

Providers disponiveis:
- JuditProvider  - judit.io (B2B, webhook nativo, 100% tribunais declarado)
- EscavadorProvider - escavador.com/business/api (SDK Python, CPF/CNPJ/OAB)
- TrackJudProvider - trackjud.com.br (por consulta, bom para MVP/prototipo)

Todos os providers implementam ProcessoProvider e podem ser selecionados via
variavel de ambiente JURIDICO_PROVIDER (valores: datajud | judit | escavador | trackjud).

A integracao real de cada provider comercial fica pronta para plugar a chave
via JURIDICO_PROVIDER_API_KEY - nenhuma credencial e hardcoded aqui.
"""

from mcp_juridico_brasil.comercial.providers import (
    EscavadorProvider,
    JuditProvider,
    TrackJudProvider,
)
from mcp_juridico_brasil.comercial.registry import selecionar_provider
from mcp_juridico_brasil.comercial.webhook import WebhookPayload, processar_webhook

__all__ = [
    "EscavadorProvider",
    "JuditProvider",
    "TrackJudProvider",
    "WebhookPayload",
    "processar_webhook",
    "selecionar_provider",
]
