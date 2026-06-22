# MCP Juridico Brasil

Plataforma de dados juridicos brasileiros exposta via Model Context Protocol (MCP),
organizada em **modulos por dominio**. O primeiro modulo entregue e o de
**acompanhamento processual** - consulta, monitoramento e alertas de prazo em
91 tribunais via [DataJud CNJ](https://datajud-wiki.cnj.jus.br/api-publica/).

Os proximos modulos (Jurisprudencia, Legislacao, Diarios Oficiais, Calculos Juridicos)
entram no roadmap apos a conclusao do modulo Processual, cada um como pacote plugavel
independente. Ver [docs/PLANO-E2E.md](docs/PLANO-E2E.md) para a visao completa.

**Autor:** Nikolas de Hor - nikolasdehor79@gmail.com
**Status:** Pre-alpha (Fase 0 - scaffold do modulo Processual)
**Licenca:** MIT

> **AVISO LEGAL:** Este software e destinado exclusivamente ao uso por advogados e
> profissionais do direito para acompanhamento de processos de seus clientes.
> Nao constitui consultoria juridica. A analise final e a orientacao ao cliente
> sao de responsabilidade exclusiva do advogado habilitado (OAB Rec. 001/2024).

---

## O que faz (modulo Processual - MVP)

| Tool | Descricao |
|---|---|
| `buscar_processo_por_numero` | Consulta completa de processo pelo numero CNJ em 91 tribunais |
| `listar_movimentacoes` | Historico de andamentos com codigo TPU e data |
| `resumir_andamento` | Retorna dados + instrucao para o LLM gerar resumo em linguagem natural |
| `monitorar_processo` | Verifica se houve atualizacao desde uma data (polling DataJud) |
| `calcular_proximo_prazo` | Estimativa de prazo processual a partir da ultima movimentacao |
| `listar_tribunais` | Lista as 91 siglas de tribunais suportados |

## Cobertura

91 tribunais via API publica DataJud (CNJ):
- Tribunais superiores: STF, STJ, TST, TSE, STM
- Tribunais Regionais Federais: TRF1 a TRF6
- Tribunais Regionais do Trabalho: TRT1 a TRT24
- Tribunais de Justica estaduais e DF (27)
- Tribunais Regionais Eleitorais e Militares Estaduais

**Limitacao importante:** O DataJud tem defasagem de T+1 a T+7 dias dependendo do tribunal. Para monitoramento de prazos criticos em producao, configure um provider comercial (Judit, Escavador) na Fase 3.

## Instalacao

### Via uvx (recomendado)

```bash
uvx mcp-juridico-brasil
```

### Via pip

```bash
pip install mcp-juridico-brasil
mcp-juridico-brasil
```

### Configuracao no Claude Desktop

Adicione ao `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "juridico-brasil": {
      "command": "uvx",
      "args": ["mcp-juridico-brasil"],
      "env": {
        "DATAJUD_API_KEY": "sua-chave-aqui"
      }
    }
  }
}
```

A chave publica padrao ja esta embutida no codigo. Atualize se o CNJ rotacionar.
Consulte sempre: https://datajud-wiki.cnj.jus.br/api-publica/acesso/

## Desenvolvimento local

Requer Python 3.10+ e [uv](https://github.com/astral-sh/uv).

```bash
git clone https://github.com/DeHor-Labs/mcp-juridico-brasil
cd mcp-juridico-brasil
uv sync --extra dev
cp .env.example .env
make test
```

## Roadmap

### Modulo Processual (Fases 0-4)

| Fase | Status | Descricao |
|---|---|---|
| Fase 0 | Em andamento | Scaffold, estrutura, CI |
| Fase 1 | Planejado | MVP DataJud - todas as tools funcionais |
| Fase 2 | Planejado | Monitoramento, alertas, calendario forense |
| Fase 3 | Planejado | Provider comercial com webhook push |
| Fase 4 | Planejado | Intimacoes DJe (Domicilio Judicial Eletronico) |

### Modulos futuros (pos-Fase 4)

| Modulo | Fontes candidatas |
|---|---|
| Jurisprudencia | STF, STJ, TST, TJs (portais e APIs) |
| Diarios Oficiais | DJEN/CNJ, Querido Diario (Open Knowledge Brasil) |
| Legislacao | LexML, portal Planalto, DOU |
| Calculos Juridicos | Tabelas CNJ, IPCA/SELIC Banco Central |

Cada modulo futuro entra com seu proprio plano, versionamento e fontes validadas.

Ver [docs/PLANO-E2E.md](docs/PLANO-E2E.md) para o plano completo, incluindo a visao de plataforma modular.

## Privacidade e LGPD

- Processos em segredo de justica sao **bloqueados** com erro explicito (nao ha fallback nem tentativa de contornar o sigilo)
- Nenhum CPF/CNPJ de partes e persistido internamente
- Dados sensiveis (saude, origem etnica, orientacao sexual) nao sao indexados
- Politica de retencao: somente enquanto necessario ao proposito declarado
- Fundamento: LGPD (Lei 13.709/2018) e Resolucao CNJ 647/2025

## Irmao deste projeto

[MCP Fiscal Brasil](https://github.com/DeHor-Labs/mcp-fiscal-brasil) - 41 ferramentas fiscais brasileiras (CNPJ, NF-e, IBS/CBS, Simples Nacional).

## Contribuicao

Issues e PRs sao bem-vindos. Ver [CONTRIBUTING.md](CONTRIBUTING.md) (a criar na Fase 1).
