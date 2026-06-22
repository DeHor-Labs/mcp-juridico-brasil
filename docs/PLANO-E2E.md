# Plano E2E - MCP Juridico Brasil

**Autor:** Nikolas de Hor - nikolasdehor79@gmail.com
**Data:** junho de 2026
**Versao do plano:** 1.0

---

## Visao de plataforma modular

O **MCP Juridico Brasil** e uma plataforma de dados juridicos brasileiros exposta via
Model Context Protocol (MCP), organizada em **modulos por dominio**. Cada modulo
e um conjunto coeso de tools, schemas e providers que cobre uma fatia especifica
do universo juridico. Os modulos sao plugaveis - cada um pode ser evoluido,
substituido ou monetizado de forma independente.

### Modulo Processual - primeiro modulo (MVP atual)

O modulo Processual e o que as **Fases 0 a 4** deste plano entregam. Ele cobre:

- Consulta e acompanhamento de processos judiciais em 91 tribunais via DataJud
- Listagem de movimentacoes com codigos TPU
- Monitoramento por polling (Fase 1) e webhook (Fase 3)
- Calculo de prazos e calendario forense (Fase 2)
- Intimacoes via Domicilio Judicial Eletronico - DJe (Fase 4)

Fonte de dados primaria: **API publica DataJud do CNJ** (gratuita, sem cadastro).

### Modulos futuros plugaveis

Os modulos abaixo entram no roadmap apos a conclusao da Fase 4. A fonte de dados
de cada um sera validada na fase de planejamento do respectivo modulo.

| Modulo | Descricao | Fontes candidatas (a validar na fase do modulo) |
|---|---|---|
| **Jurisprudencia** | Decisoes, sumulas e precedentes qualificados | Portais e APIs de STF, STJ, TST e TJs; DJe/PDPJ |
| **Legislacao** | Leis, decretos, normas e regulamentacoes | LexML (lexml.gov.br), portal Planalto, DOU |
| **Diarios Oficiais** | Publicacoes e intimacoes em diarios eletronicos | DJEN/CNJ, Querido Diario (Open Knowledge Brasil) |
| **Calculos Juridicos** | Correcao monetaria, juros legais e prazos processuais | TJSP-JEC, tabelas do CNJ, IPCA/SELIC Banco Central |

### Como a arquitetura suporta a expansao modular

A arquitetura escolhida nas Fases 0-4 foi desenhada para acomodar novos modulos
sem quebrar o que ja existe:

- **Pacotes irmaos por dominio:** cada modulo futuro vira um pacote Python ao lado
  de `src/mcp_juridico_brasil/processo/`, `movimentacoes/` etc., seguindo a mesma
  convencao de diretorios e sem acoplar ao modulo Processual.
- **Provider abstrato generalizavel:** o `ProcessoProvider` (ABC) e o padrao a ser
  replicado em cada modulo - um `JurisprudenciaProvider`, um `LegislacaoProvider`,
  etc. O padrao Strategy ja esta no codigo; basta criar novas implementacoes concretas.
- **Tools agrupadas por modulo:** cada modulo registra suas proprias tools no
  `server.py` via decorador `@app.tool()`, mantendo o namespace organizado e
  permitindo ativar ou desativar grupos de tools por configuracao.
- **Schemas Pydantic por dominio:** cada modulo define seus proprios schemas em
  `shared/schemas_<dominio>.py`, sem poluir os schemas do modulo Processual.

---

## 1. Stack e Justificativa

### Escolha: Python 3.10+ com FastMCP

O MCP Juridico Brasil adota exatamente a mesma stack do MCP Fiscal Brasil
(`mcp-fiscal-brasil`), seu projeto irmao:

