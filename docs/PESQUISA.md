# Pesquisa de Base - MCP Juridico Brasil

**Autor:** Nikolas de Hor - nikolasdehor79@gmail.com
**Data:** junho de 2026

Consolidacao da pesquisa tecnica, legal e de mercado que embasou o design
do projeto. Serve como referencia para decisoes de arquitetura e como
material de onboarding para contribuidores.

---

## 1. Fontes Oficiais de Dados Processuais

### 1.1 API Publica DataJud (CNJ) - FONTE PRIMARIA DO MVP

URL base: `https://api-publica.datajud.cnj.jus.br/api_publica_{sigla_tribunal}/_search`

Autenticacao: APIKey publica (sem cadastro). Chave atual publicada em:
https://datajud-wiki.cnj.jus.br/api-publica/acesso/

Fundamento legal: Portaria CNJ 160/2020.

**O que retorna:**
- Metadados do processo: numero CNJ, tribunal, grau, datas, nivel de sigilo
- Classe e assunto (tabela TPU unificada CNJ)
- Orgao julgador com codigo IBGE do municipio
- Partes (nome e tipo - CPF/CNPJ nao indexado por LGPD)
- Movimentacoes com codigo TPU, nome e data/hora
- Formato (fisico/eletronico) e sistema (PJe, eSAJ, eProc, etc.)

**O que NAO retorna:**
- Teor das pecas (peticoes, decisoes, acordaos integrais)
- Processos sigilosos (nivelSigilo > 0)
- Busca direta por CPF/CNPJ
- Webhooks (somente polling)

**Cobertura:** 91 tribunais (superiores, TRFs, TRTs, TJs estaduais, TREs, militares)

**Defasagem:** T+1 a T+7 dias por tribunal. Inadequado para prazos criticos
sem estrategia de redundancia.

**Limite de taxa:** Nao publicado abertamente. Para uso em escala, solicitar
aumento de cota diretamente ao CNJ.

### 1.2 API Comunica - Domicilio Judicial Eletronico (Fase 4)

Portal: https://domicilio-eletronico.pdpj.jus.br

Fundamento: Resolucao CNJ 455/2022 (art. IV). Obrigatorio para PJ desde
30/05/2024, para orgaos publicos desde 30/09/2024, para PF desde 01/10/2024.

Autenticacao: OAuth2 `client_credentials` via GeCli. Header obrigatorio:
`On-behalf-Of: [CPF sem pontuacao]` para auditoria.

Endpoints principais:
- `GET /api/v1/eu` - recupera tenant ID
- `GET /comunicacoes` - lista comunicacoes (filtro: ate 7 dias ou por processo)
- `PUT /processos/{numero}/comunicacoes/{id}` - marca como lida (INICIA PRAZO)
- `GET /processos/{numero}/logs` - logs de eventos

**CRITICO:** Marcar como lida via API tem efeito juridico real. Implementar
confirmacao explicita antes de executar (Fase 4).

Status de migracao: prazo de migracao de autenticacao era 31/03/2026.
Verificar versao atual da API antes de implementar Fase 4.

### 1.3 PJe/MNI, e-SAJ, Projudi - Avaliacao

| Sistema | Viabilidade para MCP | Motivo |
|---|---|---|
| PJe MNI (SOAP) | Baixa | Fragmentado por tribunal, sem credencial nacional |
| e-SAJ TJSP | Muito baixa | Sem API publica, reCAPTCHA, ToS proibe automacao |
| Projudi TJPR | Baixa | SOAP, cobre apenas TJPR |
| Scraping geral | Descartado | Fragil, viola ToS da maioria dos portais |

**Conclusao:** DataJud e a unica fonte oficial, gratuita e REST com cobertura
nacional. Para producao em escala, combinar com provider comercial (Fase 3).

---

## 2. APIs Comerciais - Avaliacao Comparativa

### 2.1 Para o MVP e desenvolvimento

**TrackJud** (trackjud.com.br) - Melhor para MVP/prototipo:
- R$ 0,10 por consulta/tribunal, sem mensalidade, sem contrato
- Acesso imediato, documentacao OpenAPI 3.1
- Cobertura limitada (10 estados - SP, RJ, PE, AM, DF entre outros)
- Sem webhook documentado
- Ideal para testar integracao de provider comercial na Fase 3

### 2.2 Para producao (Fase 3)

**Judit.io** (judit.io) - Melhor custo-beneficio para B2B:
- 100% dos tribunais declarado, base propria +450 mi processos
- Webhook nativo, SLA contratual nos planos anuais
- R$ 1.000/mes (plano entrada) a R$ 35.000/mes
- R$ 0,07 a R$ 0,25 por consulta conforme volume
- Reconhecimento Febraban, SPC Brasil, B3
- Suporta protocolo MCP nativamente (relevante para posicionamento do produto)

