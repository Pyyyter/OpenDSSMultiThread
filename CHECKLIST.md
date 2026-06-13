# ✅ Checklist de Implementação - OpenDSS MultiThread

## 1. Modelos de Domínio (src/utils/models.py)

- [ ] `VariableSpec` - Modelo de variável numérica extraída
- [ ] `RandomizationRule` - Regra de randomização
- [ ] `MonitorLimit` - Limites de segurança para monitor
- [ ] `SimulationCase` - Especificação de caso para executar
- [ ] `MonitorDataset` - Dados de monitor (colunas + linhas)
- [ ] `CaseResult` - Resultado da execução de um caso
- [ ] `ExecutionStats` - Estatísticas de execução

**Status:** ✅ Estrutura Criada - Pronto para Usar

---

## 2. Serviço de Validação (src/utils/validators.py)

### InputValidator

- [ ] `validate_archive()` - Validar arquivo compactado (formato, tamanho, integridade)
- [ ] `validate_dss_file()` - Validar arquivo .dss existe e é legível
- [ ] `validate_monitor_config()` - Validar configuração de monitor (target, offset)
- [ ] `validate_case_count()` - Validar número de casos (1 <= count <= max)

**Dependências:** pathlib, arquivo

**Status:** ⏳ Placeholders Criados - Pronto para Implementar

---

## 3. Serviço de Extração de Arquivos (src/utils/archive_service.py)

### ArchiveService

- [ ] `extract_archive()` - Extrair arquivo para diretório temporário
  - [ ] Suportar: zip, tar, tar.gz, tar.bz2, tar.xz, gz, bz2, xz
  - [ ] Criar diretório temporário isolado
  - [ ] Retornar Path ao diretório extraído

- [ ] `list_files()` - Listar arquivos em diretório extraído

- [ ] `find_dss_files()` - Encontrar todos os arquivos .dss

- [ ] `validate_archive_integrity()` - Validar arquivo não corrompido

**Dependências:** zipfile, tarfile, gzip, bz2, lzma, tempfile, Path

**Status:** ⏳ Placeholders Criados - Pronto para Implementar

---

## 4. Serviço de Parsing de Variáveis (src/utils/variable_parser.py)

### VariableParser

- [ ] `scan_files()` - Escanear diretório procurando por variáveis numéricas
  - [ ] Recursivo em todos os arquivos .dss e .txt
  - [ ] Retornar dict {file_path: [VariableSpec, ...]}

- [ ] `parse_numeric_variables()` - Extrair variáveis de um arquivo
  - [ ] Suportar formato key=value: `Vmaxpu = 1.05`
  - [ ] Suportar linhas simples com valores numéricos (.txt)
  - [ ] Rastrear ocorrências múltiplas da mesma chave
  - [ ] Retornar [VariableSpec]

- [ ] `parse_key_value()` - Parser para key=value
  - [ ] Regex: `([a-z][\w%]*)\s*=\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)`
  - [ ] Contar ocorrências para alinhamento de substituição

- [ ] `parse_line_values()` - Parser para linhas simples (.txt)
  - [ ] Cada linha não-vazia é um valor numérico
  - [ ] Retornar VariableSpec com line_number

- [ ] `group_by_file()` - Agrupar variáveis por arquivo de origem

**Dependências:** re, Path, defaultdict

**Status:** ⏳ Placeholders Criados - Pronto para Implementar

---

## 5. Serviço de Randomização (src/utils/randomization.py)

### RandomizationPlanner

- [ ] `build_plan()` - Construir plano de randomização
  - [ ] Receber lista de VariableSpec com threshold_pct
  - [ ] Retornar [RandomizationRule]

- [ ] `validate_plan()` - Validar plano
  - [ ] Verificar: cada variável tem threshold válido (0-100%)
  - [ ] Verificar: sem variáveis duplicadas

### ScenarioGenerator

- [ ] `generate_cases()` - Gerar N casos randomizados
  - [ ] Para cada caso: clone_scenario_structure() + apply_randomization()
  - [ ] Usar seed determinístico: `f"{filepath}-{case_idx}-{base_seed}"`
  - [ ] Retornar [SimulationCase]

