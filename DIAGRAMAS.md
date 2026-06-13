# 📐 Diagramas - OpenDSS MultiThread

## 1. Arquitetura Geral (Simplificada)

```mermaid
graph TB
    UI[UI Layer<br/>Streamlit]
    SVC[Service Layer<br/>Core Logic]
    DOM[Domain Model<br/>Data Objects]
    EXT[External<br/>OpenDSS/Files]
    
    UI -->|calls| SVC
    SVC -->|creates/uses| DOM
    SVC -->|interacts| EXT
    EXT -->|returns| DOM
    DOM -->|renders| UI
```

## 2. Pipeline de Processamento

```mermaid
graph LR
    A["📁 Upload<br/>Archive"] --> B["📂 Extract<br/>Archive"]
    B --> C["🔍 Parse<br/>Variables"]
    C --> D["🎲 Randomize<br/>Cases"]
    D --> E["⚙️ Execute<br/>Parallel"]
    E --> F["📊 Analyze<br/>Results"]
    F --> G["📈 Visualize<br/>Charts"]
    
    style A fill:#c8e6c9
    style E fill:#bbdefb
    style F fill:#ffe0b2
    style G fill:#f8bbd0
```

## 3. Estrutura de Diretórios

```
OpenDSSMultiThread/
│
├── src/
│   ├── app.py                      # Página principal (upload + config)
│   ├── pages/
│   │   └── loading.py              # Página de execução e resultados
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── run_case_worker.py      # Subprocesso isolado (OpenDSS)
│   │   ├── archive_service.py      # Extração e manipulação de arquivos
│   │   ├── variable_parser.py      # Parsing de variáveis numéricas
│   │   ├── randomization.py        # Geração de casos randomizados
│   │   ├── executor.py             # Orquestração de execução (serial/paralelo)
│   │   ├── analysis.py             # Análises (violações, CI, benchmark)
│   │   └── visualization.py        # Construção de gráficos
│   └── requirements.txt
│
├── data/
│   └── examples/                   # Datasets de exemplo
│
├── tests/
│   └── test_*.py                   # Testes automatizados
│
├── .github/
│   └── workflows/                  # CI/CD (GitHub Actions)
│
├── ESPECIFICACAO.md                # Requisitos funcionais/não-funcionais
├── ARQUITETURA.md                  # Diagramas de arquitetura detalhados
├── DIAGRAMAS.md                    # Este arquivo (diagramas rápidos)
└── README.md                       # Documentação geral
```

## 4. Estado da Aplicação (Session State)

```mermaid
graph LR
    SS["Session State"]
    
    SS --> UP["Upload & Extraction<br/>pending_main_file<br/>pending_extract_dir<br/>parsed_variables"]
    SS --> RZ["Randomization<br/>pending_random_plan<br/>pending_case_count"]
    SS --> MON["Monitors<br/>pending_selected_monitors<br/>pending_monitor_offsets<br/>pending_monitor_targets"]
    SS --> RES["Results<br/>solver_result<br/>last_parallel_duration<br/>last_workers_used"]
    SS --> UI["UI State<br/>results_view_mode<br/>selected_result_case"]
    
    style SS fill:#e1f5ff
    style UP fill:#fff3e0
    style RZ fill:#fff3e0
    style MON fill:#fff3e0
    style RES fill:#fff3e0
    style UI fill:#fff3e0
```

## 5. Fluxo do Usuário

```mermaid
graph TD
    A["🏠 Home Page<br/>app.py"] --> B["📤 Upload .zip/.tar"]
    B --> C["✅ Select Main .dss"]
    C --> D["🔍 Parse Variables"]
    D --> E["🎲 Select & Configure"]
    E --> F["⚡ Generate Cases"]
    F --> G["▶️ Loading Page<br/>loading.py"]
    G --> H["⏳ Execute Simulation"]
    H --> I["📊 View Results"]
    I --> J{View Mode?}
    J -->|Table| K["📋 Data Table"]
    J -->|Chart| L["📉 Line Chart"]
    K --> M["📥 Download Scenario"]
    L --> M
    M --> N["🎉 Export .zip"]
    
    style A fill:#bbdefb
    style G fill:#ffe0b2
    style I fill:#f8bbd0
    style N fill:#c8e6c9
```

## 6. Ciclo de Vida de um Caso