| Componente | Escolha | Razao |
|---|---|---|
| Runtime | Python 3.10+ | Compatibilidade com FastMCP, ecossistema data/legal robusto |
| Framework MCP | fastmcp >= 3.2.0 | Mesma versao do MCP Fiscal; decorator `@app.tool()` simples |
| HTTP async | httpx | Cliente async com retry nativo via tenacity |
| Validacao | pydantic v2 | Schemas tipados, serialization JSON built-in |
| Rate limiting | aiolimiter | Controla rajadas contra a API DataJud |
| Cache TTL | cachetools.TTLCache | Evita requisicoes repetidas ao DataJud |
| Retry | tenacity | Exponential backoff para erros 429/5xx |
| Logging | structlog | Logs estruturados (mesmo padrao do MCP Fiscal) |
| Config | pydantic-settings | .env -> variaveis de ambiente -> defaults |
| CLI | typer | Consistente com o MCP Fiscal |
| Linter | ruff | Identico ao MCP Fiscal |
| Typecheck | mypy (strict) | Identico ao MCP Fiscal |
| Testes | pytest + pytest-asyncio | Identico ao MCP Fiscal |
| Build | hatchling | Identico ao MCP Fiscal |
| Package manager | uv | Identico ao MCP Fiscal |
| CI | GitHub Actions (matrix 3.10-3.13) | Identico ao MCP Fiscal |

**Por que nao TypeScript/Node?**
O MCP Fiscal usa Python. Manter a mesma stack elimina custo cognitivo de troca
de contexto, permite reuso de padroes de HTTPClient, config, erros e CI, e
o ecossistema Python tem bibliotecas maduras para processamento juridico
(datas, calendarios, NLP em pt-BR). O SDK TypeScript do MCP seria igualmente
valido tecnicamente, mas a coerencia com o projeto irmao e o fator decisivo.

---

## 2. Arquitetura do MCP

### 2.1 Diagrama de camadas

```
Claude / qualquer cliente MCP
        |
        | stdio ou HTTP streamable
        v
+----------------------------+
|  server.py (FastMCP)       |  <- registro de tools, instrucoes globais
+----------------------------+
|  Tools (por modulo)        |
|  - processo/tools.py       |  buscar_processo_por_numero
|  - movimentacoes/tools.py  |  listar_movimentacoes
|  - resumo/tools.py         |  resumir_andamento
|  - monitoramento/tools.py  |  monitorar_processo
|  - prazo/tools.py          |  calcular_proximo_prazo
|  - server.py               |  listar_tribunais (inline)
+----------------------------+
|  ProcessoProvider (ABC)    |  <- interface abstrata
+----------------------------+
|  DataJudProvider           |  Fase 1 - gratuito, polling
|  ComercialProvider         |  Fase 3 - pago, webhook push
|  DJeProvider               |  Fase 4 - intimacoes proprias
+----------------------------+
|  DataJudClient             |  Elasticsearch DSL -> DataJud CNJ
|  HTTPClient (core)         |  retry + rate limit + cache
+----------------------------+
|  shared/schemas.py         |  Processo, Movimentacao, Parte, ...
|  shared/validators.py      |  validar_numero_cnj, normalizar, ...
|  datajud/tribunais.py      |  mapa sigla -> indice DataJud (91 trib.)
+----------------------------+
```

### 2.2 Tools expostas no MVP (Fase 1)

| Tool | Input | Output | Observacao |
|---|---|---|---|
| `buscar_processo_por_numero` | numero_processo, tribunal? | dados completos do processo | Verifica sigilo antes de retornar |
| `listar_movimentacoes` | numero_processo, tribunal, limite? | lista de movimentacoes TPU | Ordenado do mais recente |
| `resumir_andamento` | numero_processo, tribunal? | dados + instrucao de resumo | Resumo semantico fica no modelo |
| `monitorar_processo` | numero_processo, tribunal, desde_iso | bool houve_atualizacao | Polling; Fase 3 troca por push |
| `calcular_proximo_prazo` | numero_processo, tribunal, tipo_ato? | estimativa de prazo | Stub em dias corridos; Fase 2 expande |
| `listar_tribunais` | (nenhum) | lista de siglas | 91 tribunais suportados |

### 2.3 Resources (Fase 1)

