# Plano E2E - MCP Jurídico Brasil

**Autor:** Nikolas de Hor - nikolasdehor79@gmail.com
**Data:** junho de 2026
**Versão do plano:** 1.0

---

## Visão de plataforma modular

O **MCP Jurídico Brasil** é uma plataforma de dados jurídicos brasileiros exposta via
Model Context Protocol (MCP), organizada em **módulos por domínio**. Cada módulo
é um conjunto coeso de tools, schemas e providers que cobre uma fatia específica
do universo jurídico. Os módulos são plugáveis - cada um pode ser evoluído,
substituído ou monetizado de forma independente.

### Módulo Processual - primeiro módulo (MVP atual)

O módulo Processual é o que as **Fases 0 a 4** deste plano entregam. Ele cobre:

- Consulta e acompanhamento de processos judiciais em 91 tribunais via DataJud
- Listagem de movimentações com códigos TPU
- Monitoramento por polling (Fase 1) e webhook (Fase 3)
- Cálculo de prazos e calendário forense (Fase 2)
- Intimações via Domicílio Judicial Eletrônico - DJe (Fase 4)

Fonte de dados primária: **API pública DataJud do CNJ** (gratuita, sem cadastro).

### Módulos futuros plugáveis

Os módulos abaixo entram no roadmap após a conclusão da Fase 4. A fonte de dados
de cada um será validada na fase de planejamento do respectivo módulo.

| Módulo | Descrição | Fontes candidatas (a validar na fase do módulo) |
|---|---|---|
| **Jurisprudência** | Decisões, súmulas e precedentes qualificados | Portais e APIs de STF, STJ, TST e TJs; DJe/PDPJ |
| **Legislação** | Leis, decretos, normas e regulamentações | LexML (lexml.gov.br), portal Planalto, DOU |
| **Diários Oficiais** | Publicações e intimações em diários eletrônicos | DJEN/CNJ, Querido Diário (Open Knowledge Brasil) |
| **Cálculos Jurídicos** | Correção monetária, juros legais e prazos processuais | TJSP-JEC, tabelas do CNJ, IPCA/SELIC Banco Central |

### Como a arquitetura suporta a expansão modular

A arquitetura escolhida nas Fases 0-4 foi desenhada para acomodar novos módulos
sem quebrar o que já existe:

- **Pacotes irmãos por domínio:** cada módulo futuro virá um pacote Python ao lado
  de `src/mcp_juridico_brasil/processo/`, `movimentacoes/` etc., seguindo a mesma
  convenção de diretórios e sem acoplar ao módulo Processual.
- **Provider abstrato generalizável:** o `ProcessoProvider` (ABC) é o padrão a ser
  replicado em cada módulo - um `JurisprudenciaProvider`, um `LegislacaoProvider`,
  etc. O padrão Strategy já está no código; basta criar novas implementações concretas.
- **Tools agrupadas por módulo:** cada módulo registra suas próprias tools no
  `server.py` via decorador `@app.tool()`, mantendo o namespace organizado e
  permitindo ativar ou desativar grupos de tools por configuração.
- **Schemas Pydantic por domínio:** cada módulo define seus próprios schemas em
  `shared/schemas_<dominio>.py`, sem poluir os schemas do módulo Processual.

---

## 1. Stack e Justificativa

### Escolha: Python 3.10+ com FastMCP

O MCP Jurídico Brasil adota exatamente a mesma stack do MCP Fiscal Brasil
(`mcp-fiscal-brasil`), seu projeto irmão:

| Componente | Escolha | Razão |
|---|---|---|
| Runtime | Python 3.10+ | Compatibilidade com FastMCP, ecossistema data/legal robusto |
| Framework MCP | fastmcp >= 3.2.0 | Mesma versão do MCP Fiscal; decorator `@app.tool()` simples |
| HTTP async | httpx | Cliente async com retry nativo via tenacity |
| Validação | pydantic v2 | Schemas tipados, serialization JSON built-in |
| Rate limiting | aiolimiter | Controla rajadas contra a API DataJud |
| Cache TTL | cachetools.TTLCache | Evita requisições repetidas ao DataJud |
| Retry | tenacity | Exponential backoff para erros 429/5xx |
| Logging | structlog | Logs estruturados (mesmo padrão do MCP Fiscal) |
| Config | pydantic-settings | .env -> variáveis de ambiente -> defaults |
| CLI | typer | Consistente com o MCP Fiscal |
| Linter | ruff | Idêntico ao MCP Fiscal |
| Typecheck | mypy (strict) | Idêntico ao MCP Fiscal |
| Testes | pytest + pytest-asyncio | Idêntico ao MCP Fiscal |
| Build | hatchling | Idêntico ao MCP Fiscal |
| Package manager | uv | Idêntico ao MCP Fiscal |
| CI | GitHub Actions (matrix 3.10-3.13) | Idêntico ao MCP Fiscal |