- [ ] `clone_scenario_structure()` - Clonar diretório
  - [ ] Deep copy do diretório base
  - [ ] Criar em tempfile.mkdtemp(prefix="scenario_{idx}_")
  - [ ] Retornar Path ao clone

- [ ] `apply_randomization()` - Aplicar randomização
  - [ ] Para cada arquivo no plan:
    - [ ] Ler conteúdo
    - [ ] Aplicar replace_key_value() ou replace_line_value()
    - [ ] Escrever arquivo modificado

- [ ] `randomize_value()` - Randomizar valor único
  - [ ] Formula: `base_value × (1 ± random[0, threshold_pct/100])`
  - [ ] Usar RNG com seed: `Random(seed_material)`

- [ ] `replace_key_value()` - Substituir key=value em texto
  - [ ] Encontrar Nª ocorrência da chave (match_index)
  - [ ] Substituir valor
  - [ ] Retornar texto modificado

- [ ] `replace_line_value()` - Substituir valor em linha específica
  - [ ] Obter linha pelo número
  - [ ] Substituir primeiro valor numérico
  - [ ] Retornar texto modificado

**Dependências:** random, tempfile, shutil, re, Path

**Status:** ⏳ Placeholders Criados - Pronto para Implementar

---

## 6. Serviço de Executor (src/utils/executor.py)

### WorkerProcessAdapter

- [ ] `start_case()` - Executar caso em subprocesso isolado
  - [ ] Chamar: `python run_case_worker.py --main <path> --monitors <json>`
  - [ ] Capturar stdout/stderr
  - [ ] Parsear JSON resultado
  - [ ] Retornar CaseResult

- [ ] `read_json_result()` - Parsear JSON de worker
  - [ ] `json.loads(stdout)`
  - [ ] Tratamento de erro

- [ ] `handle_worker_error()` - Gerar mensagem de erro
  - [ ] Combinar stderr + returncode
  - [ ] Retornar string de erro legível

### ExecutionCoordinator

- [ ] `execute()` - Rotear para modo correto de execução
  - [ ] Se mode == "normal": run_parallel()
  - [ ] Se mode == "benchmark_serial_parallel": executar ambos
  - [ ] Se mode == "benchmark_incremental": run_incremental()

- [ ] `run_parallel()` - Executar casos em paralelo
  - [ ] Usar ThreadPoolExecutor
  - [ ] CPU count automático: `min(case_count, max(1, cpu_count))`
  - [ ] Para cada caso: WorkerProcessAdapter.start_case()
  - [ ] Medir tempo total
  - [ ] Retornar (results, workers_used)

- [ ] `run_serial()` - Executar sequencialmente
  - [ ] Para idx em 0..case_count:
    - [ ] WorkerProcessAdapter.start_case()
  - [ ] Medir tempo total
  - [ ] Retornar (results, 1)

- [ ] `run_incremental()` - Benchmark incremental
  - [ ] Para worker_count em 1..max_workers:
    - [ ] run_parallel(max_workers=worker_count)
    - [ ] Medir tempo
    - [ ] Registrar stats
  - [ ] Retornar (results, [{workers, seconds}, ...])

- [ ] `prepare_scenario_dirs()` - Preparar todos os cenários
  - [ ] Usar ScenarioGenerator.generate_cases()
  - [ ] Retornar [SimulationCase]

**Dependências:** subprocess, ThreadPoolExecutor, json, time, os

**Status:** ⏳ Placeholders Criados - Pronto para Implementar

---

## 7. Serviço de Análise (src/utils/analysis.py)

### ViolationAnalyzer

- [ ] `detect_violations()` - Detectar violações em todos os casos
  - [ ] Para cada case_result:
    - [ ] Para cada monitor:
      - [ ] Obter frame de dados
      - [ ] Comparar com MonitorLimit (target ± offset)
      - [ ] Contar valores fora do range
  - [ ] Retornar {monitor_name: {count, percentage}, ...}

- [ ] `count_violations_by_case()` - Contar violações por caso
  - [ ] Para cada case_result:
    - [ ] Somar violações em todos os monitores
  - [ ] Retornar [count, ...]