Nenhum resource MCP persistente no MVP. Fase 2 adiciona:
- `resource://processo/{numero}` - snapshot cacheado de processo monitorado
- `resource://tribunal/{sigla}/status` - status de atualizacao do indice DataJud

### 2.4 Design do provider abstrato

```python
class ProcessoProvider(ABC):
    async def buscar_processo(numero, tribunal?) -> Processo: ...
    async def listar_movimentacoes(numero, tribunal, limite) -> list[Movimentacao]: ...
    async def verificar_atualizacao(numero, tribunal, desde_iso) -> bool: ...
```

`DataJudProvider` e a implementacao concreta do MVP. Em Fase 3, o servidor
detecta `JURIDICO_PROVIDER_COMERCIAL` no ambiente e instancia `ComercialProvider`
que delega ao Judit, Escavador ou TrackJud via seus SDKs/APIs REST. As tools
nao mudam - apenas o provider injetado muda. Isso e o padrao Strategy aplicado
ao acesso a dados.

---

## 3. Fases de Entrega

### Fase 0 - Scaffold (atual)

**Escopo:**
- Estrutura de diretorios espelhando o MCP Fiscal
- pyproject.toml, server.json, smithery.yaml, .env.example
- Hierarquia de erros com `JuridicoSigiloError` como cidadao de primeira classe
- HTTPClient com retry/rate limit/cache (reuso de padroes do MCP Fiscal)
- Schemas Pydantic: Processo, Movimentacao, Parte, OrgaoJulgador
- Validador de numero CNJ (regex NNNNNNN-DD.AAAA.J.TT.OOOO)
- Mapeamento de 91 tribunais DataJud
- Stubs de todas as tools com docstrings e disclaimers LGPD/OAB
- Interface `ProcessoProvider` + `DataJudProvider` (parcialmente implementado)
- CI GitHub Actions (lint, typecheck, test matrix 3.10-3.13)
- Testes unitarios de validators

**Criterios de aceite:**
- `make lint` passa sem erros
- `make typecheck` passa
- `make test` executa e os testes de validators passam
- Estrutura espelha o MCP Fiscal (revisao manual)

**Estimativa:** 1-2 dias (scaffold ja criado)

---

### Fase 1 - MVP DataJud

**Escopo:**
- `DataJudClient.buscar_por_numero` funcionando contra a API real
- `DataJudClient.buscar_por_numero_multiplos_tribunais` com iteracao por tribunal
- `DataJudClient.listar_movimentacoes` com ordenacao e limite
- `DataJudProvider` completo implementando `ProcessoProvider`
- Verificacao de `nivelSigilo > 0` integrada ao parsing (bloquear, nao cachelar)
- Todas as 6 tools retornando dados reais via DataJud
- Testes de integracao com `respx` (mock do DataJud) para os 4 cenarios:
  processo publico, processo sigiloso, processo nao encontrado, erro de API
- Exemplo de uso em `examples/consulta_basica.py`
- Cobertura de testes >= 80%
- Publicacao no PyPI (versao 0.1.0)

**Criterios de aceite:**
- `buscar_processo_por_numero("0001234-56.2023.8.26.0100", "TJSP")` retorna dados reais
- Processo com `nivelSigilo=1` lanca `JuridicoSigiloError` com mensagem clara
- Processo inexistente lanca `JuridicoNotFoundError`
- `listar_tribunais()` retorna exatamente 91 entradas
- CI verde em Python 3.10, 3.11, 3.12, 3.13
- `uvx mcp-juridico-brasil` funciona no Claude Desktop

**Estimativa:** 5-7 dias

---

### Fase 2 - Monitoramento e Alertas de Prazo

**Escopo:**
- `monitorar_processo` com polling agendavel (retorna delta de movimentacoes)
- `calcular_proximo_prazo` completo:
  - Tabela de prazos CPC (art. 219 e seguintes) por tipo de ato
  - Calendario forense por UF (feriados nacionais + estaduais)
  - Deteccao de suspensao de prazo (recesso forense jan/jul)
  - Diferenciacao entre dias uteis e corridos por tipo de prazo
