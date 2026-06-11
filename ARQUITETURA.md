# 🏗️ Arquitetura de Software - OpenDSS MultiThread

## Diagrama de Arquitetura em Camadas

```mermaid
graph TB
    subgraph UI["📱 Camada de Apresentação"]
        AppUI["AppUI<br/>(app.py)"]
        ResultsPage["ResultsPage<br/>(loading.py)"]
        SessionState["SessionStateManager<br/>(st.session_state)"]
    end

    subgraph Services["🔧 Camada de Serviços"]
        Archive["ArchiveService"]
        VarParser["VariableParser"]
        Validator["InputValidator"]
        RandomPlan["RandomizationPlanner"]
        ScenGen["ScenarioGenerator"]
        Monitor["MonitorConfigService"]
        Executor["ExecutionCoordinator"]
        WorkerAdapter["WorkerProcessAdapter"]
        
        ResultProc["ResultProcessor"]
        ViolAnalyzer["ViolationAnalyzer"]
        CIAnalyzer["ConfidenceIntervalAnalyzer"]
        BenchAnalyzer["BenchmarkAnalyzer"]
        
        ChartBuilder["ChartBuilder"]
        MetricsBuilder["MetricsBuilder"]
        ExportService["ExportService"]
        
        TempMgr["TempFileManager"]
        Logger["LoggingService"]
    end

    subgraph Domain["📦 Camada de Domínio"]
        VarSpec["VariableSpec"]
        RandRule["RandomizationRule"]
        MonitorLimit["MonitorLimit"]
        SimCase["SimulationCase"]
        CaseResult["CaseResult"]
        MonitorDataset["MonitorDataset"]
    end

    subgraph External["🔗 Camada Externa"]
        OpenDSSWorker["OpenDSSWorker<br/>(run_case_worker.py)"]
        OpenDSSLib["OpenDSS COM/API"]
        TempFS["Temp FileSystem"]
    end

    %% UI → Services
    AppUI -->|upload_file| Archive
    AppUI -->|extract_dir| Archive
    AppUI -->|find_main_file| Archive
    AppUI -->|parse_vars| VarParser
    Archive -->|validate_archive| Validator
    
    VarParser -->|validate_vars| Validator
    VarParser -->|produce| VarSpec
    
    AppUI -->|build_plan| RandomPlan
    RandomPlan -->|consume| VarSpec
    RandomPlan -->|produce| RandRule
    
    AppUI -->|generate_cases| ScenGen
    ScenGen -->|consume| RandRule
    ScenGen -->|create_temp_dir| TempMgr
    ScenGen -->|produce| SimCase
    
    AppUI -->|load_monitors| Monitor
    Monitor -->|validate_config| Validator
    Monitor -->|produce| MonitorLimit
    
    AppUI -->|execute| Executor
    Executor -->|orchestrate| WorkerAdapter
    Executor -->|log_event| Logger
    
    %% Services → Domain
    RandomPlan -->|create| RandRule
    Archive -->|create| VarSpec
    Monitor -->|create| MonitorLimit
    Executor -->|create| SimCase
    
    %% Worker Adapter → External
    WorkerAdapter -->|start_subprocess| OpenDSSWorker
    WorkerAdapter -->|capture_json| OpenDSSWorker
    WorkerAdapter -->|handle_error| Logger
    
    OpenDSSWorker -->|execute| OpenDSSLib
    OpenDSSWorker -->|read_files| TempFS
    
    %% Results Processing
    Executor -->|return_result| ResultProc
    ResultProc -->|produce| CaseResult
    ResultProc -->|parse_json| MonitorDataset
    
    CaseResult -->|analyze| ViolAnalyzer
    CaseResult -->|analyze| CIAnalyzer
    CaseResult -->|analyze| BenchAnalyzer
    
    %% Visualization
    ResultProc -->|build_chart| ChartBuilder
    ViolAnalyzer -->|build_metrics| MetricsBuilder
    CIAnalyzer -->|build_chart| ChartBuilder
    BenchAnalyzer -->|build_chart| ChartBuilder
    
    %% Results Page
    ResultsPage -->|query_results| SessionState
    ResultsPage -->|render| ChartBuilder
    ResultsPage -->|render| MetricsBuilder
    ResultsPage -->|export| ExportService
    
    ExportService -->|consume| SimCase
    ExportService -->|consume| CaseResult
    ExportService -->|zip_files| TempFS
    
    %% Cleanup
    TempMgr -->|manage_dirs| TempFS
    Logger -->|file_io| TempFS
    
    style UI fill:#e1f5ff
    style Services fill:#fff3e0
    style Domain fill:#f3e5f5
    style External fill:#e8f5e9
```