- [ ] `frequency_distribution()` - Distribuição de frequência
  - [ ] Contar quantos casos têm 0, 1, 2, ... violações
  - [ ] Retornar {n_violations: percentage, ...}

### ConfidenceIntervalAnalyzer

- [ ] `compute_mean_series()` - Média entre múltiplas séries
  - [ ] Alinhar índices (hora/iteração)
  - [ ] Média por índice
  - [ ] Retornar Series

- [ ] `compute_std_series()` - Desvio padrão
  - [ ] Idem mean
  - [ ] Retornar Series

- [ ] `compute_ci95()` - Intervalo de confiança 95%
  - [ ] CI = 1.96 × σ / √n
  - [ ] Retornar (lower, upper)

### BenchmarkAnalyzer

- [ ] `compare_serial_parallel()` - Comparar serial vs paralelo
  - [ ] Speedup = serial_time / parallel_time
  - [ ] Efficiency = speedup / workers
  - [ ] Gain% = (serial_time - parallel_time) / serial_time × 100
  - [ ] Retornar {speedup, efficiency, gain_pct, ...}

- [ ] `compute_speedup()` - Computar speedup
  - [ ] serial_time / parallel_time

- [ ] `build_scalability_curve()` - Curva de escalabilidade
  - [ ] Criar DataFrame: workers, seconds
  - [ ] Retornar DataFrame

### ResultProcessor

- [ ] `to_dataframes()` - Converter CaseResult em DataFrame
  - [ ] Para cada case_result:
    - [ ] Para cada monitor:
      - [ ] monitor_payload_to_frame()
  - [ ] Retornar {case_idx: {monitor_name: DataFrame, ...}}

- [ ] `normalize_monitor_data()` - Normalizar dados de monitor
  - [ ] columns + rows → DataFrame
  - [ ] Validar dimensões
  - [ ] Tipos corretos

- [ ] `compute_max_voltage()` - Máximo de tensão
  - [ ] Encontrar colunas V1, V2, V3, ...
  - [ ] max(V1, V2, V3) por amostra
  - [ ] Retornar Series

- [ ] `to_tidy_format()` - Formato tidy para visualização
  - [ ] Converter colunas em "series" (nome qualificado)
  - [ ] Formato: {hour, value, series, monitor, column}
  - [ ] Para visualização com Altair

**Dependências:** pandas, numpy

**Status:** ⏳ Placeholders Criados - Pronto para Implementar

---

## 8. Serviço de Visualização (src/utils/visualization.py)

### ChartBuilder

- [ ] `line_chart()` - Gráfico de linha
  - [ ] Usar Altair
  - [ ] X, Y, cor (opcional)
  - [ ] Título
  - [ ] Retornar alt.Chart

- [ ] `area_chart_ci()` - Gráfico de área com IC
  - [ ] Banda sombreada (lower, upper)
  - [ ] Linha da média
  - [ ] Retornar alt.LayerChart (band + line)

- [ ] `bar_chart()` - Gráfico de barras
  - [ ] Categorias, valores
  - [ ] Título
  - [ ] Retornar alt.Chart

### MetricsBuilder

- [ ] `violation_metrics()` - Cards de violações
  - [ ] Para cada monitor: "X / N cases"
  - [ ] Retornar [dict, ...]

- [ ] `benchmark_metrics()` - Sumário de benchmark
  - [ ] Serial time, parallel time, workers
  - [ ] Speedup, efficiency, gain%
  - [ ] Retornar dict

- [ ] `execution_summary()` - Sumário de execução
  - [ ] Total casos, sucesso, tempo, workers
  - [ ] Taxa de sucesso
  - [ ] Retornar dict

**Dependências:** altair, pandas

**Status:** ⏳ Placeholders Criados - Pronto para Implementar

---

## 9. Serviço de Gerenciamento Temporário (src/utils/temp_manager.py)

### TempFileManager

- [ ] `create_temp_dir()` - Criar diretório temporário
  - [ ] tempfile.mkdtemp(prefix=...)
  - [ ] Registrar para limpeza
  - [ ] Retornar Path