- Resource MCP `processo/{numero}/snapshot` para armazenar estado anterior
- Comparacao de snapshots para identificar novas movimentacoes
- Tool `listar_processos_monitorados` (estado em memoria por sessao)
- Testes de calendario com casos de borda (virada de ano, feriados moveis)

**Criterios de aceite:**
- Prazo de Embargos de Declaracao (5 dias uteis) calculado corretamente
  considerando sabados, domingos e feriados nacionais
- Recesso forense (20 dez a 20 jan) suspende contagem corretamente
- `monitorar_processo` retorna apenas movimentacoes novas desde o ultimo check
- Cobertura de testes >= 80%

**Estimativa:** 10-14 dias

---

### Fase 3 - Push em Tempo Real via Provider Comercial

**Escopo:**
- Interface `WebhookProvider` (extensao de `ProcessoProvider`)
- `ComercialProvider` configuravel via env: Judit, Escavador ou TrackJud
- Mecanismo de registro de webhook: tool `registrar_webhook_processo`
- Recepcao de notificacao push e traducao para o schema interno
- Fallback automatico para DataJud se o provider comercial estiver indisponivel
- Documentacao de configuracao de cada provider suportado
- Preco estimado por consulta documentado no README por provider

**Criterios de aceite:**
- Com `JURIDICO_PROVIDER_COMERCIAL=judit` e chave valida, `monitorar_processo`
  retorna notificacao em < 2 horas apos movimentacao (SLA Judit)
- Sem provider configurado, todas as tools funcionam normalmente via DataJud
- Troca de provider nao exige alteracao no codigo das tools
- Cobertura de testes >= 80% (mocks dos providers comerciais)

**Estimativa:** 10-15 dias (depende de acesso a sandbox dos providers)

---

### Fase 4 - Intimacoes via Domicilio Judicial Eletronico

**Escopo:**
- `DJeProvider` implementando acesso a API Comunica (DJe/PDPJ)
- Autenticacao OAuth2 com `client_credentials` via GeCli
- Tool `listar_intimacoes`: lista comunicacoes pendentes do CNPJ cadastrado
- Tool `marcar_intimacao_como_lida`: PUT que perfaz a ciencia oficial
- Tool `buscar_intimacoes_por_processo`: filtra por numero CNJ
- Aviso claro: `marcar_intimacao_como_lida` inicia contagem de prazo oficial
- Logs de auditoria imutaveis para cada leitura (header `On-behalf-Of`)
- Documentacao de credenciamento no portal DJe (exige certificado digital)

**Criterios de aceite:**
- `listar_intimacoes` retorna comunicacoes reais do CNPJ configurado
- `marcar_intimacao_como_lida` retorna confirmacao e timestamp da ciencia
- Tentativa de acessar intimacao de CNPJ diferente do configurado retorna erro
- Aviso de prazo exibido proeminentemente antes de qualquer marcacao como lida
- Logs de auditoria persistidos em arquivo local com hash de integridade

**Riscos especificos Fase 4:**
- O portal DJe exige credenciamento com certificado digital ICP-Brasil
  (e-CNPJ ou e-CPF) - nao pode ser automatizado completamente
- A API OAuth2 do DJe teve migracao obrigatoria ate 31/03/2026;
  verificar se a versao atual e compativel antes de implementar
- Marcar como lida via API tem efeito juridico real (inicia prazo);
  exigir confirmacao explicita do usuario antes de executar

**Estimativa:** 15-20 dias

---

### Pos-Fase 4 - Abertura dos proximos modulos

Com o modulo Processual maduro e publicado, os proximos modulos entram em
planejamento seguindo o mesmo ciclo: definicao de fontes, scaffold, MVP, expansao.

Ordem tentativa (sujeita a validacao de demanda):

