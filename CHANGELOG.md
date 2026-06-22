# Changelog

Todas as mudanças notáveis neste projeto serão documentadas aqui.

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
versionamento seguindo [Semantic Versioning](https://semver.org/lang/pt-BR/).

## [Unreleased]

### Adicionado

- (trabalho em andamento)

## [0.1.0] - 2026-06-22

### Adicionado

#### Fase 1 - Consulta processual via DataJud CNJ

- `buscar_processo_por_numero` - consulta completa de um processo pelo número CNJ unificado
  (NNNNNNN-DD.AAAA.J.TT.OOOO), retornando dados cadastrais, classe, assunto, órgão julgador,
  valor da causa e situação atual. Cobertura de 91 tribunais (STF, STJ, TJs, TRFs, TRTs e
  especializados).
- `listar_movimentacoes` - lista as movimentações processuais com data, código CNJ de movimento
  e complementos. Suporta cursor de navegação por offset e filtro por período.
- `resumir_andamento` - retorna dados do processo mais instrução de resumo estruturado para o
  modelo de linguagem: partes, fase atual, últimas movimentações e próximos passos relevantes.
- `monitorar_processo` - verifica atualizações desde uma data de referência (polling com snapshot
  em memória), retornando flag de atualização e diff de movimentações novas.
- `listar_tribunais` - retorna a lista completa dos 91 tribunais cobertos pela API DataJud com
  suas siglas (Portaria CNJ 160/2020). Use as siglas retornadas no parâmetro `tribunal` das
  demais tools.

#### Fase 2 - Cálculo de prazo e resources de monitoramento

- `calcular_proximo_prazo` - calcula o próximo prazo processual a partir de uma data-base,
  considerando dias úteis, feriados nacionais, estaduais e recessos forenses configuráveis por
  tribunal (art. 219, 220 e 224 do CPC). Usa `workalendar` para calendário brasileiro. Retorna
  data de vencimento, dias úteis percorridos e lista de dias não computados com justificativa.
- `listar_processos_monitorados` - lista os números de processos que possuem snapshot salvo na
  sessão MCP atual. Use o resource `processo://{numero}/snapshot` para ler os dados completos.
- Resource `processo://{numero_processo}/snapshot` - retorna o último snapshot capturado por
  `buscar_processo_por_numero` ou `monitorar_processo` para o processo informado. O estado é
  mantido em memória da sessão; configure `JURIDICO_SNAPSHOT_DIR` para persistência em arquivo.

[Unreleased]: https://github.com/DeHor-Labs/mcp-juridico-brasil/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/DeHor-Labs/mcp-juridico-brasil/releases/tag/v0.1.0