- [ ] `cleanup_dir()` - Deletar diretório
  - [ ] shutil.rmtree()
  - [ ] Ignorar erros

- [ ] `cleanup_all()` - Limpar todos os diretórios rastreados
  - [ ] Iterar _temp_dirs
  - [ ] cleanup_dir() para cada um

- [ ] `register_cleanup()` - Registrar para limpeza automática
  - [ ] Adicionar a _temp_dirs

**Comportamento:** Automático na saída com atexit.register()

**Status:** ⏳ Placeholders Criados - Pronto para Implementar

---

## 10. Serviço de Logging (src/utils/logger.py)

### LoggingService

- [ ] `setup()` - Configurar logging
  - [ ] Formato: timestamp, level, message
  - [ ] File handler (opcional)
  - [ ] Retornar logger configurado

- [ ] `get_logger()` - Obter logger singleton

- [ ] `info()`, `warning()`, `error()`, `debug()` - Métodos de log

- [ ] `track_run()` - Registrar execução
  - [ ] run_seed, case_count, mode
  - [ ] Timestamp

**Status:** ⏳ Placeholders Criados - Pronto para Implementar

---

## 11. Worker Isolado (src/utils/run_case_worker.py)

**Status:** ✅ Implementado Completo

---

## 12. Interface de Usuário - app.py (Página Principal)

### Estrutura Refatorizada

- [ ] `render_header()` - Cabeçalho com navegação
  - [ ] "Get Started", "Documentation" links
  - [ ] Logo/título

- [ ] `render_upload_section()` - Seção de upload
  - [ ] File uploader widget
  - [ ] Chamar ArchiveService.extract_archive()
  - [ ] Listar arquivos extraídos

- [ ] `render_dss_selection()` - Seleção de .dss
  - [ ] Selectbox com DSS files
  - [ ] Validação: arquivo existe

- [ ] `render_variable_selection()` - Seleção de variáveis
  - [ ] Checkboxes por variável
  - [ ] Number input para threshold
  - [ ] "Mark all" button
  - [ ] Agrupar por arquivo

- [ ] `render_execution_config()` - Configuração
  - [ ] Slider: número de casos
  - [ ] Radio: modo de execução (Normal, Benchmark Serial+Parallel, Incremental)

- [ ] `main()` - Fluxo principal
  - [ ] Integrar todas as funções
  - [ ] State management via st.session_state
  - [ ] Navegação para loading.py

**Status:** ⏳ Estrutura Criada - Pronto para Implementar

---

## 13. Interface de Usuário - pages/loading.py (Página de Execução)

### Estrutura Refatorizada

- [ ] `render_execution_controls()` - Controles de execução
  - [ ] Seleção de modo (Normal, Benchmark, Incremental)
  - [ ] Slider max_workers (para modo incremental)

- [ ] `render_monitor_selection()` - Seleção de monitores
  - [ ] Multiselect de monitores disponíveis
  - [ ] Target + Offset inputs para cada monitor

- [ ] `execute_simulation()` - Executar simulação
  - [ ] Chamar ExecutionCoordinator.execute()
  - [ ] Medir tempo
  - [ ] Capturar resultados
  - [ ] Armazenar em session_state

- [ ] `render_execution_stats()` - Exibir estatísticas
  - [ ] Tempo total, workers usados
  - [ ] Gain% (se benchmark)
  - [ ] Taxa de sucesso

- [ ] `render_results_section()` - Seção de resultados
  - [ ] Seletor de caso
  - [ ] Toggle: Tabela vs Gráfico
  - [ ] Exibir dados/gráficos

- [ ] `render_table_view()` - Visualização em tabela
  - [ ] DataFrame com dados do monitor
  - [ ] st.dataframe()

- [ ] `render_chart_view()` - Visualização em gráfico
  - [ ] Checkboxes para selecionar séries
  - [ ] ChartBuilder.line_chart()
  - [ ] st.altair_chart()

- [ ] `render_violation_analysis()` - Análise de violações
  - [ ] Cards com overflow counts
  - [ ] Gráfico de frequência