**Por que não TypeScript/Node?**
O MCP Fiscal usa Python. Manter a mesma stack elimina custo cognitivo de troca
de contexto, permite reuso de padrões de HTTPClient, config, erros e CI, e
o ecossistema Python tem bibliotecas maduras para processamento jurídico
(datas, calendários, NLP em pt-BR). O SDK TypeScript do MCP seria igualmente
válido tecnicamente, mas a coerência com o projeto irmão é o fator decisivo.

---

## 2. Arquitetura do MCP

### 2.1 Diagrama de camadas

```
Claude / qualquer cliente MCP
        |
        | stdio ou HTTP streamable
        v
+----------------------------+
|  server.py (FastMCP)       |  <- registro de tools, instruções globais
+----------------------------+
|  Tools (por módulo)        |
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
|  DJeProvider               |  Fase 4 - intimações próprias
+----------------------------+
|  DataJudClient             |  Elasticsearch DSL -> DataJud CNJ
|  HTTPClient (core)         |  retry + rate limit + cache
+----------------------------+
|  shared/schemas.py         |  Processo, Movimentacao, Parte, ...
|  shared/validators.py      |  validar_numero_cnj, normalizar, ...
|  datajud/tribunais.py      |  mapa sigla -> índice DataJud (91 trib.)
+----------------------------+
```

### 2.2 Tools expostas no MVP (Fase 1)

| Tool | Input | Output | Observação |
|---|---|---|---|
| `buscar_processo_por_numero` | numero_processo, tribunal? | dados completos do processo | Verifica sigilo antes de retornar |
| `listar_movimentacoes` | numero_processo, tribunal, limite? | lista de movimentações TPU | Ordenado do mais recente |
| `resumir_andamento` | numero_processo, tribunal? | dados + instrução de resumo | Resumo semântico fica no modelo |
| `monitorar_processo` | numero_processo, tribunal, desde_iso | bool houve_atualizacao | Polling; Fase 3 troca por push |
| `calcular_proximo_prazo` | numero_processo, tribunal, tipo_ato? | estimativa de prazo | Stub em dias corridos; Fase 2 expande |
| `listar_tribunais` | (nenhum) | lista de siglas | 91 tribunais suportados |

### 2.3 Resources (Fase 1)

Nenhum resource MCP persistente no MVP. Fase 2 adiciona:
- `resource://processo/{numero}` - snapshot cacheado de processo monitorado
- `resource://tribunal/{sigla}/status` - status de atualização do índice DataJud

### 2.4 Design do provider abstrato

```python
class ProcessoProvider(ABC):
    async def buscar_processo(numero, tribunal?) -> Processo: ...
    async def listar_movimentacoes(numero, tribunal, limite) -> list[Movimentacao]: ...
    async def verificar_atualizacao(numero, tribunal, desde_iso) -> bool: ...
```

`DataJudProvider` é a implementação concreta do MVP. Em Fase 3, o servidor
detecta `JURIDICO_PROVIDER_COMERCIAL` no ambiente e instancia `ComercialProvider`
que delega ao Judit, Escavador ou TrackJud via seus SDKs/APIs REST. As tools
não mudam - apenas o provider injetado muda. Isso é o padrão Strategy aplicado
ao acesso a dados.

---

## 3. Fases de Entrega

### Fase 0 - Scaffold (atual)

**Escopo:**
- Estrutura de diretórios espelhando o MCP Fiscal
- pyproject.toml, server.json, smithery.yaml, .env.example
- Hierarquia de erros com `JuridicoSigiloError` como cidadão de primeira classe
- HTTPClient com retry/rate limit/cache (reuso de padrões do MCP Fiscal)
- Schemas Pydantic: Processo, Movimentacao, Parte, OrgaoJulgador
- Validador de número CNJ (regex NNNNNNN-DD.AAAA.J.TT.OOOO)
- Mapeamento de 91 tribunais DataJud
- Stubs de todas as tools com docstrings e disclaimers LGPD/OAB
- Interface `ProcessoProvider` + `DataJudProvider` (parcialmente implementado)
- CI GitHub Actions (lint, typecheck, test matrix 3.10-3.13)
- Testes unitários de validators