**Escavador** (escavador.com/business/api) - Para casos com foco em diarios:
- SDK Python oficial no GitHub
- Busca por CPF/CNPJ/OAB/Nome + webhooks
- Teor de pecas e diarios oficiais
- Por credito (modelo pre-pago ou pos-pago)

**Jusbrasil Solucoes** (insight.jusbrasil.com.br) - Para compliance/risco:
- +500 mi processos, motor de decisao < 1 segundo
- 96 tribunais, 550+ diarios oficiais
- R$ 1.000/mes entrada
- Melhor para casos de KYC/AML, nao para monitoramento de prazo

**Digesto** (digesto.com.br) - Para LegalOps corporativo:
- Unico com gestao de prazos nativa e workflows BPMN
- Webhook com 13 tentativas, entrega ~1h apos publicacao em diario
- Preco nao publico (negociacao comercial)

**Codilo** (codilo.com.br) - Para alto volume com push puro:
- Push API sem polling necessario
- 95% taxa de acerto declarada
- Preco nao publico

### 2.3 Tabela decisoria por cenario

| Cenario | Provider recomendado |
|---|---|
| MVP / prototipo (< 500 consultas/mes) | TrackJud + DataJud fallback |
| Producao B2B escalavel | Judit.io |
| Compliance financeiro e KYC | Jusbrasil Solucoes |
| LegalOps corporativo com BPMN | Digesto |
| Alto volume com push puro | Codilo |

---

## 3. Marco Regulatorio

### 3.1 LGPD aplicada a dados processuais

Tensao fundamental: publicidade processual (CF art. 5 LX e 93 IX) vs.
protecao de dados pessoais (EC 115/2022 como direito fundamental).

Bases legais aplicaveis ao produto:
- Art. 7 V LGPD: execucao de contrato (servico ao advogado)
- Art. 7 IX LGPD: legitimo interesse (monitoramento de processo publico)
- Art. 11 II "d" LGPD: prevencao a fraude (alertas de movimentacao)

Dados sensiveis nos autos (saude, origem etnica, orientacao sexual):
exigem base legal mais robusta. Decisao de design: nao indexar, nao exibir.

### 3.2 Resolucao CNJ 647/2025 - marco central

Publicada em 26/09/2025. Pontos criticos para o produto:
- Compartilhamento formal obrigatorio (convenio ou instrumento equivalente)
  para acesso comercial aos dados CNJ/DataJud
- Proibicao de redistribuicao de base replica (art. 13)
- Proibicao de reidentificacao de titulares anonimizados
- Responsabilidade civil integral do agente privado em incidentes (art. 20)
- Exige hipotese legal dos arts. 7 e 11 LGPD para acesso de terceiros

**Acao pre-Fase 1:** Formalizar comunicacao ao CNJ sobre o produto antes
do lancamento publico.

### 3.3 Segredo de justica

Fundamento: art. 189 CPC. Processos sigilosos incluem:
- Acoes de familia (divorcio, guarda, adoção, alimentos) - art. 189 II CPC
- Processos criminais com risco a intimidade - art. 189 I CPC
- ECA (sigilo absoluto para menores)
- Dados de saude quando o juiz declara sigilo

O DataJud filtra processos sigilosos na origem (Portaria CNJ 160/2020).
O produto adiciona verificacao redundante via `nivelSigilo` no parsing.

### 3.4 OAB - limites do produto

Instrumentos relevantes:
- Provimento OAB 205/2021: publicidade e marketing juridico
- Recomendacao OAB 001/2024: diretrizes para IA na advocacia
- Resolucao CNJ 615/2025: politica de IA no Poder Judiciario (jul/2025)

O produto PODE:
- Resumos de movimentacoes para o advogado
- Alertas de intimacao e prazo para o advogado
- Pesquisa jurisprudencial assistida
- Geracao de rascunhos com revisao obrigatoria pelo advogado

O produto NUNCA pode:
- Configurar consultoria juridica direta ao cliente final
- Captar clientela automaticamente
- Prometer resultado processual
- Delegar analise juridica integral ao sistema sem revisao do advogado

---

## 4. Mercado

### 4.1 Dimensionamento

- 1,3 milhao de advogados ativos (OAB, 2025)
- 600 associados AB2L (ante 20 em 2017) - crescimento acelerado do setor
- 77% dos escritorios usam algum software de gestao processual
- 60 horas/mes economizadas com automacao de leitura do DJe (tendencia 2026)

### 4.2 Mapa de concorrentes

**Segmento autonomo/micro (1-3 advogados):**
Jusbrasil Pro, Juridiq Jovem Advogado, Astrea Light, Escavador Individual.
Faixa de preco: R$ 0 a R$ 50/mes.

**Segmento escritorio pequeno/medio (4-30 advogados):**
Astrea Up/Smart, Juridiq Essencial, ADVBOX Essencial, Projuris ADV.
Faixa de preco: R$ 220 a R$ 439/mes.

