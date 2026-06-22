# Changelog

Todas as mudanças notáveis neste projeto serão documentadas aqui.

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
versionamento seguindo [Semantic Versioning](https://semver.org/lang/pt-BR/).

## [Unreleased]

### Adicionado

- (trabalho em andamento)

## [0.1.0] - 2026-06-22

### Adicionado

#### Fase 1 - Consulta processual via DataJud CNJ (6 tools)

- `consultar_processo` - consulta um processo pelo número CNJ unificado (NNNNNNN-DD.AAAA.J.TT.OOOO),
  retornando dados cadastrais, classe, assunto, órgão julgador, valor da causa e situação atual.
  Cobertura de 91 tribunais (STF, STJ, TJs, TRFs, TRTs e especializados).
- `listar_movimentacoes` - lista as movimentações processuais com data, código CNJ de movimento
  e complementos. Suporta cursor de navegação por offset e filtro por período.
- `resumir_processo` - gera resumo estruturado do processo em linguagem natural: partes, pedidos,
  fase atual, últimas movimentações e próximos passos relevantes.
- `buscar_processos_parte` - busca processos por nome ou CPF/CNPJ de uma das partes, com filtro
  de tribunal e classe processual.
- `listar_tribunais` - retorna a lista de tribunais cobertos pela API DataJud com seus códigos,
  nomes e tipos (estadual, federal, trabalhista, superior).
- `verificar_disponibilidade_datajud` - verifica a disponibilidade da API DataJud e o status
  do índice de cada tribunal, útil para diagnóstico antes de consultas em lote.

#### Fase 2 - Cálculo de prazo e resources de monitoramento

- `calcular_prazo` - calcula o prazo processual a partir de uma data-base, considerando
  dias úteis, feriados nacionais, estaduais e recessos forenses configuráveis por tribunal.
  Usa `workalendar` para calendário de feriados brasileiro. Retorna data de vencimento,
  dias úteis percorridos e lista de dias não computados com justificativa.
- `verificar_prazo_vencimento` - verifica se um prazo está dentro do alerta (configurável,
  padrão 3 dias úteis) ou já vencido, retornando status semáforo (ok, alerta, vencido).
- Resource `processo://{numero_cnj}` - resource MCP de acompanhamento: retorna snapshot
  atualizado do processo a cada leitura, adequado para monitoramento periódico por clientes MCP.
- Resource `movimentacoes://{numero_cnj}` - resource MCP com as últimas movimentações do
  processo, com suporte a `since` para recuperar apenas novidades desde a última consulta.

[Unreleased]: https://github.com/DeHor-Labs/mcp-juridico-brasil/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/DeHor-Labs/mcp-juridico-brasil/releases/tag/v0.1.0