## Diagrama de Fluxo de Dados

```mermaid
graph LR
    subgraph Input["📥 Entrada"]
        File["Arquivo .zip<br/>ou .tar"]
    end

    subgraph Processing["⚙️ Processamento"]
        Extract["Extração"]
        Parse["Parsing<br/>Variáveis"]
        Randomize["Randomização<br/>N Casos"]
        Execute["Execução<br/>Paralela"]
        Aggregate["Agregação<br/>Resultados"]
    end

    subgraph Analysis["📊 Análise"]
        Violations["Detector<br/>Violações"]
        Stats["Estatísticas<br/>CI 95%"]
        Benchmark["Análise<br/>Performance"]
    end

    subgraph Output["📤 Saída"]
        Table["Tabelas"]
        Charts["Gráficos"]
        Export["Download ZIP"]
    end

    File -->|ArchiveService| Extract
    Extract -->|VariableParser| Parse
    Parse -->|RandomizationPlanner| Randomize
    Randomize -->|ExecutionCoordinator| Execute
    Execute -->|ResultProcessor| Aggregate
    
    Aggregate -->|ViolationAnalyzer| Violations
    Aggregate -->|ConfidenceIntervalAnalyzer| Stats
    Aggregate -->|BenchmarkAnalyzer| Benchmark
    
    Violations -->|MetricsBuilder| Output
    Stats -->|ChartBuilder| Output
    Benchmark -->|ChartBuilder| Output
    Aggregate -->|ExportService| Export

    style Input fill:#c8e6c9
    style Processing fill:#bbdefb
    style Analysis fill:#ffe0b2
    style Output fill:#f8bbd0
```

## Diagrama de Componentes por Módulo

```mermaid
graph TB
    subgraph app["📄 app.py - Página Principal"]
        AppLogic["Lógica de UI<br/>Upload e Seleção"]
        AppState["Gerenciamento<br/>Session State"]
        AppValidate["Validação<br/>Input"]
    end

    subgraph loading["📄 loading.py - Execução e Resultados"]
        LoadUI["Lógica de UI<br/>Execução"]
        LoadState["Gerenciamento<br/>Execution State"]
        LoadViz["Renderização<br/>Gráficos"]
    end

    subgraph utils_archive["📦 utils/archive_service.py"]
        ArchiveLogic["extract_archive()"]
        ArchiveList["list_files()"]
        ArchiveFind["find_dss_files()"]
    end

    subgraph utils_parser["📦 utils/variable_parser.py"]
        ParserScan["scan_files()"]
        ParserParse["parse_numeric_variables()"]
        ParserGroup["group_by_file()"]
    end

    subgraph utils_randomize["📦 utils/randomization.py"]
        RandPlan["build_plan()"]
        RandGenerate["generate_cases()"]
        RandApply["apply_randomization()"]
    end

    subgraph utils_execute["📦 utils/executor.py"]
        ExecParallel["run_cases_parallel()"]
        ExecSerial["run_cases_serial()"]
        ExecBench["run_benchmark_incremental()"]
    end

    subgraph utils_worker["📦 utils/run_case_worker.py"]
        WorkerMain["main()"]
        WorkerSolve["solve()"]
        WorkerSerialize["serialize_monitor()"]
    end

    subgraph utils_analysis["📦 utils/analysis.py"]
        AnalysisViolation["detect_violations()"]
        AnalysisCI["compute_confidence_interval()"]
        AnalysisBench["compute_speedup()"]
    end

    subgraph utils_viz["📦 utils/visualization.py"]
        VizLine["build_line_chart()"]
        VizArea["build_confidence_area()"]
        VizBar["build_violation_bars()"]
    end

    app -->|chamadas| AppLogic
    app -->|lê/escreve| AppState
    app -->|valida| AppValidate

    loading -->|chamadas| LoadUI
    loading -->|lê/escreve| LoadState
    loading -->|renderiza| LoadViz

    AppLogic -->|importa| utils_archive
    AppLogic -->|importa| utils_parser
    AppLogic -->|importa| utils_randomize

    LoadUI -->|importa| utils_execute
    LoadUI -->|importa| utils_analysis
    LoadUI -->|importa| utils_viz

    utils_archive -->|retorna arquivos| AppState
    utils_parser -->|retorna variáveis| AppState
    utils_randomize -->|cria casos| TempFS["Temp Dir"]

    utils_execute -->|executa| utils_worker
    utils_execute -->|retorna resultados| LoadState

    utils_worker -->|chama| OpenDSS["OpenDSS<br/>COM/API"]

    utils_analysis -->|analisa| LoadState
    LoadState -->|dados| utils_viz
    utils_viz -->|Altair| LoadUI

    style app fill:#e3f2fd
    style loading fill:#f3e5f5
    style utils_archive fill:#fff3e0
    style utils_parser fill:#fff3e0
    style utils_randomize fill:#fff3e0
    style utils_execute fill:#fff3e0
    style utils_worker fill:#c8e6c9
    style utils_analysis fill:#fff3e0
    style utils_viz fill:#fff3e0
```

