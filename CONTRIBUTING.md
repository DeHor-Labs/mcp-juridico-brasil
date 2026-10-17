# Contribuindo com o mcp-juridico-brasil

Obrigado pelo interesse em contribuir! Este guia descreve como o projeto está organizado,
o fluxo de desenvolvimento com `uv` e as convenções que seguimos.

## Estrutura dos módulos

Cada domínio jurídico é um pacote Python independente dentro de `src/mcp_juridico_brasil/`:

```
src/mcp_juridico_brasil/
├── processual/          # consulta e histórico de processos via DataJud
│   ├── client.py        # cliente HTTP (httpx + tenacity) para a API DataJud CNJ
│   ├── schemas.py       # modelos Pydantic de request/response
│   └── tools.py         # funções MCP expostas via @mcp.tool()
├── monitoramento/       # resources de acompanhamento e alertas
│   ├── client.py
│   ├── schemas.py
│   └── tools.py
├── prazo/               # cálculo de prazo processual com calendário de feriados
│   ├── client.py
│   ├── schemas.py
│   └── tools.py
├── jurisprudencia/      # busca de jurisprudência nos tribunais
│   ├── client.py
│   ├── schemas.py
│   └── tools.py
├── legislacao/          # textos consolidados de legislação
│   ├── client.py
│   ├── schemas.py
│   └── tools.py
├── calculos/            # utilitários de cálculo (correção monetária, custas, etc.)
│   ├── client.py
│   ├── schemas.py
│   └── tools.py
└── core/                # configuração, logging, rate-limit, exceções
    └── ...
```

### Convenção dos três arquivos

| Arquivo | Responsabilidade |
|---------|-----------------|
| `client.py` | Comunicação com a API DataJud ou outra fonte externa. Usa `httpx.AsyncClient`, `tenacity` para retry e `aiolimiter` para rate-limit. |
| `schemas.py` | Modelos Pydantic que representam os dados recebidos e retornados. Inclui validators e exemplos de `model_config`. |
| `tools.py` | Funções decoradas com `@mcp.tool()` que compõem a interface pública do servidor. Cada função deve ter docstring clara e tipos anotados. |

## Fonte de dados principal: DataJud CNJ

A API DataJud do Conselho Nacional de Justiça fornece acesso a dados processuais dos
tribunais brasileiros; o servidor cadastra 92 siglas (STF, STJ, TJs, TRFs, TRTs, etc.). Toda consulta processual
deve passar pelo cliente em `processual/client.py` ou pelo módulo correspondente.

Documentação oficial: https://datajud-wiki.cnj.jus.br/

## Ambiente de desenvolvimento

Este projeto usa [`uv`](https://docs.astral.sh/uv/) como gerenciador de pacotes e
ambiente virtual.

### Configuração inicial

```bash
# Clone o repositório
git clone https://github.com/DeHor-Labs/mcp-juridico-brasil.git
cd mcp-juridico-brasil

# Instala dependências (cria .venv automaticamente)
uv sync

# Ativa o ambiente (uv run faz isso automaticamente em cada comando)
source .venv/bin/activate
```

### Executar testes

```bash
uv run pytest tests/ -v
uv run pytest tests/ --cov=src --cov-report=term-missing
```

### Lint e formatação

```bash
uv run ruff check src tests
uv run ruff format --check src tests

# Corrigir automaticamente
uv run ruff check --fix src tests
uv run ruff format src tests
```

### Verificação de tipos

```bash
uv run mypy src
```

### Atalho via Makefile

```bash
make check          # lint + typecheck
make test           # testes
make build          # empacota o wheel
```

## Fluxo de contribuição

1. **Abra uma issue** descrevendo o bug ou a funcionalidade antes de abrir um PR.
2. **Crie uma branch** a partir de `main`:
   ```bash
   git checkout -b feat/nome-da-feature
   ```
3. **Implemente** seguindo a convenção `client.py + schemas.py + tools.py`.
4. **Adicione testes** em `tests/` cobrindo os novos comportamentos.
5. **Rode** `make check` e `make test` e garanta que tudo passa.
6. **Abra o PR** com título descritivo e preencha o template.

## Convenções de commit

Seguimos [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: consulta por número CNJ no módulo processual
fix: tratamento de timeout na API DataJud
docs: exemplos de uso no README
test: cobertura do cálculo de prazo em recesso
```

## Código de conduta

Este projeto adota o [Contributor Covenant](https://www.contributor-covenant.org/).
Seja respeitoso e construtivo nas interações.

## Dúvidas

Abra uma [Discussion](https://github.com/DeHor-Labs/mcp-juridico-brasil/discussions)
ou envie um e-mail para nikolasdehor79@gmail.com.
