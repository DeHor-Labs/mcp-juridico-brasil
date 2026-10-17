<!-- mcp-name: io.github.DeHor-Labs/mcp-juridico-brasil -->

<p align="center">
  <img src="https://raw.githubusercontent.com/DeHor-Labs/mcp-juridico-brasil/main/assets/banner.svg" width="800" alt="MCP Juridico Brasil">
</p>

<p align="center">
  <strong>Conecte qualquer assistente de IA ao DataJud CNJ - com 92 siglas de tribunais cadastradas, cálculo de prazos, monitoramento de processos e conformidade com o CPC.</strong>
</p>

<p align="center">
  <a href="https://juridico.dehor.dev"><strong>juridico.dehor.dev</strong></a>: página do projeto, com exemplos, instalação e perguntas frequentes
</p>

<p align="center">
  <a href="https://pypi.org/project/mcp-juridico-brasil/"><img src="https://img.shields.io/pypi/v/mcp-juridico-brasil?color=003087&label=PyPI" alt="PyPI version"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-1a7a4a?logo=python&logoColor=white" alt="Python 3.10+"></a>
  <a href="https://github.com/DeHor-Labs/mcp-juridico-brasil/actions/workflows/ci.yml"><img src="https://github.com/DeHor-Labs/mcp-juridico-brasil/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/licenca-MIT-4fc3f7?labelColor=001f5b" alt="Licença MIT"></a>
  <a href="https://modelcontextprotocol.io"><img src="https://img.shields.io/badge/MCP-compatível-7c3aed" alt="MCP Compatível"></a>
  <img src="https://img.shields.io/github/stars/DeHor-Labs/mcp-juridico-brasil?style=flat&color=003087" alt="Stars">
  <img src="https://img.shields.io/github/issues/DeHor-Labs/mcp-juridico-brasil?color=4fc3f7&labelColor=001f5b" alt="Issues">
</p>

<p align="center">
  <a href="#o-que-é">O que é</a> ·
  <a href="#ferramentas-disponíveis">Ferramentas</a> ·
  <a href="#instalação">Instalação</a> ·
  <a href="#configuração-por-cliente-mcp">Configuração</a> ·
  <a href="#roadmap">Roadmap</a> ·
  <a href="#contribuindo">Contribuindo</a>
</p>

---

## O que é

`mcp-juridico-brasil` conecta assistentes de IA, escritórios de advocacia e sistemas de gestão processual ao **DataJud CNJ** - a base unificada de dados judiciais do Conselho Nacional de Justiça - com **92 siglas de tribunais cadastradas** em todas as justiças (Federal, Estadual, do Trabalho, Militar, Eleitoral e Superior). Estar cadastrado não garante que o DataJud tenha dados daquele tribunal: o volume de dados depende do que cada tribunal envia ao CNJ.

O servidor não é um catálogo genérico de dados públicos. A proposta é ser uma vertical processual: transformar consultas judiciais fragmentadas em **tools seguras, componíveis e prontas para agentes** - com cálculo de prazos em dias úteis conforme o CPC, monitoramento de andamentos por consulta e acesso ao Domicílio Judicial Eletrônico.

---

## Ferramentas disponíveis

O servidor registra **9 tools** e **1 resource** (ver `src/mcp_juridico_brasil/server.py`).

### Consulta e monitoramento de processos

| Ferramenta | Descrição | Fonte |
|------------|-----------|-------|
| `buscar_processo_por_numero` | Consulta completa de processo pelo número CNJ (NNNNNNN-DD.AAAA.J.TT.OOOO) | DataJud CNJ |
| `listar_movimentacoes` | Histórico de andamentos processuais com filtro por data | DataJud CNJ |
| `resumir_andamento` | Dados do processo mais instrução de resumo para o modelo de linguagem | DataJud CNJ |
| `monitorar_processo` | Informa se houve atualização desde uma data e a data da última atualização (polling, sem gravar snapshot) | DataJud CNJ |
| `listar_processos_monitorados` | Lista processos com snapshot gravado na sessão. Nesta versão nenhuma tool de consulta grava snapshot, então a lista vem vazia | Memória local |

### Cálculo de prazos processuais