**Critérios de aceite:**
- `make lint` passa sem erros
- `make typecheck` passa
- `make test` executa e os testes de validators passam
- Estrutura espelha o MCP Fiscal (revisão manual)

**Estimativa:** 1-2 dias (scaffold já criado)

---

### Fase 1 - MVP DataJud

**Escopo:**
- `DataJudClient.buscar_por_numero` funcionando contra a API real
- `DataJudClient.buscar_por_numero_multiplos_tribunais` com iteração por tribunal
- `DataJudClient.listar_movimentacoes` com ordenação e limite
- `DataJudProvider` completo implementando `ProcessoProvider`
- Verificação de `nivelSigilo > 0` integrada ao parsing (bloquear, não cachear)
- Todas as 6 tools retornando dados reais via DataJud
- Testes de integração com `respx` (mock do DataJud) para os 4 cenários:
  processo público, processo sigiloso, processo não encontrado, erro de API
- Exemplo de uso em `examples/consulta_basica.py`
- Cobertura de testes >= 80%
- Publicação no PyPI (versão 0.1.0)

**Critérios de aceite:**
- `buscar_processo_por_numero("0001234-56.2023.8.26.0100", "TJSP")` retorna dados reais
- Processo com `nivelSigilo=1` lança `JuridicoSigiloError` com mensagem clara
- Processo inexistente lança `JuridicoNotFoundError`
- `listar_tribunais()` retorna exatamente 91 entradas
- CI verde em Python 3.10, 3.11, 3.12, 3.13
- `uvx mcp-juridico-brasil` funciona no Claude Desktop

**Estimativa:** 5-7 dias

---

### Fase 2 - Monitoramento e Alertas de Prazo

**Escopo:**
- `monitorar_processo` com polling agendável (retorna delta de movimentações)
- `calcular_proximo_prazo` completo:
  - Tabela de prazos CPC (art. 219 e seguintes) por tipo de ato
  - Calendário forense por UF (feriados nacionais + estaduais)
  - Detecção de suspensão de prazo (recesso forense jan/jul)
  - Diferenciação entre dias úteis e corridos por tipo de prazo
- Resource MCP `processo/{numero}/snapshot` para armazenar estado anterior
- Comparação de snapshots para identificar novas movimentações
- Tool `listar_processos_monitorados` (estado em memória por sessão)
- Testes de calendário com casos de borda (virada de ano, feriados móveis)

**Critérios de aceite:**
- Prazo de Embargos de Declaração (5 dias úteis) calculado corretamente
  considerando sábados, domingos e feriados nacionais
- Recesso forense (20 dez a 20 jan) suspende contagem corretamente
- `monitorar_processo` retorna apenas movimentações novas desde o último check
- Cobertura de testes >= 80%

**Estimativa:** 10-14 dias

---

### Fase 3 - Push em Tempo Real via Provider Comercial

**Escopo:**
- Interface `WebhookProvider` (extensão de `ProcessoProvider`)
- `ComercialProvider` configurável via env: Judit, Escavador ou TrackJud
- Mecanismo de registro de webhook: tool `registrar_webhook_processo`
- Recepção de notificação push e tradução para o schema interno
- Fallback automático para DataJud se o provider comercial estiver indisponível
- Documentação de configuração de cada provider suportado
- Preço estimado por consulta documentado no README por provider

**Critérios de aceite:**
- Com `JURIDICO_PROVIDER_COMERCIAL=judit` e chave válida, `monitorar_processo`
  retorna notificação em < 2 horas após movimentação (SLA Judit)
- Sem provider configurado, todas as tools funcionam normalmente via DataJud
- Troca de provider não exige alteração no código das tools
- Cobertura de testes >= 80% (mocks dos providers comerciais)

**Estimativa:** 10-15 dias (depende de acesso a sandbox dos providers)

---

### Fase 4 - Intimações via Domicílio Judicial Eletrônico

**Escopo:**
- `DJeProvider` implementando acesso à API Comunica (DJe/PDPJ)
- Autenticação OAuth2 com `client_credentials` via GeCli
- Tool `listar_intimacoes`: lista comunicações pendentes do CNPJ cadastrado
- Tool `marcar_intimacao_como_lida`: PUT que perfaz a ciência oficial
- Tool `buscar_intimacoes_por_processo`: filtra por número CNJ
- Aviso claro: `marcar_intimacao_como_lida` inicia contagem de prazo oficial
- Logs de auditoria imutáveis para cada leitura (header `On-behalf-Of`)
- Documentação de credenciamento no portal DJe (exige certificado digital)