1. **Jurisprudencia** - alta sinergia com o modulo Processual (processos citam acórdaos)
2. **Diarios Oficiais** - complemento natural ao modulo DJe da Fase 4
3. **Legislacao** - base de referencia para os demais modulos
4. **Calculos Juridicos** - modulo transversal, pode ser entregue em paralelo com qualquer outro

Cada modulo tera seu proprio PLANO-E2E, versionamento de API e politica de
compatibilidade. Modulos existentes nao serao quebrados por modulos novos.

---

## 4. Riscos e Mitigacoes (como Requisitos de Design)

### 4.1 Segredo de justica (CRITICO)

**Risco:** Expor dados de processo sigiloso para usuario nao autorizado.

**Mitigacao embutida no design:**
- `JuridicoSigiloError` e verificado ANTES de qualquer retorno de dados
- Processos com `nivelSigilo > 0` nao sao cacheados (nem no TTLCache)
- Logs de processos sigilosos registram apenas numero e nivel, nunca conteudo
- Nenhum fallback para "tentar outro provider" quando o DataJud bloqueia por sigilo
- Fundamento: art. 189 CPC + Portaria CNJ 160/2020 (DataJud filtra na origem)

**Implementacao:** `datajud/client.py` - metodo `_parse_processo` verifica
`nivelSigilo` antes de construir o objeto `Processo`. Qualquer valor > 0 lanca
`JuridicoSigiloError` imediatamente, sem retornar dados parciais.

### 4.2 LGPD - dados pessoais de partes (ALTO)

**Risco:** Tratar CPF/CNPJ de partes, dados de saude ou dados sensiveis
sem base legal adequada ou alem do necessario.

**Mitigacao embutida no design:**
- Schema `Parte` nao tem campo CPF/CNPJ (a API DataJud nao indexa por razoes de LGPD)
- Campos de dados sensiveis (saude, orientacao sexual, origem etnica) nao existem
  nos schemas - se estiverem nos complementos, nao sao indexados
- Retencao: dados em memoria apenas durante a sessao MCP ativa
- Nenhum banco de dados local ou cache persistente no MVP

**Base legal adotada:** art. 7, IX LGPD (legitimo interesse do advogado
no acompanhamento de processos de seus clientes) + art. 7, V (execucao
de contrato de servico com o advogado).

### 4.3 Resolucao CNJ 647/2025 - uso comercial do DataJud (ALTO)

**Risco:** Usar DataJud como base de produto comercial sem formalizacao
com o CNJ pode ser contestado. Art. 13 proibe redistribuicao de base replica.

**Mitigacao embutida no design:**
- Arquitetura "query on demand": nenhuma base replica e mantida localmente
- Cada consulta busca em tempo real na API DataJud
- Cache TTL curto (300s padrao) para uso normal, nao para replicacao
- Termos de uso do produto proibem exportacao em massa pelo usuario
- Recomendacao: formalizar relacionamento com CNJ via comunicacao oficial
  antes do lancamento publico (acao pre-Fase 1)

### 4.4 OAB - exercicio da advocacia / captacao indevida (ALTO)

**Risco:** Funcionalidade que configure consultoria juridica direta ou
captacao automatizada de clientela, vedada pelo CED OAB e
Provimento OAB 205/2021.

**Mitigacao embutida no design:**
- Disclaimer obrigatorio em TODAS as tools e no campo `instructions` do servidor
- `resumir_andamento` retorna dados + instrucao de resumo, nao "conselho juridico"
- Nenhuma tool envia mensagens a clientes finais ou terceiros
- Produto posicionado como ferramenta para o advogado, nunca para o cliente final
- Termos de uso do produto vederao uso direto por clientes sem intermediacao

### 4.5 Rotacao da chave DataJud pelo CNJ (MEDIO)

**Risco:** O CNJ pode rotacionar a APIKey publica sem aviso previo.

**Mitigacao:** Chave configuravel via `DATAJUD_API_KEY` no .env. Fallback
de erro explicito com link para a wiki do CNJ. SLA interno: readequar em 48h
apos notificacao de revogacao.

### 4.6 Defasagem DataJud em prazos criticos (MEDIO)

