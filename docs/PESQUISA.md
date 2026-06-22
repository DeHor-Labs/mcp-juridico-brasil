# Pesquisa de Base - MCP Jurídico Brasil

**Autor:** Nikolas de Hor - nikolasdehor79@gmail.com
**Data:** junho de 2026

Consolidação da pesquisa técnica, legal e de mercado que embasou o design
do projeto. Serve como referência para decisões de arquitetura e como
material de onboarding para contribuidores.

---

## 1. Fontes Oficiais de Dados Processuais

### 1.1 API Pública DataJud (CNJ) - FONTE PRIMÁRIA DO MVP

URL base: `https://api-publica.datajud.cnj.jus.br/api_publica_{sigla_tribunal}/_search`

Autenticação: APIKey pública (sem cadastro). Chave atual publicada em:
https://datajud-wiki.cnj.jus.br/api-publica/acesso/

Fundamento legal: Portaria CNJ 160/2020.

**O que retorna:**
- Metadados do processo: número CNJ, tribunal, grau, datas, nível de sigilo
- Classe e assunto (tabela TPU unificada CNJ)
- Órgão julgador com código IBGE do município
- Partes (nome e tipo - CPF/CNPJ não indexado por LGPD)
- Movimentações com código TPU, nome e data/hora
- Formato (físico/eletrônico) e sistema (PJe, eSAJ, eProc, etc.)

**O que NÃO retorna:**
- Teor das peças (petições, decisões, acórdãos integrais)
- Processos sigilosos (nivelSigilo > 0)
- Busca direta por CPF/CNPJ
- Webhooks (somente polling)

**Cobertura:** 91 tribunais (superiores, TRFs, TRTs, TJs estaduais, TREs, militares)

**Defasagem:** T+1 a T+7 dias por tribunal. Inadequado para prazos críticos
sem estratégia de redundância.

**Limite de taxa:** Não publicado abertamente. Para uso em escala, solicitar
aumento de cota diretamente ao CNJ.

### 1.2 API Comunica - Domicílio Judicial Eletrônico (Fase 4)

Portal: https://domicilio-eletronico.pdpj.jus.br

Fundamento: Resolução CNJ 455/2022 (art. IV). Obrigatório para PJ desde
30/05/2024, para órgãos públicos desde 30/09/2024, para PF desde 01/10/2024.

Autenticação: OAuth2 `client_credentials` via GeCli. Header obrigatório:
`On-behalf-Of: [CPF sem pontuação]` para auditoria.

Endpoints principais:
- `GET /api/v1/eu` - recupera tenant ID
- `GET /comunicacoes` - lista comunicações (filtro: até 7 dias ou por processo)
- `PUT /processos/{numero}/comunicacoes/{id}` - marca como lida (INICIA PRAZO)
- `GET /processos/{numero}/logs` - logs de eventos

**CRÍTICO:** Marcar como lida via API tem efeito jurídico real. Implementar
confirmação explícita antes de executar (Fase 4).

Status de migração: prazo de migração de autenticação era 31/03/2026.
Verificar versão atual da API antes de implementar Fase 4.

### 1.3 PJe/MNI, e-SAJ, Projudi - Avaliação

| Sistema | Viabilidade para MCP | Motivo |
|---|---|---|
| PJe MNI (SOAP) | Baixa | Fragmentado por tribunal, sem credencial nacional |
| e-SAJ TJSP | Muito baixa | Sem API pública, reCAPTCHA, ToS proíbe automação |
| Projudi TJPR | Baixa | SOAP, cobre apenas TJPR |
| Scraping geral | Descartado | Frágil, viola ToS da maioria dos portais |

**Conclusão:** DataJud é a única fonte oficial, gratuita e REST com cobertura
nacional. Para produção em escala, combinar com provider comercial (Fase 3).

---

## 2. APIs Comerciais - Avaliação Comparativa

### 2.1 Para o MVP e desenvolvimento

**TrackJud** (trackjud.com.br) - Melhor para MVP/protótipo:
- R$ 0,10 por consulta/tribunal, sem mensalidade, sem contrato
- Acesso imediato, documentação OpenAPI 3.1
- Cobertura limitada (10 estados - SP, RJ, PE, AM, DF entre outros)
- Sem webhook documentado
- Ideal para testar integração de provider comercial na Fase 3

### 2.2 Para produção (Fase 3)

**Judit.io** (judit.io) - Melhor custo-benefício para B2B:
- 100% dos tribunais declarado, base própria +450 mi processos
- Webhook nativo, SLA contratual nos planos anuais
- R$ 1.000/mês (plano entrada) a R$ 35.000/mês
- R$ 0,07 a R$ 0,25 por consulta conforme volume
- Reconhecimento Febraban, SPC Brasil, B3
- Suporta protocolo MCP nativamente (relevante para posicionamento do produto)