**Critérios de aceite:**
- `listar_intimacoes` retorna comunicações reais do CNPJ configurado
- `marcar_intimacao_como_lida` retorna confirmação e timestamp da ciência
- Tentativa de acessar intimação de CNPJ diferente do configurado retorna erro
- Aviso de prazo exibido proeminentemente antes de qualquer marcação como lida
- Logs de auditoria persistidos em arquivo local com hash de integridade

**Riscos específicos Fase 4:**
- O portal DJe exige credenciamento com certificado digital ICP-Brasil
  (e-CNPJ ou e-CPF) - não pode ser automatizado completamente
- A API OAuth2 do DJe teve migração obrigatória até 31/03/2026;
  verificar se a versão atual é compatível antes de implementar
- Marcar como lida via API tem efeito jurídico real (inicia prazo);
  exigir confirmação explícita do usuário antes de executar

**Estimativa:** 15-20 dias

---

### Pós-Fase 4 - Abertura dos próximos módulos

Com o módulo Processual maduro e publicado, os próximos módulos entram em
planejamento seguindo o mesmo ciclo: definição de fontes, scaffold, MVP, expansão.

Ordem tentativa (sujeita a validação de demanda):

1. **Jurisprudência** - alta sinergia com o módulo Processual (processos citam acórdãos)
2. **Diários Oficiais** - complemento natural ao módulo DJe da Fase 4
3. **Legislação** - base de referência para os demais módulos
4. **Cálculos Jurídicos** - módulo transversal, pode ser entregue em paralelo com qualquer outro

Cada módulo terá seu próprio PLANO-E2E, versionamento de API e política de
compatibilidade. Módulos existentes não serão quebrados por módulos novos.

---

## 4. Riscos e Mitigações (como Requisitos de Design)

### 4.1 Segredo de justiça (CRÍTICO)

**Risco:** Expor dados de processo sigiloso para usuário não autorizado.

**Mitigação embutida no design:**
- `JuridicoSigiloError` é verificado ANTES de qualquer retorno de dados
- Processos com `nivelSigilo > 0` não são cacheados (nem no TTLCache)
- Logs de processos sigilosos registram apenas número e nível, nunca conteúdo
- Nenhum fallback para "tentar outro provider" quando o DataJud bloqueia por sigilo
- Fundamento: art. 189 CPC + Portaria CNJ 160/2020 (DataJud filtra na origem)

**Implementação:** `datajud/client.py` - método `_parse_processo` verifica
`nivelSigilo` antes de construir o objeto `Processo`. Qualquer valor > 0 lança
`JuridicoSigiloError` imediatamente, sem retornar dados parciais.

### 4.2 LGPD - dados pessoais de partes (ALTO)

**Risco:** Tratar CPF/CNPJ de partes, dados de saúde ou dados sensíveis
sem base legal adequada ou além do necessário.

**Mitigação embutida no design:**
- Schema `Parte` não tem campo CPF/CNPJ (a API DataJud não indexa por razões de LGPD)
- Campos de dados sensíveis (saúde, orientação sexual, origem étnica) não existem
  nos schemas - se estiverem nos complementos, não são indexados
- Retenção: dados em memória apenas durante a sessão MCP ativa
- Nenhum banco de dados local ou cache persistente no MVP

**Base legal adotada:** art. 7, IX LGPD (legítimo interesse do advogado
no acompanhamento de processos de seus clientes) + art. 7, V (execução
de contrato de serviço com o advogado).

### 4.3 Resolução CNJ 647/2025 - uso comercial do DataJud (ALTO)

**Risco:** Usar DataJud como base de produto comercial sem formalização
com o CNJ pode ser contestado. Art. 13 proíbe redistribuição de base réplica.

**Mitigação embutida no design:**
- Arquitetura "query on demand": nenhuma base réplica é mantida localmente
- Cada consulta busca em tempo real na API DataJud
- Cache TTL curto (300s padrão) para uso normal, não para replicação
- Termos de uso do produto proíbem exportação em massa pelo usuário
- Recomendação: formalizar relacionamento com CNJ via comunicação oficial
  antes do lançamento público (ação pré-Fase 1)

### 4.4 OAB - exercício da advocacia / captação indevida (ALTO)

**Risco:** Funcionalidade que configure consultoria jurídica direta ou
captação automatizada de clientela, vedada pelo CED OAB e
Provimento OAB 205/2021.

