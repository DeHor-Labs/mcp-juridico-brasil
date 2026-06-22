"""Schemas Pydantic compartilhados entre os modulos do MCP Juridico Brasil.

NOTA LGPD: Estes schemas nao persistem CPF/CNPJ de partes nem dados sensiveis
(saude, orientacao sexual, origem etnica) mesmo quando presentes nos autos.
Campos de identificacao de partes adversas sao retornados somente para o
advogado autenticado cujo processo esta sendo monitorado.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class OrgaoJulgador(BaseModel):
    codigo: int | None = None
    nome: str
    codigo_municipio_ibge: int | None = None


class Parte(BaseModel):
    """Parte processual.

    LGPD: O campo 'nome' e retornado como presente na API publica DataJud.
    CPF/CNPJ nao e indexado pela API publica por razoes de LGPD.
    """

    nome: str
    tipo: str  # ex.: "Advogado", "Autor", "Reu", "Interessado"
    polo: str | None = None  # "ativo", "passivo", "outros"


class Movimentacao(BaseModel):
    codigo: int | None = None
    nome: str
    data_hora: datetime
    complementos: list[dict[str, Any]] = Field(default_factory=list)


class Assunto(BaseModel):
    codigo: int
    nome: str
    principal: bool = False


class Processo(BaseModel):
    """Representacao de um processo judicial.

    nivel_sigilo == 0 indica processo publico.
    nivel_sigilo > 0 NUNCA deve ser armazenado ou exibido sem autorizacao judicial.
    """

    numero_processo: str
    tribunal: str
    grau: str | None = None  # "G1", "G2", "JE", "JESP"
    data_ajuizamento: datetime | None = None
    data_ultima_atualizacao: datetime | None = None
    nivel_sigilo: int = Field(default=0, ge=0)
    classe_codigo: int | None = None
    classe_nome: str | None = None
    assuntos: list[Assunto] = Field(default_factory=list)
    orgao_julgador: OrgaoJulgador | None = None
    partes: list[Parte] = Field(default_factory=list)
    movimentacoes: list[Movimentacao] = Field(default_factory=list)
    formato: str | None = None  # "Fisico" ou "Eletronico"
    sistema: str | None = None  # "PJe", "eSAJ", "eProc", etc.

    @property
    def e_sigiloso(self) -> bool:
        return self.nivel_sigilo > 0


__all__ = ["Assunto", "Movimentacao", "OrgaoJulgador", "Parte", "Processo"]