**Escavador** (escavador.com/business/api) - Para casos com foco em diários:
- SDK Python oficial no GitHub
- Busca por CPF/CNPJ/OAB/Nome + webhooks
- Teor de peças e diários oficiais
- Por crédito (modelo pré-pago ou pós-pago)

**Jusbrasil Soluções** (insight.jusbrasil.com.br) - Para compliance/risco:
- +500 mi processos, motor de decisão < 1 segundo
- 96 tribunais, 550+ diários oficiais
- R$ 1.000/mês entrada
- Melhor para casos de KYC/AML, não para monitoramento de prazo

**Digesto** (digesto.com.br) - Para LegalOps corporativo:
- Único com gestão de prazos nativa e workflows BPMN
- Webhook com 13 tentativas, entrega ~1h após publicação em diário
- Preço não público (negociação comercial)

**Codilo** (codilo.com.br) - Para alto volume com push puro:
- Push API sem polling necessário
- 95% taxa de acerto declarada
- Preço não público

### 2.3 Tabela decisória por cenário

| Cenário | Provider recomendado |
|---|---|
| MVP / protótipo (< 500 consultas/mês) | TrackJud + DataJud fallback |
| Produção B2B escalável | Judit.io |
| Compliance financeiro e KYC | Jusbrasil Soluções |
| LegalOps corporativo com BPMN | Digesto |
| Alto volume com push puro | Codilo |

---

## 3. Marco Regulatório

### 3.1 LGPD aplicada a dados processuais

Tensão fundamental: publicidade processual (CF art. 5 LX e 93 IX) vs.
proteção de dados pessoais (EC 115/2022 como direito fundamental).

Bases legais aplicáveis ao produto:
- Art. 7 V LGPD: execução de contrato (serviço ao advogado)
- Art. 7 IX LGPD: legítimo interesse (monitoramento de processo público)
- Art. 11 II "d" LGPD: prevenção a fraude (alertas de movimentação)

Dados sensíveis nos autos (saúde, origem étnica, orientação sexual):
exigem base legal mais robusta. Decisão de design: não indexar, não exibir.

### 3.2 Resolução CNJ 647/2025 - marco central

Publicada em 26/09/2025. Pontos críticos para o produto:
- Compartilhamento formal obrigatório (convênio ou instrumento equivalente)
  para acesso comercial aos dados CNJ/DataJud
- Proibição de redistribuição de base réplica (art. 13)
- Proibição de reidentificação de titulares anonimizados
- Responsabilidade civil integral do agente privado em incidentes (art. 20)
- Exige hipótese legal dos arts. 7 e 11 LGPD para acesso de terceiros

**Ação pré-Fase 1:** Formalizar comunicação ao CNJ sobre o produto antes
do lançamento público.

### 3.3 Segredo de justiça

Fundamento: art. 189 CPC. Processos sigilosos incluem:
- Ações de família (divórcio, guarda, adoção, alimentos) - art. 189 II CPC
- Processos criminais com risco à intimidade - art. 189 I CPC
- ECA (sigilo absoluto para menores)
- Dados de saúde quando o juiz declara sigilo

O DataJud filtra processos sigilosos na origem (Portaria CNJ 160/2020).
O produto adiciona verificação redundante via `nivelSigilo` no parsing.

### 3.4 OAB - limites do produto

Instrumentos relevantes:
- Provimento OAB 205/2021: publicidade e marketing jurídico
- Recomendação OAB 001/2024: diretrizes para IA na advocacia
- Resolução CNJ 615/2025: política de IA no Poder Judiciário (jul/2025)

O produto PODE:
- Resumos de movimentações para o advogado
- Alertas de intimação e prazo para o advogado
- Pesquisa jurisprudencial assistida
- Geração de rascunhos com revisão obrigatória pelo advogado

O produto NUNCA pode:
- Configurar consultoria jurídica direta ao cliente final
- Captar clientela automaticamente
- Prometer resultado processual
- Delegar análise jurídica integral ao sistema sem revisão do advogado

---

## 4. Mercado

### 4.1 Dimensionamento

- 1,3 milhão de advogados ativos (OAB, 2025)
- 600 associados AB2L (ante 20 em 2017) - crescimento acelerado do setor
- 77% dos escritórios usam algum software de gestão processual
- 60 horas/mês economizadas com automação de leitura do DJe (tendência 2026)

### 4.2 Mapa de concorrentes

**Segmento autônomo/micro (1-3 advogados):**
Jusbrasil Pro, Juridiq Jovem Advogado, Astrea Light, Escavador Individual.
Faixa de preço: R$ 0 a R$ 50/mês.

**Segmento escritório pequeno/médio (4-30 advogados):**
Astrea Up/Smart, Juridiq Essencial, ADVBOX Essencial, Projuris ADV.
Faixa de preço: R$ 220 a R$ 439/mês.