| Ferramenta | Descrição | Referência |
|------------|-----------|------------|
| `calcular_proximo_prazo` | Cálculo de prazo em dias úteis com recesso forense e feriados nacionais (art. 219, 220 e 224 CPC). Feriados estaduais só entram com `uf` informada | Offline com `data_intimacao_iso`; sem ela, consulta o DataJud para usar a última movimentação |

### Referência de tribunais

| Ferramenta | Descrição | Fonte |
|------------|-----------|-------|
| `listar_tribunais` | Lista as 92 siglas cadastradas no servidor (Portaria CNJ 160/2020) | Offline |

### Domicílio Judicial Eletrônico (opcional)

Exigem credenciais próprias do DJe (`DJE_CLIENT_ID`, `DJE_CLIENT_SECRET`, `DJE_BEHALF_OF_CPF`).

| Ferramenta | Descrição | Fonte |
|------------|-----------|-------|
| `listar_intimacoes` | Lista comunicações recebidas no DJe. Somente leitura; conteúdo de intimações sigilosas é suprimido | DJe (API Comunica) |
| `confirmar_leitura_intimacao` | Confirma leitura de intimação. **Tem efeito jurídico real e inicia prazo.** Funciona em dry-run por padrão e só confirma com `confirmar=True` e `DJE_PERMITIR_CONFIRMACAO_LEITURA=true` | DJe (API Comunica) |

### Resource MCP

| Resource | Descrição |
|----------|-----------|
| `processo://{numero}/snapshot` | Lê o snapshot gravado de um processo, se existir. Como `buscar_processo_por_numero` e `monitorar_processo` não gravam snapshot, nesta versão ele responde que não há snapshot disponível |

---

## Instalação

A forma mais simples, sem instalar nada permanentemente:

```bash
uvx mcp-juridico-brasil
```