- [ ] `render_confidence_interval()` - Intervalo de confiança
  - [ ] Seletor de monitor
  - [ ] ChartBuilder.area_chart_ci()
  - [ ] st.altair_chart()

- [ ] `render_export_section()` - Exportação
  - [ ] Download button para ZIP do cenário

- [ ] `main()` - Fluxo principal
  - [ ] Validação de dados pendentes
  - [ ] Seleção de modo
  - [ ] Execução
  - [ ] Exibição de resultados

**Status:** ⏳ Estrutura Criada (referência do código antigo) - Pronto para Refatorar

---

## 14. Testes Automatizados (tests/)

- [ ] `test_validators.py`
  - [ ] Testes para InputValidator

- [ ] `test_archive_service.py`
  - [ ] Testes para ArchiveService

- [ ] `test_variable_parser.py`
  - [ ] Testes para VariableParser

- [ ] `test_randomization.py`
  - [ ] Testes para RandomizationPlanner e ScenarioGenerator

- [ ] `test_executor.py`
  - [ ] Testes para ExecutionCoordinator

- [ ] `test_analysis.py`
  - [ ] Testes para ViolationAnalyzer, ConfidenceIntervalAnalyzer

- [ ] `conftest.py`
  - [ ] Fixtures compartilhadas
  - [ ] Mock de OpenDSS

- [ ] `pytest.ini` ou `setup.cfg`
  - [ ] Configuração de pytest

**Meta:** >70% cobertura de código

**Status:** ⏳ A Criar

---

## 15. Documentação e CI/CD

- [ ] `README.md` - Atualizar com arquitetura refatorada

- [ ] `.github/workflows/ci.yml`
  - [ ] Testes: `pytest`
  - [ ] Lint: `flake8`, `black`
  - [ ] Type check: `mypy`

- [ ] `setup.py` ou `pyproject.toml`
  - [ ] Configuração de pacote

- [ ] `requirements.txt` - Finalizado (já existe)

- [ ] `IMPLEMENTACAO.md` - Este arquivo (atualizar conforme progresso)

**Status:** ⏳ Parcialmente Criado

---

## 📊 Resumo de Progresso

| Componente | Status | Prioridade |
|-----------|--------|-----------|
| **Modelos** | ✅ Criado | P0 |
| **Validators** | ⏳ Placeholder | P1 |
| **ArchiveService** | ⏳ Placeholder | P1 |
| **VariableParser** | ⏳ Placeholder | P1 |
| **Randomization** | ⏳ Placeholder | P1 |
| **Executor** | ⏳ Placeholder | P0 |
| **Analysis** | ⏳ Placeholder | P2 |
| **Visualization** | ⏳ Placeholder | P2 |
| **TempManager** | ⏳ Placeholder | P1 |
| **Logger** | ⏳ Placeholder | P3 |
| **Worker** | ✅ Implementado | P0 |
| **app.py** | ⏳ Parcialmente | P1 |
| **loading.py** | ⏳ Parcialmente | P1 |
| **Testes** | ❌ Não Iniciado | P2 |
| **CI/CD** | ❌ Não Iniciado | P3 |

---

## 🎯 Roteiro de Implementação Sugerido

### Fase 1: Core Services (Semana 1)
1. InputValidator
2. ArchiveService
3. VariableParser
4. TempFileManager

### Fase 2: Execução (Semana 2)
1. RandomizationPlanner & ScenarioGenerator
2. WorkerProcessAdapter & ExecutionCoordinator
3. Logger

### Fase 3: Análise e Visualização (Semana 3)
1. ViolationAnalyzer
2. ConfidenceIntervalAnalyzer
3. BenchmarkAnalyzer
4. ResultProcessor
5. ChartBuilder & MetricsBuilder

### Fase 4: UI Refactoring (Semana 4)
1. app.py - Integrar todos os services
2. loading.py - Integrar execução e visualização

### Fase 5: Testes e Polish (Semana 5)
1. Testes unitários
2. Testes de integração
3. CI/CD setup
4. Documentação final

---

**Última Atualização:** 2026-06-11
**Versão:** 1.0