**Segmento enterprise (30+ advogados / dept. juridico):**
Projuris Enterprise, Themis (Aurum), ADVBOX Elite, SAJ ADV.
Preco sob consulta.

### 4.3 Posicionamento do produto

O MCP Juridico Brasil nao compete diretamente com os SaaS acima.
E um provedor de dados para assistentes de IA - camada complementar.
O advogado que ja usa Claude/GPT/Copilot no trabalho ganha acesso
processual dentro do assistente sem trocar de ferramenta.

Lacunas identificadas que o produto preenche:
1. Integracao nativa de dados processuais em assistentes de IA
2. Custo zero para consultas basicas (DataJud)
3. Conformidade LGPD + OAB como diferencial explicito de venda
4. Ecossistema open-source extensivel (advogado que programa pode contribuir)

---

## 5. Links de Referencia

### Fontes oficiais
- [API Publica DataJud - Wiki CNJ](https://datajud-wiki.cnj.jus.br/api-publica/)
- [Acesso API DataJud](https://datajud-wiki.cnj.jus.br/api-publica/acesso/)
- [Glossario DataJud](https://datajud-wiki.cnj.jus.br/api-publica/glossario/)
- [Domicilio Judicial Eletronico - PDPJ](https://docs.pdpj.jus.br/servicos-negociais/domicilio-judicial-eletronico/)
- [Manual DJe 3a Edicao (2025)](https://www.cnj.jus.br/wp-content/uploads/2025/02/manual-domicilio-ed3-2025-1.pdf)
- [Resolucao CNJ 455/2022](https://atos.cnj.jus.br/atos/detalhar/4509)
- [Resolucao CNJ 647/2025](https://atos.cnj.jus.br/atos/detalhar/6340)
- [Resolucao CNJ 615/2025 - IA no Judiciario](https://atos.cnj.jus.br/atos/detalhar/6001)
- [Termo de Uso API DataJud V1.1](https://formularios.cnj.jus.br/wp-content/uploads/2023/05/Termos-de-uso-api-publica-V1.1.pdf)
- [Padroes de API PJe/MNI](https://docs.pje.jus.br/manuais-basicos/padroes-de-api-do-pje/)
- [Projudi TJPR - Acesso automatizado](https://www.tjpr.jus.br/acesso-automatizado-por-sistemas-externos)

### OAB e regulacao
- [OAB - Recomendacao 001/2024 - IA na advocacia](https://www.oab.org.br/noticia/62704/oab-aprova-recomendacoes-para-uso-de-ia-na-pratica-juridica)
- [Provimento OAB 205/2021](https://diario.oab.org.br/pages/materia/842347)
- [STJ - Segredo de justica nas acoes penais (nov/2024)](https://www.stj.jus.br/sites/portalp/Paginas/Comunicacao/Noticias/2024/11082024-Segredo-de-justica-nas-acoes-penais-o-STJ-entre-o-direito-a-intimidade-e-o-interesse-publico-na-informacao.aspx)
- [Nota Tecnica TJES 04/2025 - Segredo de Justica](https://www.tjes.jus.br/wp-content/uploads/NOTA-TECNICA-04.2025-ORIENTACOES-PARA-O-USO-ADEQUADO-DA-PRERROGATIVA-SEGREDO-DE-JUSTICA.pdf)

### APIs comerciais
- [Escavador - API Business](https://www.escavador.com/business/api)
- [Judit.io - Planos](https://judit.io/planos/)
- [Judit.io - Cobertura](https://judit.io/cobertura-dos-tribunais/)
- [Codilo - Documentacao](https://docs.codilo.com.br/)
- [Digesto - LegalOps](https://www.digesto.com.br/legalops-planos)
- [Jusbrasil - API](https://conteudo.jusbrasil.com.br/api)
- [TrackJud - Precos](https://trackjud.com.br/pricing)

### Mercado e contexto
- [Comparativo softwares juridicos 2026 - SquadZ](https://asquadz.ai/blog/softwares-gestao-juridica-comparativo/)
- [Tendencias legal tech 2026 - Voga](https://voga.adv.br/blog/tendencias-legal-tech-2026-automacao-cloud-advocacia/)
- [Mercado legaltechs no Brasil - Agencia Javali](https://agenciajavali.com.br/o-mercado-de-legaltechs-no-brasil/)
- [Judit - DataJud vs APIs privadas](https://judit.io/blog/artigos/datajud-cnj-api-publica-x-privada-comparacao/)
- [LegalSuite - Guia DataJud](https://legalsuite.com.br/blog/datajud-api-cnj)
- [TecJustica - PJe/MNI: nem todo tribunal esta pronto](https://tecjustica.substack.com/p/integracao-pjemni-nem-todo-tribunal)
