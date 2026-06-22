"""Schemas Pydantic para o módulo DJe - Domicílio Judicial Eletrônico.

Modela as comunicações processuais oficiais recebidas via API Comunica (PDPJ/CNJ).
Fundamento: Resolução CNJ 455/2022 e Manual DJe 3a Edição (2025).

COMPLIANCE E LGPD:
- Campos de identificação pessoal (CPF/CNPJ do destinatário) não são
  expostos nos schemas públicos - o destinatário é identificado pelo
  tenant_id configurado via DJE_BEHALF_OF_CPF no ambiente.
- Intimações com sigilosas (is_sigilosa=True) têm conteúdo suprimido
  no retorno das tools; apenas metadados não sensíveis são exibidos.
- Dados de intimação são retidos apenas em memória durante a sessão MCP.
  Nenhum armazenamento persistente local é realizado por este módulo.

EFEITO JURÍDICO:
- O campo prazo_em_dias indica o prazo processual que COMEÇA A CORRER
  a partir da data de confirmação da leitura.
- O campo data_disponibilizacao é a data de publicação no DJe.
- O campo data_leitura é preenchido somente após confirmação explícita
  via API (operação com efeito jurídico irreversível).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class StatusIntimacao(str, Enum):
    """Status de leitura de uma comunicação no DJe."""

    PENDENTE = "pendente"
    LIDA = "lida"
    EXPIRADA = "expirada"


class Intimacao(BaseModel):
    """Comunicação processual recebida via Domicílio Judicial Eletrônico.

    Campos alinhados ao schema da API Comunica (PDPJ/CNJ - Resolução CNJ 455/2022).
    Referência: Manual DJe 3a Edição (2025) - seção de estrutura de comunicações.

    AVISO DE EFEITO JURÍDICO: O campo `status` transitando de PENDENTE para
    LIDA tem efeito jurídico irreversível: inicia a contagem do prazo
    processual definido em `prazo_em_dias`.
    """

    id: str = Field(description="Identificador único da comunicação no DJe.")
    numero_processo: str = Field(
        description="Número CNJ do processo ao qual a comunicação pertence."
    )
    orgao_julgador: str = Field(description="Nome do órgão julgador que expediu a comunicação.")
    tipo_comunicacao: str = Field(
        description=("Tipo da comunicação (ex.: 'Intimação', 'Citação', 'Notificação').")
    )
    data_disponibilizacao: datetime = Field(
        description="Data e hora de disponibilização da comunicação no DJe."
    )
    data_leitura: datetime | None = Field(
        default=None,
        description=(
            "Data e hora de confirmação de leitura. Nulo enquanto não confirmada. "
            "ATENÇÃO: Preenchimento tem efeito jurídico - inicia contagem de prazo."
        ),
    )
    prazo_em_dias: int | None = Field(
        default=None,
        description=(
            "Prazo processual em dias que começa a correr após a confirmação da leitura. "
            "Verificar sempre no portal do tribunal - esta informação pode estar desatualizada."
        ),
    )
    status: StatusIntimacao = Field(
        description="Status atual da comunicação (pendente/lida/expirada)."
    )
    is_sigilosa: bool = Field(
        default=False,
        description=(
            "Indica comunicação em segredo de justiça. "
            "Quando True, o conteúdo textual é suprimido pelo módulo DJe "
            "e apenas metadados são retornados."
        ),
    )
    conteudo: str | None = Field(
        default=None,
        description=(
            "Texto da comunicação. Suprimido quando is_sigilosa=True. "
            "Pode estar ausente mesmo em comunicações não sigilosas se "
            "o conteúdo integral for acessível somente pelo portal do DJe."
        ),
    )

    @property
    def pode_ser_confirmada(self) -> bool:
        """Indica se a comunicação pode ser marcada como lida.

        Somente comunicações com status PENDENTE podem ter leitura confirmada.
        """
        return self.status == StatusIntimacao.PENDENTE

    model_config = ConfigDict(use_enum_values=False)


class ListaIntimacoes(BaseModel):
    """Resultado da listagem de intimações do Domicílio Judicial Eletrônico."""

    intimacoes: list[Intimacao] = Field(default_factory=list)
    total: int = Field(description="Número total de comunicações retornadas.")
    pendentes: int = Field(description="Quantidade de comunicações com status PENDENTE.")
    aviso_juridico: str = Field(
        description=(
            "Aviso sobre efeito jurídico da confirmação de leitura. "
            "Exibido sempre como lembrete ao operador."
        )
    )


class ResultadoConfirmacaoLeitura(BaseModel):
    """Resultado da operação de confirmação de leitura de intimação.

    Esta operação tem efeito jurídico real quando executada no modo real
    (DJE_PERMITIR_CONFIRMACAO_LEITURA=true). No modo dry-run (padrão),
    nenhuma chamada de escrita é realizada na API DJe.
    """

    id_intimacao: str = Field(description="ID da intimação processada.")
    numero_processo: str = Field(description="Número CNJ do processo.")
    executado: bool = Field(
        description=(
            "True se a marcação foi efetivamente realizada na API DJe. "
            "False em modo dry-run (padrão seguro) ou se já estava lida."
        )
    )
    modo_dry_run: bool = Field(
        description=(
            "True quando operando em modo seguro/simulação (DJE_PERMITIR_CONFIRMACAO_LEITURA "
            "ausente ou false). Neste modo, NENHUMA marcação é feita na API - "
            "sem efeito jurídico."
        )
    )
    data_leitura: datetime | None = Field(
        default=None,
        description=(
            "Data e hora da confirmação quando executado=True. "
            "Nulo em modo dry-run ou se já estava lida anteriormente."
        ),
    )
    ja_estava_lida: bool = Field(
        default=False,
        description="True se a intimação já havia sido confirmada anteriormente (idempotência).",
    )
    aviso_juridico: str = Field(
        description="Aviso de efeito jurídico exibido sempre nesta operação."
    )
    mensagem: str = Field(description="Mensagem descritiva do resultado da operação.")


__all__ = [
    "Intimacao",
    "ListaIntimacoes",
    "ResultadoConfirmacaoLeitura",
    "StatusIntimacao",
]
