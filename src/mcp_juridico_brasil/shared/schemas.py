"""Schemas Pydantic compartilhados entre os módulos do MCP Jurídico Brasil.

NOTA LGPD: Estes schemas não persistem CPF/CNPJ de partes nem dados sensíveis
(saúde, orientação sexual, origem étnica) mesmo quando presentes nos autos.
Campos de identificação de partes adversas são retornados somente para o
advogado autenticado cujo processo está sendo monitorado.
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

    LGPD: O campo 'nome' é retornado como presente na API pública DataJud.
    CPF/CNPJ não é indexado pela API pública por razões de LGPD.
    """

    nome: str
    tipo: str  # ex.: "Advogado", "Autor", "Réu", "Interessado"
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
    """Representação de um processo judicial.

    nivel_sigilo == 0 indica processo público.
    nivel_sigilo > 0 NUNCA deve ser armazenado ou exibido sem autorização judicial.
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
    formato: str | None = None  # "Físico" ou "Eletrônico"
    sistema: str | None = None  # "PJe", "eSAJ", "eProc", etc.

    @property
    def e_sigiloso(self) -> bool:
        return self.nivel_sigilo > 0


__all__ = ["Assunto", "Movimentacao", "OrgaoJulgador", "Parte", "Processo"]