```mermaid
graph TB
    A["Case 1..N<br/>to Execute"] --> B["📂 Clone Base Dir"]
    B --> C["🎲 Apply Randomization<br/>seed_material = hash"]
    C --> D["🚀 Spawn Subprocess<br/>run_case_worker.py"]
    D --> E["🔄 OpenDSS Execution<br/>redirect main.dss"]
    E --> F["📊 Collect Monitor Data<br/>SaveAll() + Serialize"]
    F --> G["📤 Return JSON Result"]
    G --> H["💾 Store in Results[]"]
    H --> I["🧹 Cleanup Temp Dir"]
    
    style A fill:#bbdefb
    style D fill:#c8e6c9
    style E fill:#c8e6c9
    style F fill:#c8e6c9
    style H fill:#ffe0b2
    style I fill:#ffe0b2
```

## 7. Execução Serial vs. Paralela vs. Incremental

```mermaid
graph TB
    subgraph SERIAL["Serial (1 Worker)"]
        S1["Case 1"] --> S2["Case 2"] --> S3["Case 3"]
    end
    
    subgraph PARALLEL["Parallel (4 Workers)"]
        P1["Case 1"]
        P2["Case 2"]
        P3["Case 3"]
        P4["Case 4"]
    end
    
    subgraph INCREMENTAL["Incremental (1->2->3->4)"]
        I1["Workers=1"]
        I2["Workers=2"]
        I3["Workers=3"]
        I4["Workers=4"]
    end
    
    SERIAL -.->|Tempo: 3T| OUT1
    PARALLEL -.->|Tempo: ~T| OUT2
    INCREMENTAL -.->|Medir cada| OUT3
    
    OUT1["Result"]
    OUT2["Result"]
    OUT3["Scalability Curve"]
    
    style SERIAL fill:#ffcccc
    style PARALLEL fill:#ccffcc
    style INCREMENTAL fill:#ccccff
```

## 8. Análise de Violações

```mermaid
graph TB
    RES["Results<br/>10 Cases"]
    RES --> ANA["Violation Analysis"]
    
    ANA --> V1["Monitor 1:<br/>2 / 10 cases"]
    ANA --> V2["Monitor 2:<br/>5 / 10 cases"]
    ANA --> V3["Monitor 3:<br/>1 / 10 cases"]
    
    ANA --> FREQ["Frequency Distribution"]
    FREQ --> F1["0 violations: 3 cases (30%)"]
    FREQ --> F2["1 violation: 4 cases (40%)"]
    FREQ --> F3["2+ violations: 3 cases (30%)"]
    
    style RES fill:#e1f5ff
    style ANA fill:#fff3e0
    style V1 fill:#ffebee
    style V2 fill:#ffebee
    style V3 fill:#ffebee
    style FREQ fill:#ffe0b2
```

## 9. Intervalo de Confiança (CI 95%)

```mermaid
graph TB
    RES["Results<br/>N Cases"]
    RES --> SEL["Select Monitor"]
    SEL --> CALC["For Each Hour/Iteration"]
    
    CALC --> MEAN["Mean = avg(all_cases)"]
    CALC --> STD["StdDev = σ(all_cases)"]
    CALC --> CI["CI = 1.96 × σ/√n"]
    
    MEAN --> VIZ["Visualize"]
    CI --> VIZ
    
    VIZ --> AREA["Shaded Area<br/>Upper = Mean + CI<br/>Lower = Mean - CI"]
    VIZ --> LINE["Line<br/>Mean Value"]
    
    style VIZ fill:#fff3e0
    style AREA fill:#e3f2fd
    style LINE fill:#e3f2fd
```

## 10. Estrutura de Dados - CaseResult

```mermaid
graph TB
    CR["CaseResult"]
    
    CR --> C["case: int (1..N)"]
    CR --> D["data: dict"]
    CR --> M["monitors: list[str]"]
    CR --> SD["scenario_dir: str"]
    CR --> E["error: str | None"]
    
    D --> D1["Monitor1"]
    D --> D2["Monitor2"]
    
    D1 --> D1C["columns: [sample, hour, V1, V2, ...]"]
    D1 --> D1R["rows: [[0, 0.0, 100, 101, ...], ...]"]
    
    style CR fill:#f3e5f5
    style C fill:#e1bee7
    style D fill:#e1bee7
    style M fill:#e1bee7
    style SD fill:#e1bee7
    style E fill:#e1bee7
```

## 11. Interações Usuário × Sistema (Activity Diagram)