**Mitigação embutida no design:**
- Disclaimer obrigatório em TODAS as tools e no campo `instructions` do servidor
- `resumir_andamento` retorna dados + instrução de resumo, não "conselho jurídico"
- Nenhuma tool envia mensagens a clientes finais ou terceiros
- Produto posicionado como ferramenta para o advogado, nunca para o cliente final
- Termos de uso do produto vedará uso direto por clientes sem intermediação

### 4.5 Rotação da chave DataJud pelo CNJ (MÉDIO)

**Risco:** O CNJ pode rotacionar a APIKey pública sem aviso prévio.

**Mitigação:** Chave configurável via `DATAJUD_API_KEY` no .env. Fallback
de erro explícito com link para a wiki do CNJ. SLA interno: readequar em 48h
após notificação de revogação.

### 4.6 Defasagem DataJud em prazos críticos (MÉDIO)

**Risco:** Advogado usa `calcular_proximo_prazo` baseado em movimentação
desatualizada e perde o prazo real.

**Mitigação embutida no design:**
- Aviso de defasagem em TODOS os retornos de prazo (campo `aviso` obrigatório)
- `calcular_proximo_prazo` tem campo `limitacao` explicitando que é estimativa
- Documentação orienta uso de provider comercial (Fase 3) para prazos críticos
- Disclaimer no README e nas instruções do servidor MCP

---

## 5. Posicionamento e Monetização

### 5.1 Modelo: core open-source + camada paga opcional

```
+------------------------------------------+
| CORE OPEN-SOURCE (MIT)                   |
| - DataJud (91 tribunais, polling)        |
| - Todas as 6 tools do MVP               |
| - Sem limite de processos locais         |
| - Sem cadastro ou API key própria        |
+------------------------------------------+
          |
          v
+------------------------------------------+
| CAMADA PAGA (futura - Fase 3+)           |
| - Provider comercial (webhook push)      |
| - Monitoramento contínuo multi-processo  |
| - Alertas em tempo real                  |
| - Integração DJe (intimações oficiais)   |
+------------------------------------------+
```

O modelo espelha o MCP Fiscal Brasil: funcionalidade básica gratuita e útil
para o público geral; camada paga para casos de uso profissional em escala.

### 5.2 Público-alvo e proposta de valor

**Primário:** Advogado autônomo e escritório pequeno (1-5 advogados)

- Dor principal: perda de prazo por não monitorar DJe e portal do tribunal
- Proposta: consulta processual direto no Claude/assistente de IA sem
  sair do fluxo de trabalho. Sem login em portal, sem copiar/colar número.
- Barreira de entrada: zero (open-source, sem cadastro, sem custo inicial)

**Secundário:** Desenvolvedor de legaltech

- Dor: construir integração DataJud do zero para cada produto
- Proposta: provider abstraído, schemas Pydantic prontos, CI configurado,
  tratamento de sigilo e LGPD embutidos

### 5.3 Diferenciação em relação aos concorrentes

Os concorrentes diretos (Jusbrasil Pro, Juridiq, Astrea, ADVBOX) são
plataformas SaaS com interface web própria. O MCP Jurídico Brasil é
um provedor de dados para assistentes de IA - posicionamento complementar,
não substituto. O advogado que já usa Claude/Copilot/GPT no dia a dia
ganha acesso processual sem trocar de ferramenta.

### 5.4 Caminho para monetização (Fase 3+)

Opções a avaliar após validação do MVP:
1. **API key própria paga** para acesso ao provider comercial embutido
   (repassar custo do Judit/Escavador com margem)
2. **Plano mensal** para monitoramento contínuo com webhook e alertas
   (R$ 29-49/mês para até 100 processos monitorados)
3. **Plugin pago no Smithery/MCP Registry** para usuários que não querem
   configurar infraestrutura própria

Não há plano de cobrar pelo acesso ao DataJud (que é público e gratuito).

---

## 6. Dependências de Terceiros e Licenças

| Dependência | Versão mínima | Licença | Uso |
|---|---|---|---|
| fastmcp | 3.2.0 | MIT | Framework MCP |
| httpx | 0.27.0 | BSD | HTTP async |
| pydantic | 2.0 | MIT | Schemas e validação |
| pydantic-settings | 2.13.1 | MIT | Config via env |
| python-dateutil | 2.9.0 | Apache 2.0 | Parsing de datas |
| tenacity | 9.1.4 | Apache 2.0 | Retry com backoff |
| cachetools | 7.0.5 | MIT | Cache TTL |
| aiolimiter | 1.2.1 | MIT | Rate limiting |
| structlog | 25.5.0 | MIT | Logging estruturado |
| typer | 0.25.1 | MIT | CLI |

Todas as dependências são compatíveis com licença MIT do projeto.