**Segmento enterprise (30+ advogados / dept. jurídico):**
Projuris Enterprise, Themis (Aurum), ADVBOX Elite, SAJ ADV.
Preço sob consulta.

### 4.3 Posicionamento do produto

O MCP Jurídico Brasil não compete diretamente com os SaaS acima.
É um provedor de dados para assistentes de IA - camada complementar.
O advogado que já usa Claude/GPT/Copilot no trabalho ganha acesso
processual dentro do assistente sem trocar de ferramenta.

Lacunas identificadas que o produto preenche:
1. Integração nativa de dados processuais em assistentes de IA
2. Custo zero para consultas básicas (DataJud)
3. Conformidade LGPD + OAB como diferencial explícito de venda
4. Ecossistema open-source extensível (advogado que programa pode contribuir)

---

## 5. Links de Referência

### Fontes oficiais
- [API Pública DataJud - Wiki CNJ](https://datajud-wiki.cnj.jus.br/api-publica/)
- [Acesso API DataJud](https://datajud-wiki.cnj.jus.br/api-publica/acesso/)
- [Glossário DataJud](https://datajud-wiki.cnj.jus.br/api-publica/glossario/)
- [Domicílio Judicial Eletrônico - PDPJ](https://docs.pdpj.jus.br/servicos-negociais/domicilio-judicial-eletronico/)
- [Manual DJe 3a Edição (2025)](https://www.cnj.jus.br/wp-content/uploads/2025/02/manual-domicilio-ed3-2025-1.pdf)
- [Resolução CNJ 455/2022](https://atos.cnj.jus.br/atos/detalhar/4509)
- [Resolução CNJ 647/2025](https://atos.cnj.jus.br/atos/detalhar/6340)
- [Resolução CNJ 615/2025 - IA no Judiciário](https://atos.cnj.jus.br/atos/detalhar/6001)
- [Termo de Uso API DataJud V1.1](https://formularios.cnj.jus.br/wp-content/uploads/2023/05/Termos-de-uso-api-publica-V1.1.pdf)
- [Padrões de API PJe/MNI](https://docs.pje.jus.br/manuais-basicos/padroes-de-api-do-pje/)
- [Projudi TJPR - Acesso automatizado](https://www.tjpr.jus.br/acesso-automatizado-por-sistemas-externos)

### OAB e regulação
- [OAB - Recomendação 001/2024 - IA na advocacia](https://www.oab.org.br/noticia/62704/oab-aprova-recomendacoes-para-uso-de-ia-na-pratica-juridica)
- [Provimento OAB 205/2021](https://diario.oab.org.br/pages/materia/842347)
- [STJ - Segredo de justiça nas ações penais (nov/2024)](https://www.stj.jus.br/sites/portalp/Paginas/Comunicacao/Noticias/2024/11082024-Segredo-de-justica-nas-acoes-penais-o-STJ-entre-o-direito-a-intimidade-e-o-interesse-publico-na-informacao.aspx)
- [Nota Técnica TJES 04/2025 - Segredo de Justiça](https://www.tjes.jus.br/wp-content/uploads/NOTA-TECNICA-04.2025-ORIENTACOES-PARA-O-USO-ADEQUADO-DA-PRERROGATIVA-SEGREDO-DE-JUSTICA.pdf)

### APIs comerciais
- [Escavador - API Business](https://www.escavador.com/business/api)
- [Judit.io - Planos](https://judit.io/planos/)
- [Judit.io - Cobertura](https://judit.io/cobertura-dos-tribunais/)
- [Codilo - Documentação](https://docs.codilo.com.br/)
- [Digesto - LegalOps](https://www.digesto.com.br/legalops-planos)
- [Jusbrasil - API](https://conteudo.jusbrasil.com.br/api)
- [TrackJud - Preços](https://trackjud.com.br/pricing)

### Mercado e contexto
- [Comparativo softwares juridicos 2026 - SquadZ](https://asquadz.ai/blog/softwares-gestao-juridica-comparativo/)
- [Tendencias legal tech 2026 - Voga](https://voga.adv.br/blog/tendencias-legal-tech-2026-automacao-cloud-advocacia/)
- [Mercado legaltechs no Brasil - Agencia Javali](https://agenciajavali.com.br/o-mercado-de-legaltechs-no-brasil/)
- [Judit - DataJud vs APIs privadas](https://judit.io/blog/artigos/datajud-cnj-api-publica-x-privada-comparacao/)
- [LegalSuite - Guia DataJud](https://legalsuite.com.br/blog/datajud-api-cnj)
- [TecJustica - PJe/MNI: nem todo tribunal esta pronto](https://tecjustica.substack.com/p/integracao-pjemni-nem-todo-tribunal)