## Diagrama de Sequência - Fluxo Completo

```mermaid
sequenceDiagram
    participant User as Usuário
    participant UI as AppUI
    participant Archive as ArchiveService
    participant Parser as VariableParser
    participant RandomPlan as RandomizationPlanner
    participant Executor as ExecutionCoordinator
    participant WorkerAdapter as WorkerProcessAdapter
    participant Worker as OpenDSSWorker
    participant ResultsUI as ResultsPage

    User->>UI: Upload arquivo .zip
    UI->>Archive: extract_archive(file)
    Archive-->>UI: extracted_files[]
    
    UI->>Archive: find_dss_files(dir)
    Archive-->>UI: dss_files[]
    
    User->>UI: Seleciona main_file.dss
    
    UI->>Parser: parse_numeric_variables(dir)
    Parser-->>UI: variables_by_file{}
    
    User->>UI: Marca variáveis + percentuais
    User->>UI: Clica "Gerar casos e carregar"
    
    UI->>RandomPlan: build_plan(selected_vars)
    RandomPlan-->>UI: randomization_plan[]
    
    UI->>Executor: execute(mode='parallel', cases=10)
    
    loop Para cada caso (paralelo)
        Executor->>WorkerAdapter: start_case(case_index, dir, monitors)
        WorkerAdapter->>Worker: subprocess.run([run_case_worker.py, --main, path])
        Worker->>Worker: dss.Basic.ClearAll()
        Worker->>Worker: dss.Text.Command(redirect path)
        Worker->>Worker: dss.Monitors.SaveAll()
        Worker-->>WorkerAdapter: JSON resultado
        WorkerAdapter-->>Executor: CaseResult{case, data, monitors}
    end
    
    Executor-->>UI: results[]
    UI->>UI: st.session_state['solver_result'] = results
    UI->>ResultsUI: st.switch_page('pages/loading.py')
    
    ResultsUI->>ResultsUI: Renderiza tabelas
    ResultsUI->>ResultsUI: Renderiza gráficos
    ResultsUI->>ResultsUI: Calcula CI 95%
    ResultsUI->>ResultsUI: Detecta violações
    
    User->>ResultsUI: Seleciona caso
    ResultsUI->>ResultsUI: build_case_chart_frame()
    ResultsUI-->>User: Visualização
    
    User->>ResultsUI: Clica "Baixar cenário"
    ResultsUI->>ExportService: export_case_zip(scenario_dir)
    ExportService-->>User: download cenario_X.zip
```

## Diagrama de Dependências de Classe