**Risco:** Advogado usa `calcular_proximo_prazo` baseado em movimentacao
desatualizada e perde o prazo real.

**Mitigacao embutida no design:**
- Aviso de defasagem em TODOS os retornos de prazo (campo `aviso` obrigatorio)
- `calcular_proximo_prazo` tem campo `limitacao` explicitando que e estimativa
- Documentacao orienta uso de provider comercial (Fase 3) para prazos criticos
- Disclaimer no README e nas instrucoes do servidor MCP

---

## 5. Posicionamento e Monetizacao

### 5.1 Modelo: core open-source + camada paga opcional

```
+------------------------------------------+
| CORE OPEN-SOURCE (MIT)                   |
| - DataJud (91 tribunais, polling)        |
| - Todas as 6 tools do MVP               |
| - Sem limite de processos locais         |
| - Sem cadastro ou API key propria        |
+------------------------------------------+
          |
          v
+------------------------------------------+
| CAMADA PAGA (futura - Fase 3+)           |
| - Provider comercial (webhook push)      |
| - Monitoramento continuo multi-processo  |
| - Alertas em tempo real                  |
| - Integracao DJe (intimacoes oficiais)   |
+------------------------------------------+
```

O modelo espelha o MCP Fiscal Brasil: funcionalidade basica gratuita e util
para o publico geral; camada paga para casos de uso profissional em escala.

### 5.2 Publico-alvo e proposta de valor

**Primario:** Advogado autonomo e escritorio pequeno (1-5 advogados)

- Dor principal: perda de prazo por nao monitorar DJe e portal do tribunal
- Proposta: consulta processual direto no Claude/assistente de IA sem
  sair do fluxo de trabalho. Sem login em portal, sem copiar/colar numero.
- Barreira de entrada: zero (open-source, sem cadastro, sem custo inicial)

**Secundario:** Desenvolvedor de legaltech

- Dor: construir integracao DataJud do zero para cada produto
- Proposta: provider abstraido, schemas Pydantic prontos, CI configurado,
  tratamento de sigilo e LGPD embutidos

### 5.3 Diferenciacao em relacao aos concorrentes

Os concorrentes diretos (Jusbrasil Pro, Juridiq, Astrea, ADVBOX) sao
plataformas SaaS com interface web propria. O MCP Juridico Brasil e
um provedor de dados para assistentes de IA - posicionamento complementar,
nao substituto. O advogado que ja usa Claude/Copilot/GPT no dia a dia
ganha acesso processual sem trocar de ferramenta.

### 5.4 Caminho para monetizacao (Fase 3+)

Opcoes a avaliar apos validacao do MVP:
1. **API key propria paga** para acesso ao provider comercial embutido
   (repassar custo do Judit/Escavador com margem)
2. **Plano mensal** para monitoramento continuo com webhook e alertas
   (R$ 29-49/mes para ate 100 processos monitorados)
3. **Plugin pago no Smithery/MCP Registry** para usuarios que nao querem
   configurar infraestrutura propria

Nao ha plano de cobrar pelo acesso ao DataJud (que e publico e gratuito).

---

## 6. Dependencias de Terceiros e Licencas

| Dependencia | Versao minima | Licenca | Uso |
|---|---|---|---|
| fastmcp | 3.2.0 | MIT | Framework MCP |
| httpx | 0.27.0 | BSD | HTTP async |
| pydantic | 2.0 | MIT | Schemas e validacao |
| pydantic-settings | 2.13.1 | MIT | Config via env |
| python-dateutil | 2.9.0 | Apache 2.0 | Parsing de datas |
| tenacity | 9.1.4 | Apache 2.0 | Retry com backoff |
| cachetools | 7.0.5 | MIT | Cache TTL |
| aiolimiter | 1.2.1 | MIT | Rate limiting |
| structlog | 25.5.0 | MIT | Logging estruturado |
| typer | 0.25.1 | MIT | CLI |

Todas as dependencias sao compatíveis com licenca MIT do projeto.