> **O que é `uvx`?** É o gerenciador de ferramentas do [uv](https://docs.astral.sh/uv/), que baixa e executa pacotes Python em ambiente isolado, sem poluir seu sistema. Se ainda não tem o uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`

> **Mantendo atualizado:** use `uvx mcp-juridico-brasil@latest` ou `uvx --refresh mcp-juridico-brasil` para forçar a versão mais recente do PyPI.

### Instalação permanente (alternativa)

```bash
# via pip
pip install mcp-juridico-brasil

# via uv (recomendado para projetos Python)
uv add mcp-juridico-brasil
```

### A partir do código-fonte

```bash
git clone https://github.com/DeHor-Labs/mcp-juridico-brasil.git
cd mcp-juridico-brasil
uv sync
```

---

## Configuração por cliente MCP

Cole o trecho abaixo no arquivo de configuração do seu cliente. A variável `DATAJUD_API_KEY` é opcional: por padrão o servidor usa a chave pública vigente divulgada pelo CNJ em [datajud-wiki.cnj.jus.br](https://datajud-wiki.cnj.jus.br/api-publica/acesso/). Como o CNJ pode trocá-la a qualquer momento, use a variável para substituí-la quando necessário.

### Claude Desktop

Edite `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) ou `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

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

Reinicie o Claude Desktop. As ferramentas jurídicas aparecem automaticamente.

### Claude Code (CLI)

```bash
claude mcp add juridico-brasil -- uvx mcp-juridico-brasil
```

Para incluir a chave de API:

```bash
DATAJUD_API_KEY=sua-chave-aqui claude mcp add juridico-brasil -- uvx mcp-juridico-brasil
```

### Cursor / `.mcp.json`

Crie ou edite `.cursor/mcp.json` (ou `.mcp.json` na raiz do projeto):

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

### VS Code + Continue

Adicione ao `settings.json`:

```json
{
  "continue.mcpServers": {
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

---

## Variáveis de ambiente

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `DATAJUD_API_KEY` | Substitui a chave pública padrão do DataJud CNJ | chave pública vigente do CNJ |
| `JURIDICO_LOG_LEVEL` | Nível de log: `DEBUG`, `INFO`, `WARNING` | `INFO` |
| `JURIDICO_SNAPSHOT_DIR` | Diretório para persistir em arquivo snapshots gravados. Nesta versão as tools de consulta não gravam snapshot | memória |
| `JURIDICO_HTTP_TIMEOUT` | Timeout em segundos para chamadas HTTP ao DataJud | `30` |

---

## Arquitetura

```
Claude / GPT / Cursor / qualquer cliente MCP
              |
              | Model Context Protocol (stdio)
              v
    mcp-juridico-brasil
              |
    +---------+---------+-----------+----------+
    |         |         |           |          |
 Processos  Movim.   Resumo    Monitoram.  Prazos
    |         |         |           |          |
    v         v         v           v          v
 DataJud   DataJud   DataJud    DataJud   Calendario
  CNJ        CNJ       CNJ        CNJ      forense
                                           offline
              |
              v
   92 siglas de tribunais
  (Federal, Estadual, Trabalho,
   Militar, Eleitoral, Superior)
```

**Fontes de dados:**
- [DataJud CNJ](https://datajud-wiki.cnj.jus.br/) - base unificada de dados judiciais (Portaria CNJ 160/2020)
- Calendário forense nacional e estadual - processado offline para cálculo de prazos (CPC art. 219/220/224)

---

## Roadmap

- [x] **v0.1.x** - Busca de processo, listagem de movimentações, resumo de andamento e listagem de tribunais
- [x] **v0.2.x** - Monitoramento por consulta, cálculo de prazos em dias úteis (CPC), resource MCP por processo
- [ ] **v0.3.x** - Webhook push de atualizações, persistência em banco de dados e alertas por prazo
- [x] **v0.4.x (parcial)** - Intimações via Domicílio Judicial Eletrônico (DJe): listagem e confirmação de leitura com gate duplo
- [ ] **v0.4.x** - Parsing de publicações e extração estruturada
- [ ] **v1.0.0** - Suite processual completa com auditoria LGPD, contratos de API estáveis e cobertura ampliada

---

## Privacidade e LGPD

> **Atenção:** as tools de consulta processual acessam exclusivamente dados públicos disponibilizados pelo DataJud CNJ (Resolução CNJ 331/2020); processos em **segredo de justiça** não são retornados por essa API. As tools opcionais do DJe são diferentes: com credenciais do próprio advogado, acessam comunicações processuais não públicas recebidas no Domicílio Judicial Eletrônico, com o conteúdo de intimações sigilosas suprimido, e `confirmar_leitura_intimacao` pode produzir efeito jurídico. Nenhum dado processual é armazenado fora do ambiente local do usuário, e nesta versão as tools de consulta não gravam os resultados em disco. O uso das ferramentas é de responsabilidade do profissional habilitado, em conformidade com a LGPD (Lei 13.709/2018), a Resolução CNJ 647/2025 e a OAB Recomendação 001/2024. Estas ferramentas não constituem consultoria jurídica.

---

## Contribuindo

Contribuições são bem-vindas!

```bash
# 1. Clone o repositório ou seu fork
git clone https://github.com/DeHor-Labs/mcp-juridico-brasil.git
cd mcp-juridico-brasil

# 2. Instale as dependências de desenvolvimento
uv sync

# 3. Crie sua branch
git checkout -b feature/meu-recurso

# 4. Implemente, teste e verifique
pytest
ruff check src/
mypy src/

# 5. Abra um Pull Request
```

Veja as [issues abertas](https://github.com/DeHor-Labs/mcp-juridico-brasil/issues) - especialmente as marcadas com `good first issue`.

Cada módulo segue o padrão `client.py` + `schemas.py` + `tools.py`, tornando simples adicionar novos módulos processuais.

---

## Projeto irmão

Este servidor faz par com o **MCP Fiscal Brasil**, que conecta IAs ao sistema fiscal brasileiro (NF-e, SPED, CNPJ, Simples Nacional, Reforma Tributária 2026):

[github.com/DeHor-Labs/mcp-fiscal-brasil](https://github.com/DeHor-Labs/mcp-fiscal-brasil)

---

## Licença

MIT - veja [LICENSE](LICENSE) para detalhes.

---

<p align="center">
  Feito com dedicação para o Judiciário brasileiro
  <br>
  <sub>Conectando inteligência artificial aos tribunais do sistema de justiça nacional</sub>
</p>
