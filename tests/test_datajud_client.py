"""Testes de integracao do DataJudClient com mock HTTP via respx.

Cobre os cenarios principais da Fase 1 MVP:
- Processo publico encontrado (happy path)
- Processo nao encontrado (JuridicoNotFoundError)
- Processo sigiloso (JuridicoSigiloError - bloqueia ANTES de qualquer retorno)
- Movimentacoes ordenadas por data decrescente
- Erro de rede/conexao (propaga excecao apos retries)
- Tribunal desconhecido (JuridicoAPIError)

Nota sobre URLs: o HTTPClient cria httpx.AsyncClient com
  base_url = "https://api-publica.datajud.cnj.jus.br/api_publica_tjsp/_search"
e executa POST "". O httpx normaliza base_url com file-path (adiciona trailing slash),
gerando URL final com "/_search/". O respx precisa registrar exatamente essa URL.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
import respx
from httpx import ConnectError, Response

from mcp_juridico_brasil._core.errors import (
    JuridicoAPIError,
    JuridicoNotFoundError,
    JuridicoSigiloError,
)
from mcp_juridico_brasil.datajud.client import DataJudClient

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

BASE_URL = "https://api-publica.datajud.cnj.jus.br"

# httpx adiciona trailing slash quando base_url e um path sem "/" no final
# Ex: base_url=".../_search" + path="" => URL final ".../_search/"
TJSP_SEARCH = f"{BASE_URL}/api_publica_tjsp/_search/"
TJRJ_SEARCH = f"{BASE_URL}/api_publica_tjrj/_search/"
NUMERO = "00012345620238260100"


# ---------------------------------------------------------------------------
# Payloads de resposta simulada
# ---------------------------------------------------------------------------


def _resp_processo_publico(numero: str = NUMERO) -> dict[str, Any]:
    """Payload DataJud simulando processo publico no TJSP."""
    return {
        "hits": {
            "hits": [
                {
                    "_source": {
                        "numeroProcesso": numero,
                        "tribunal": "TJSP",
                        "grau": "G1",
                        "nivelSigilo": 0,
                        "dataAjuizamento": "2023-03-15T00:00:00.000Z",
                        "dataHoraUltimaAtualizacao": "2024-01-10T14:30:00.000Z",
                        "classe": {"codigo": 7, "nome": "Procedimento Comum"},
                        "assuntos": [
                            {
                                "codigo": 10435,
                                "nome": "Indenizacao por Dano Material",
                                "principal": True,
                            }
                        ],
                        "orgaoJulgador": {
                            "codigo": 1,
                            "nome": "1a Vara Civel da Capital",
                            "codigoMunicipioIBGE": 3550308,
                        },
                        "partes": [
                            {
                                "nome": "Joao da Silva",
                                "tipo": {"nome": "Autor"},
                                "polo": "ativo",
                            },
                            {
                                "nome": "Empresa XYZ Ltda",
                                "tipo": {"nome": "Reu"},
                                "polo": "passivo",
                            },
                        ],
                        "movimentos": [
                            {
                                "codigo": 11010,
                                "nome": "Juntada de Peticao",
                                "dataHora": "2024-01-10T14:30:00.000Z",
                                "complementosTabelados": [],
                            },
                            {
                                "codigo": 11009,
                                "nome": "Distribuicao",
                                "dataHora": "2023-03-15T09:00:00.000Z",
                                "complementosTabelados": [],
                            },
                        ],
                        "formato": {"nome": "Eletronico"},
                        "sistema": {"nome": "eSAJ"},
                    }
                }
            ]
        }
    }


def _resp_processo_sigiloso(nivel: int = 2) -> dict[str, Any]:
    """Payload DataJud simulando processo com nivelSigilo > 0."""
    return {
        "hits": {
            "hits": [
                {
                    "_source": {
                        "numeroProcesso": NUMERO,
                        "tribunal": "TJSP",
                        "nivelSigilo": nivel,
                    }
                }
            ]
        }
    }


def _resp_vazio() -> dict[str, Any]:
    """Payload DataJud sem resultados (processo nao encontrado)."""
    return {"hits": {"hits": []}}


# ---------------------------------------------------------------------------
# Testes: buscar_por_numero - happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buscar_processo_publico() -> None:
    """Processo publico deve retornar com todos os campos populados."""
    client = DataJudClient()

    with respx.mock:
        respx.post(TJSP_SEARCH).mock(return_value=Response(200, json=_resp_processo_publico()))
        processo = await client.buscar_por_numero(NUMERO, "TJSP")

    assert processo.numero_processo == NUMERO
    assert processo.tribunal == "TJSP"
    assert processo.nivel_sigilo == 0
    assert not processo.e_sigiloso
    assert processo.grau == "G1"
    assert processo.classe_nome == "Procedimento Comum"
    assert len(processo.partes) == 2
    assert len(processo.assuntos) == 1
    assert processo.assuntos[0].principal is True
    assert processo.formato == "Eletronico"
    assert processo.sistema == "eSAJ"
    assert processo.orgao_julgador is not None
    assert processo.orgao_julgador.nome == "1a Vara Civel da Capital"
    # Movimentacoes ordenadas da mais recente para a mais antiga
    assert len(processo.movimentacoes) == 2
    assert processo.movimentacoes[0].nome == "Juntada de Peticao"
    assert processo.movimentacoes[1].nome == "Distribuicao"


@pytest.mark.asyncio
async def test_buscar_processo_data_ajuizamento_parsada() -> None:
    """Data de ajuizamento deve ser convertida corretamente para datetime."""
    client = DataJudClient()

    with respx.mock:
        respx.post(TJSP_SEARCH).mock(return_value=Response(200, json=_resp_processo_publico()))
        processo = await client.buscar_por_numero(NUMERO, "TJSP")

    assert processo.data_ajuizamento is not None
    assert processo.data_ajuizamento.year == 2023
    assert processo.data_ajuizamento.month == 3
    assert processo.data_ajuizamento.day == 15


# ---------------------------------------------------------------------------
# Testes: buscar_por_numero - erros
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buscar_processo_nao_encontrado() -> None:
    """Processo inexistente deve lancar JuridicoNotFoundError."""
    client = DataJudClient()

    with respx.mock:
        respx.post(TJSP_SEARCH).mock(return_value=Response(200, json=_resp_vazio()))

        with pytest.raises(JuridicoNotFoundError) as exc_info:
            await client.buscar_por_numero(NUMERO, "TJSP")

    assert NUMERO in str(exc_info.value)
    assert "TJSP" in str(exc_info.value)


@pytest.mark.asyncio
async def test_buscar_processo_sigiloso_lanca_erro() -> None:
    """Processo sigiloso (nivelSigilo > 0) deve lancar JuridicoSigiloError."""
    client = DataJudClient()

    with respx.mock:
        respx.post(TJSP_SEARCH).mock(
            return_value=Response(200, json=_resp_processo_sigiloso(nivel=2))
        )

        with pytest.raises(JuridicoSigiloError) as exc_info:
            await client.buscar_por_numero(NUMERO, "TJSP")

    erro = exc_info.value
    assert NUMERO in str(erro)
    assert erro.detail["nivel_sigilo"] == 2


@pytest.mark.asyncio
async def test_buscar_processo_sigiloso_nivel_1() -> None:
    """Qualquer nivelSigilo > 0 deve ser bloqueado, mesmo sendo nivel 1."""
    client = DataJudClient()

    with respx.mock:
        respx.post(TJSP_SEARCH).mock(
            return_value=Response(200, json=_resp_processo_sigiloso(nivel=1))
        )

        with pytest.raises(JuridicoSigiloError) as exc_info:
            await client.buscar_por_numero(NUMERO, "TJSP")

    assert exc_info.value.detail["nivel_sigilo"] == 1


@pytest.mark.asyncio
async def test_erro_de_rede_propagado() -> None:
    """Erro de conexao deve ser propagado apos esgotar retries."""
    client = DataJudClient()

    with respx.mock:
        respx.post(TJSP_SEARCH).mock(side_effect=ConnectError("conexao recusada"))

        with pytest.raises(ConnectError):
            await client.buscar_por_numero(NUMERO, "TJSP")


@pytest.mark.asyncio
async def test_tribunal_desconhecido_lanca_api_error() -> None:
    """Tribunal nao mapeado deve lancar JuridicoAPIError antes de qualquer HTTP."""
    client = DataJudClient()

    with pytest.raises(JuridicoAPIError) as exc_info:
        await client.buscar_por_numero(NUMERO, "TRIBUNAL_INEXISTENTE_XYZ")

    assert (
        "TRIBUNAL_INEXISTENTE_XYZ" in str(exc_info.value)
        or "nao suportado" in str(exc_info.value).lower()
    )


# ---------------------------------------------------------------------------
# Testes: listar_movimentacoes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_listar_movimentacoes_ordenadas_decrescente() -> None:
    """Movimentacoes devem retornar da mais recente para a mais antiga."""
    client = DataJudClient()

    with respx.mock:
        respx.post(TJSP_SEARCH).mock(return_value=Response(200, json=_resp_processo_publico()))
        movs = await client.listar_movimentacoes(NUMERO, "TJSP", limite=10)

    assert len(movs) == 2
    assert movs[0].nome == "Juntada de Peticao"
    assert movs[1].nome == "Distribuicao"
    assert movs[0].data_hora > movs[1].data_hora


@pytest.mark.asyncio
async def test_listar_movimentacoes_respeita_limite() -> None:
    """O limite passado deve ser respeitado na fatia retornada."""
    client = DataJudClient()

    with respx.mock:
        respx.post(TJSP_SEARCH).mock(return_value=Response(200, json=_resp_processo_publico()))
        movs = await client.listar_movimentacoes(NUMERO, "TJSP", limite=1)

    assert len(movs) == 1
    assert movs[0].nome == "Juntada de Peticao"


@pytest.mark.asyncio
async def test_listar_movimentacoes_processo_sigiloso_bloqueia() -> None:
    """listar_movimentacoes de processo sigiloso deve propagar JuridicoSigiloError."""
    client = DataJudClient()

    with respx.mock:
        respx.post(TJSP_SEARCH).mock(return_value=Response(200, json=_resp_processo_sigiloso()))

        with pytest.raises(JuridicoSigiloError):
            await client.listar_movimentacoes(NUMERO, "TJSP", limite=5)


# ---------------------------------------------------------------------------
# Testes: buscar_por_numero_multiplos_tribunais
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiplos_tribunais_encontra_no_segundo() -> None:
    """Deve iterar tribunais e retornar quando encontrar o processo."""
    client = DataJudClient()

    with respx.mock:
        respx.post(TJSP_SEARCH).mock(return_value=Response(200, json=_resp_vazio()))
        respx.post(TJRJ_SEARCH).mock(
            return_value=Response(200, json=_resp_processo_publico(numero=NUMERO))
        )

        processo = await client.buscar_por_numero_multiplos_tribunais(
            NUMERO, tribunais=["TJSP", "TJRJ"]
        )

    assert processo is not None
    assert processo.numero_processo == NUMERO


@pytest.mark.asyncio
async def test_multiplos_tribunais_sigilo_para_imediatamente() -> None:
    """JuridicoSigiloError deve interromper a busca imediatamente."""
    client = DataJudClient()

    with respx.mock:
        respx.post(TJSP_SEARCH).mock(return_value=Response(200, json=_resp_processo_sigiloso()))
        # TJRJ nao deve ser chamado - sigilo para antes
        respx.post(TJRJ_SEARCH).mock(return_value=Response(200, json=_resp_vazio()))

        with pytest.raises(JuridicoSigiloError):
            await client.buscar_por_numero_multiplos_tribunais(NUMERO, tribunais=["TJSP", "TJRJ"])


@pytest.mark.asyncio
async def test_multiplos_tribunais_nao_encontrado_em_nenhum() -> None:
    """Processo ausente em todos os tribunais deve lancar JuridicoNotFoundError."""
    client = DataJudClient()

    with respx.mock:
        respx.post(TJSP_SEARCH).mock(return_value=Response(200, json=_resp_vazio()))
        respx.post(TJRJ_SEARCH).mock(return_value=Response(200, json=_resp_vazio()))

        with pytest.raises(JuridicoNotFoundError):
            await client.buscar_por_numero_multiplos_tribunais(NUMERO, tribunais=["TJSP", "TJRJ"])


# ---------------------------------------------------------------------------
# Testes: schema Parte sem CPF/CNPJ (LGPD)
# ---------------------------------------------------------------------------


def test_parte_nao_tem_campo_cpf() -> None:
    """O schema Parte nao deve ter campo CPF/CNPJ (requisito LGPD)."""
    from mcp_juridico_brasil.shared.schemas import Parte

    parte = Parte(nome="Joao da Silva", tipo="Autor", polo="ativo")
    dados = parte.model_dump()

    assert "cpf" not in dados
    assert "cnpj" not in dados
    assert "documento" not in dados


def test_parte_campos_basicos() -> None:
    """Parte deve ter nome, tipo e polo corretamente."""
    from mcp_juridico_brasil.shared.schemas import Parte

    parte = Parte(nome="Maria Souza", tipo="Reu", polo="passivo")
    assert parte.nome == "Maria Souza"
    assert parte.tipo == "Reu"
    assert parte.polo == "passivo"


# ---------------------------------------------------------------------------
# Testes: schemas gerais
# ---------------------------------------------------------------------------


def test_processo_e_sigiloso_property() -> None:
    """Propriedade e_sigiloso deve refletir nivel_sigilo corretamente."""
    from mcp_juridico_brasil.shared.schemas import Processo

    publico = Processo(numero_processo="123", tribunal="TJSP", nivel_sigilo=0)
    sigiloso = Processo(numero_processo="456", tribunal="TJSP", nivel_sigilo=1)

    assert not publico.e_sigiloso
    assert sigiloso.e_sigiloso


def test_movimentacao_sem_codigo() -> None:
    """Movimentacao pode ter codigo None (campo opcional)."""
    from mcp_juridico_brasil.shared.schemas import Movimentacao

    mov = Movimentacao(
        codigo=None,
        nome="Publicacao de Decisao",
        data_hora=datetime(2024, 1, 10, 14, 0, tzinfo=timezone.utc),
    )
    assert mov.codigo is None
    assert mov.nome == "Publicacao de Decisao"


def test_processo_model_dump_json_serializavel() -> None:
    """Processo.model_dump(mode='json') deve produzir estrutura com datetime como string."""
    from mcp_juridico_brasil.shared.schemas import Processo

    processo = Processo(
        numero_processo=NUMERO,
        tribunal="TJSP",
        nivel_sigilo=0,
        data_ajuizamento=datetime(2023, 3, 15, tzinfo=timezone.utc),
    )
    dados = processo.model_dump(mode="json")
    assert dados["numero_processo"] == NUMERO
    assert dados["nivel_sigilo"] == 0
    # No modo JSON, datetime e serializado como string ISO
    assert isinstance(dados["data_ajuizamento"], str)