```mermaid
graph TB
    AppUI["<b>AppUI</b><br/>+ render_home()<br/>+ handle_upload()<br/>+ handle_randomization()"]
    
    SessionState["<b>SessionStateManager</b><br/>+ get key<br/>+ set key<br/>+ initialize()"]
    
    Archive["<b>ArchiveService</b><br/>+ extract_archive<br/>+ list_files<br/>+ find_dss_files"]
    
    Parser["<b>VariableParser</b><br/>+ scan_files<br/>+ parse_numeric_variables<br/>+ group_by_file"]
    
    Validator["<b>InputValidator</b><br/>+ validate_archive<br/>+ validate_dss<br/>+ validate_config"]
    
    RandomPlan["<b>RandomizationPlanner</b><br/>+ build_plan<br/>+ validate_plan"]
    
    ScenGen["<b>ScenarioGenerator</b><br/>+ generate_cases<br/>+ clone_structure<br/>+ apply_randomization"]
    
    Monitor["<b>MonitorConfigService</b><br/>+ load_available<br/>+ validate_limits"]
    
    Executor["<b>ExecutionCoordinator</b><br/>+ execute<br/>+ run_parallel<br/>+ run_serial<br/>+ run_incremental"]
    
    WorkerAdapter["<b>WorkerProcessAdapter</b><br/>+ start_case<br/>+ read_result<br/>+ handle_error"]
    
    ResultProc["<b>ResultProcessor</b><br/>+ to_dataframes<br/>+ normalize_data<br/>+ to_tidy_format"]
    
    ViolAnalyzer["<b>ViolationAnalyzer</b><br/>+ detect_violations<br/>+ count_by_case<br/>+ frequency_dist"]
    
    CIAnalyzer["<b>ConfidenceIntervalAnalyzer</b><br/>+ compute_mean<br/>+ compute_ci95"]
    
    BenchAnalyzer["<b>BenchmarkAnalyzer</b><br/>+ compare_times<br/>+ compute_speedup"]
    
    ChartBuilder["<b>ChartBuilder</b><br/>+ line_chart<br/>+ area_chart<br/>+ bar_chart"]
    
    MetricsBuilder["<b>MetricsBuilder</b><br/>+ violation_metrics<br/>+ benchmark_metrics"]
    
    TempMgr["<b>TempFileManager</b><br/>+ create_dir<br/>+ cleanup_dir<br/>+ cleanup_on_exit"]
    
    Logger["<b>LoggingService</b><br/>+ info<br/>+ warning<br/>+ error<br/>+ track_run"]
    
    VarSpec["VarSpec"]
    RandRule["RandRule"]
    MonitorLimit["MonitorLimit"]
    SimCase["SimCase"]
    CaseResult["CaseResult"]
    
    AppUI --> SessionState
    AppUI --> Archive
    AppUI --> Parser
    AppUI --> Validator
    AppUI --> RandomPlan
    AppUI --> ScenGen
    AppUI --> Monitor
    AppUI --> Executor
    AppUI --> Logger
    
    Archive --> Validator
    Archive --> VarSpec
    
    Parser --> VarSpec
    Parser --> Validator
    
    RandomPlan --> RandRule
    RandomPlan --> Validator
    
    ScenGen --> RandRule
    ScenGen --> SimCase
    ScenGen --> TempMgr
    
    Monitor --> MonitorLimit
    Monitor --> Validator
    
    Executor --> WorkerAdapter
    Executor --> SimCase
    Executor --> Logger
    
    WorkerAdapter --> CaseResult
    
    ResultProc --> CaseResult
    
    ViolAnalyzer --> CaseResult
    ViolAnalyzer --> MonitorLimit
    
    CIAnalyzer --> CaseResult
    BenchAnalyzer --> CaseResult
    
    ChartBuilder --> CaseResult
    MetricsBuilder --> CaseResult
    
    ExportService["<b>ExportService</b><br/>+ export_zip"] --> SimCase
    ExportService --> CaseResult
    ExportService --> TempMgr
    
    ResultsPage["<b>ResultsPage</b>"] --> SessionState
    ResultsPage --> ResultProc
    ResultsPage --> ViolAnalyzer
    ResultsPage --> CIAnalyzer
    ResultsPage --> BenchAnalyzer
    ResultsPage --> ChartBuilder
    ResultsPage --> MetricsBuilder
    ResultsPage --> ExportService
    
    style AppUI fill:#bbdefb
    style SessionState fill:#bbdefb
    style Archive fill:#ffe0b2
    style Parser fill:#ffe0b2
    style Validator fill:#ffe0b2
    style RandomPlan fill:#ffe0b2
    style ScenGen fill:#ffe0b2
    style Monitor fill:#ffe0b2
    style Executor fill:#ffe0b2
    style WorkerAdapter fill:#ffe0b2
    style ResultProc fill:#ffe0b2
    style ViolAnalyzer fill:#ffe0b2
    style CIAnalyzer fill:#ffe0b2
    style BenchAnalyzer fill:#ffe0b2
    style ChartBuilder fill:#ffe0b2
    style MetricsBuilder fill:#ffe0b2
    style TempMgr fill:#ffe0b2
    style Logger fill:#ffe0b2
    style ResultsPage fill:#bbdefb
    style ExportService fill:#ffe0b2
    style VarSpec fill:#f3e5f5
    style RandRule fill:#f3e5f5
    style MonitorLimit fill:#f3e5f5
    style SimCase fill:#f3e5f5
    style CaseResult fill:#f3e5f5
```

## Padrões de Design Utilizados

| Padrão | Componente | Propósito |
|--------|-----------|----------|
| **Service Layer** | ArchiveService, VariableParser, Executor | Encapsular lógica de negócio |
| **Adapter** | WorkerProcessAdapter | Abstrair comunicação com subprocesso |
| **Factory** | ScenarioGenerator | Criar instâncias de casos |
| **Coordinator** | ExecutionCoordinator | Orquestrar múltiplos serviços |
| **State** | SessionStateManager | Gerenciar estado da aplicação |
| **Validator** | InputValidator | Validar input em um único lugar |
| **Builder** | ChartBuilder, MetricsBuilder | Construir visualizações complexas |
| **Strategy** | run_parallel, run_serial, run_incremental | Diferentes estratégias de execução |

---

**Versão:** 1.0  
**Data:** 2026-06-11  
**Status:** Pronto para DrawIO