```mermaid
stateDiagram-v2
    [*] --> Home: Visita app
    
    Home --> Upload: Seleciona arquivo
    Upload --> Extract: Arquivo enviado
    Extract --> SelectDSS: Extração OK
    SelectDSS --> ParseVars: .dss selecionado
    ParseVars --> SelectVars: Parsing OK
    SelectVars --> Configure: Variáveis listadas
    Configure --> Generate: Config OK
    Generate --> Execute: Casos gerados
    Execute --> Loading: Execução inicia
    Loading --> Results: Execução OK
    
    Results --> ViewTable: Seleciona tabela
    Results --> ViewChart: Seleciona gráfico
    ViewTable --> ViewCI: Próxima seção
    ViewChart --> ViewCI
    ViewCI --> Export: Analisou resultado
    Export --> [*]: Baixou cenário
    
    Error --> Home: Erro ocorreu
```

## 12. Benchmarking - Curva de Escalabilidade

```
Workers (X) vs. Tempo (Y)

Tempo (s)
    ^
 90 |     ╱╲
 80 |    ╱  ╲___
 70 |   ╱       ╲
 60 |  ╱         ╲___
 50 | ╱              ╲__
 40 |╱                  
    +──────────────────────→ Workers
    1  2  3  4  5  6  7  8

Ideal (linear): tempo ↓ com mais workers
Real: plateau quando I/O ≥ CPU
```

## 13. Pipeline de Tratamento de Erros

```mermaid
graph TD
    ERR["Error Occurs"]
    
    ERR --> T1{Type?}
    
    T1 -->|Upload| E1["Archive<br/>Validation Failed"]
    T1 -->|Extract| E2["Extraction<br/>Failed"]
    T1 -->|Parse| E3["Variable Parsing<br/>Failed"]
    T1 -->|Execute| E4["Worker<br/>Subprocess Failed"]
    
    E1 --> LOG["Log Error"]
    E2 --> LOG
    E3 --> LOG
    E4 --> LOG
    
    LOG --> SHOW["Display User<br/>Friendly Message"]
    SHOW --> RECOVER{Recoverable?}
    RECOVER -->|Yes| HOME["Allow Retry"]
    RECOVER -->|No| STOP["Stop Execution"]
    
    HOME --> END((End))
    STOP --> END
    style ERR fill:#ffcccc
    style SHOW fill:#ffe0b2
```

## 14. Modelo de Dados - Variável Numérica

```mermaid
graph TB
    VS["VariableSpec"]
    
    VS --> ID["id: str<br/>e.g. 'kv-0'"]
    VS --> NAME["name: str<br/>e.g. 'Vmaxpu'"]
    VS --> VALUE["value: float<br/>e.g. 1.05"]
    VS --> LINE["line: int<br/>e.g. 42"]
    VS --> KIND["kind: str<br/>'key_value' | 'line_value'"]
    VS --> RELPATH["relative_path: str<br/>e.g. 'master.dss'"]
    VS --> MATCH["match_index: int<br/>e.g. 0 (1st occurrence)"]
    
    style VS fill:#f3e5f5
    style ID fill:#e1bee7
```

## 15. Integração OpenDSS

```mermaid
graph TB
    WORKER["run_case_worker.py<br/>Subprocess"]
    
    WORKER --> INIT["opendssdirect<br/>Import & Init"]
    INIT --> CLEAR["dss.Basic<br/>ClearAll()"]
    CLEAR --> REDIRECT["dss.Text<br/>Command(redirect)"]
    REDIRECT --> SOLVE["Auto-solve<br/>on Redirect"]
    SOLVE --> SAVEALL["dss.Monitors<br/>SaveAll()"]
    SAVEALL --> COLLECT["dss.Monitors<br/>AsMatrix()"]
    COLLECT --> SERIALIZE["to_serializable()<br/>JSON Encode"]
    SERIALIZE --> OUTPUT["print(JSON)<br/>stdout"]
    
    OUTPUT --> ADAPTER["WorkerProcessAdapter<br/>Capture stdout"]
    ADAPTER --> PARSE["json.loads()"]
    PARSE --> RESULT["CaseResult"]
    
    style WORKER fill:#c8e6c9
    style OUTPUT fill:#ffe0b2
    style RESULT fill:#f3e5f5
```

---

**Versão:** 1.0  
**Data:** 2026-06-06  
**Status:** Referência Inicial   para Desenvolvimento
