# 📋 Especificação Funcional e Não-Funcional - OpenDSS MultiThread

## 1. Visão Geral

**OpenDSS MultiThread** é uma plataforma web para execução paralela e análise otimizada de simulações do OpenDSS, permitindo que usuários executem múltiplas variações de casos de rede elétrica simultaneamente, coletando dados de monitores e gerando análises estatísticas robustas.

**Stack Tecnológico:**
- **Frontend/Backend:** Streamlit (Python)
- **Engine de Simulação:** OpenDSS (via `opendssdirect`)
- **Processamento Paralelo:** ThreadPoolExecutor + Subprocessos
- **Análise de Dados:** Pandas, NumPy
- **Visualização:** Altair

---

## 2. Requisitos Funcionais (RF)

### 2.1 Gerenciamento de Arquivos e Extração

**RF-001:** Upload de Arquivos Compactados
- O sistema deve aceitar arquivos compactados nos seguintes formatos:
  - `.zip`
  - `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz`, `.tbz2`, `.tar.xz`, `.txz`
  - `.gz`, `.bz2`, `.xz` (compressão simples)
- Máximo de tamanho a ser definido conforme ambiente (cliente Web)
- Extração deve ocorrer em diretório temporário isolado
- Exibição de lista de arquivos extraídos ao usuário

**RF-002:** Seleção de Arquivo Principal
- Após extração, sistema deve listar todos os arquivos `.dss` encontrados
- Usuário seleciona um arquivo `.dss` como arquivo principal da simulação. Isso é necessário pois será o parâmetro passado para o OPENDSS rodar o main correto;
- Validação: arquivo selecionado deve existir e ser acessível
- Feedback de erro se nenhum arquivo `.dss` for encontrado

**RF-003:** Parsing e Leitura de Variáveis Numéricas
- Sistema deve scanear todos os arquivos `.dss` e `.txt` no diretório extraído
- Extrair variáveis numéricas usando pattern regex:
  - Formato key-value: `KEY = valor` (ex: `Vmaxpu=1.05`)
  - Linhas de texto simples com valores numéricos
- Cada variável deve armazenar:
  - ID único
  - Nome/identificador
  - Valor atual
  - Número da linha
  - Tipo (key_value ou line_value)
  - Caminho relativo no arquivo
  - Índice de ocorrência (para múltiplas ocorrências da mesma chave)

### 2.2 Randomização de Variáveis

**RF-004:** Seleção e Configuração de Variáveis para Randomização
- Usuário seleciona quais variáveis deseja randomizar
- Para cada variável selecionada:
  - Definir percentual de limite de aleatoriedade (0-100%)
  - Variação = valor_base × (1 ± [0%, limite_pct])
  - Seed determinístico para reprodutibilidade
- Interface com checkboxes para seleção em massa por arquivo
- Botão "Marcar todas as variáveis"
- Gerenciar variáveis linkadas entre si

**RF-005:** Geração de Casos Randomizados
- Criar N casos paralelos com variações pseudo-aleatórias
- Cada caso:
  - Herda cópia completa da estrutura de arquivos extraída
  - Substitui valores nas variáveis selecionadas
  - Mantém determinismo via seed: `seed_material = f"{filepath}-{case_index}-{base_seed}"`
- Armazenar cada caso em diretório temporário isolado

### 2.3 Execução de Simulações

**RF-006:** Execução Serial de Casos
- Executar casos sequencialmente (1 por vez)
- Cada caso roda em subprocesso isolado via `run_case_worker.py`
- Medir tempo total de execução

**RF-007:** Execução Paralela de Casos
- Executar múltiplos casos simultaneamente usando `ThreadPoolExecutor`
- Número automático de workers baseado em quantas threads estão disponíveis
- Permitir override manual do máximo de workers
- Cada caso roda em subprocesso isolado (evita reentrância do OpenDSS)
- Medir tempo total paralelo e número de workers realmente utilizados

**RF-008:** Worker Isolado (Subprocesso OpenDSS)
- Arquivo `run_case_worker.py` executável standalone
- Aceita argumentos CLI:
  - `--main <path>`: arquivo .dss principal
  - `--monitors <json>`: lista JSON de nomes de monitores a capturar
- Executar OpenDSS com `redirect <main_path>`
- Salvar todos os monitores com `SaveAll()`
- Serializar dados de monitores selecionados em JSON
- Retornar JSON com estrutura:
  ```json
  {
    "ok": true/false,
    "result": {
      "monitors": ["Monitor1", "Monitor2"],
      "data": {
        "Monitor1": {
          "columns": [...],
          "rows": [...]
        }
      }
    },
    "error": "mensagem de erro (se ok=false)"
  }
  ```

### 2.4 Coleta e Processamento de Dados

**RF-009:** Coleta de Dados de Monitores
- Extrair matriz de dados de cada monitor
- Capturar headers (nomes das colunas)
- Incluir timestamps (hours)
- Estruturar como DataFrame com colunas: [sample, hour, ...headers]
- Validar alinhamento de dimensões

**RF-010:** Processamento de Séries Temporais
- Converter dados de monitores em DataFrames Pandas
- Identificar colunas de tensão (V1, V2, V3, etc.)
- Identificar colunas de valor (exclui sample, hour, ângulos)
- Calcular máximo de tensão por amostra
- Preparar dados para visualização em formato long (tidy data)

### 2.5 Análise de Violações

**RF-011:** Definição de Limites de Segurança
- Para cada monitor selecionado:
  - Valor desejado (target)
  - Offset máximo permitido (range: [target-offset, target+offset])
- Violação ocorre quando algum valor cai fora do range

**RF-012:** Detecção de Violações por Caso
- Para cada caso, contar quantos monitores têm violações
- Registrar contagem total de violações por caso
- Gerar estatísticas:
  - Medições que ocorreram violações, em comparação com todas as medições
  - Casos que ocorreram violações, em comparação com todos os casos
  - Quantidade de violações por monitor
  - Percentual de casos com violações
  - Distribuição de frequência de violações

### 2.6 Modos de Execução e Benchmarking

**RF-013:** Modo Normal
- Executar todos os casos em paralelo uma vez
- Exibir tempo total e workers utilizados

**RF-014:** Modo Benchmark (Serial + Paralelo)
- Executar casos com MESMO seed de forma serial
- Executar casos com MESMO seed de forma paralela
- Comparar tempos (ganho em percentual)
- Exibir informações e estatísticas de workers em cada modo

**RF-015:** Modo Benchmark Incremental
- Executar casos com 1 worker, depois 2, 3, ... até N
- Para cada valor de workers, medir tempo total
- Gerar série temporal: workers → tempo
- Visualizar curva de escalabilidade

### 2.7 Visualização de Resultados

**RF-016:** Seleção de Caso para Análise
- Dropdown com todos os casos executados
- Exibir resultado do caso (sucesso ou erro)

**RF-017:** Visualização em Tabela
- DataFrame com todos os dados de monitores do caso
- Incluir coluna de máxima tensão por amostra
- Paginação/scroll para grandes datasets
- Exportação de dados (CSV)

**RF-018:** Visualização em Gráfico
- Gráfico de linha com múltiplas séries
- Usuário seleciona quais séries exibir (checkboxes)
- Eixo X: hora/iteração
- Eixo Y: valor
- Usar Altair para visualização interativa

**RF-019:** Download de Cenário Randomizado
- Botão para baixar pasta do caso em ZIP
- Arquivo: `cenario_{case_number}_randomizado.zip`
- Incluir todos os arquivos modificados do cenário

### 2.8 Análises Estatísticas

**RF-020:** Intervalo de Confiança por Monitor
- Selecionar um monitor para análise
- Para cada hora/iteração:
  - Calcular média entre todos os casos
  - Calcular desvio padrão
  - Calcular intervalo de confiança 95% (1.96 × σ / √n)
  - Exibir: banda sombreada (IC) + linha (média)
- Checkbox que exibe linhas de TODAS as iterações ao mesmo tempo
- Usar Altair para visualização

**RF-021:** Frequência de Violações
- Gráfico de barras: número de violações → frequência (%)
- X: quantidade de violações por caso (0, 1, 2, ...)
- Y: percentual de casos com N violações

**RF-022:** Métricas de Overflow
- Exibir cards com:
  - Monitor name
  - Quantidade de casos com violação / total de casos
  - Help text explicando o significado

### 2.9 Persistência de Estado

**RF-023:** Session State Streamlit
- Armazenar em `st.session_state`:
  - Arquivo principal selecionado
  - Diretório extraído
  - Plano de randomização
  - Quantidade de casos
  - Monitores selecionados
  - Offsets e targets
  - Resultados de execução (com timestamps)
  - Modo de benchmark
  - Duração de execução
  - Workers utilizados
- Permitir user rerun sem perder dados

### 2.10 Tratamento de Erros

**RF-024:** Validação de Entrada
- Arquivo compactado: formato válido e não corrompido
- Arquivo principal: existe e é arquivo .dss
- Variáveis selecionadas: pelo menos 1 para randomização
- Monitores selecionados: pelo menos 1
- Casos : 1+ (validação numérica)

**RF-025:** Captura de Exceções
- Extração com try-catch e feedback de erro
- Execução de worker com captura de stderr/stdout
- Parsing de JSON do worker com fallback
- Display amigável de erros em componentes Streamlit

---

## 3. Requisitos Não-Funcionais (RNF)

### 3.1 Performance

**RNF-001:** Tempo de Extração
- Arquivo < 100 MB: extração em < 5 segundos
- Arquivo < 500 MB: extração em < 15 segundos
- Feedback visual de progresso

**RNF-002:** Comportamento durante parsing
- Não bloquear UI durante parsing

**RNF-003:** Escalabilidade de Cases
- Suportar até N casos paralelos (hardware permitting, onde N é o número de threads)
- ThreadPoolExecutor com ajuste dinâmico de workers

**RNF-004:** Tempo de Resposta de Interatividade
- Seleção de série em gráfico: < 500ms
- Toggle table/chart: < 1s
- Download de ZIP: < 10s para pasta de até 100 MB

### 3.2 Confiabilidade

**RNF-005:** Reprodutibilidade
- Seed determinístico para randomização
- Mesmas configurações + seed = mesmos resultados
- Seed gerado via `random.SystemRandom().getrandbits(64)`

**RNF-006:** Isolamento de Processos
- Cada caso roda em subprocesso único
- Falha em 1 caso não afeta outros, considerando que são independentes
- Timeout para subprocessos (5 min para cada iteração?)
- Captura de stack trace de exceções

**RNF-007:** Robustez de Dados
- Parser regex tolerante a espaços em branco e variações
- Tratamento de caracteres especiais em nomes de arquivo
- Sanitização de chaves de sessão Streamlit (replace "/", ":")
- Fallback para dados faltantes (NaN, fill_value)

**RNF-008:** Limpeza de Recursos
- Diretórios temporários criados com `tempfile.mkdtemp()`
- Implementar garbage collection
- Limitar retenção de dados na memória durante execução, casos muito grandes devem ser quebrados

### 3.3 Usabilidade

**RNF-009:** Interface Responsiva
- Layout adaptável para desktop/tablet
- Botões com state visual (disabled/loading)
- Uso de spinners para operações longas
- Feedback immediate (success/warning/error)

**RNF-010:** Navegação e Contexto
- Breadcrumb ou indicação de página atual (main → loading)
- Links "Get Started", "Documentation"
- Descrições claras de cada etapa
- Help text em inputs críticos

**RNF-011:** Internacionalização (Português)
- Interface em português brasileiro
- Mensagens de erro legíveis
- Rótulos de inputs explicativos

**RNF-012:** Acessibilidade
- Labels associados a inputs
- Cores de erro/sucesso + texto descritivo

### 3.4 Segurança

**RNF-013:** Validação de Input
- Rejeitar arquivos compactados > limiar de tamanho (ex: 500 MB)
- Verificar tipo MIME (se possível, verificar se é main)
- Limite de profundidade de diretórios extraídos

**RNF-014:** Execução Isolada
- Subprocessos OpenDSS rodando com permissões limitadas
- Sem acesso a diretórios sensíveis do sistema

**RNF-015:** Gestão de Segredos
- Nenhuma senha/token armazenado em sessão
- Logs sem informações sensíveis
- Diretórios temporários com permissões restritas (mode 0o700)

### 3.5 Manutenibilidade

**RNF-016:** Estrutura Modular
- Separação clara: UI  vs. lógica 
- Seguir GRASP e SOLID
- Docstrings para functions

**RNF-017:** Logging e Observabilidade
- Logs estruturados (não apenas prints)
- Níveis: DEBUG, INFO, WARNING, ERROR
- Rastreamento de IDs de execução (run_seed)
- Duração de operações críticas

**RNF-018:** Testabilidade
- Funções puras onde possível
- Mock de OpenDSS para testes unitários
- Fixtures para casos de teste (dados exemplo)
- Cobertura de teste: > 70%

**RNF-019:** Documentação
- README com instruções setup
- Docstrings em Python
- Exemplos de uso (datasets exemplo na pasta data/)
- CHANGELOG para versões

### 3.6 Compatibilidade

**RNF-020:** Compatibilidade de Plataforma
- Suporte a múltiplos CPU counts (ARM/x86)

**RNF-021:** Compatibilidade de OpenDSS
- OpenDSS versão 9.0+ (com automação COM/Python interface)
- Validar compatibilidade com `opendssdirect` >= 1.0.2

**RNF-022:** Compatibilidade de Dependências
- Python: 3.10 - 3.11 (3.12 quando estável)
- NumPy 1.24+
- Pandas 1.5+
- Streamlit 1.28+ (último stable)

### 3.7 Escalabilidade

**RNF-023:** Gestão do uso
- Cada sessão Streamlit isolada
- Diretórios temporários únicos por sessão
- Sem compartilhamento de estado global

**RNF-024:** Suporte a Grandes Datasets
- Monitor com 10k+ amostras: visualização sem lag
- Chunking de dados se necessário

### 3.8 Compliance e Regulamentação

**RNF-025:** Conformidade
- Nenhum requisito de LGPD (dados não identificam pessoas)
- Logs não persistem indefinidamente
- Opção de limpeza de cache de uploads

---

## 4. Casos de Uso

### CU-001: Simulação Básica
1. Usuário faz upload de arquivo .zip com circuito OpenDSS
2. Sistema extrai e apresenta arquivo .dss principal
3. Usuário seleciona variáveis (ex: Vmaxpu, Sbase)
4. Define percentual de variação (±10%)
5. Solicita execução de n casos paralelos
6. Sistema executa e exibe resultados (gráficos + tabelas)

### CU-002: Análise Comparativa Serial vs. Paralelo
1. Usuário segue CU-001 até seleção de modo
2. Escolhe "Benchmark (serial + paralelo)"
3. Sistema executa mesma configuração nos 2 modos
4. Compara tempos e calcula ganho percentual
5. Exibe relatório com workers utilizados

### CU-003: Análise de Estabilidade com Limites
1. Usuário segue CU-001
2. Após extração, define:
   - Monitor "Vsection1": target = 1.0, offset = 0.05
   - Monitor "Isource": target = 100, offset = 10
3. Sistema detecta violações automáticamente
4. Exibe frequência de violações em gráfico
5. Usuário identifica cenários problemáticos

### CU-004: Exportação e Documentação
1. Usuário executa simulação (CU-001)
2. Seleciona um caso interessante
3. Clica "Baixar pasta randomizada"
4. Recebe ZIP com arquivos modificados
5. Compartilha com equipe para análise posterior

---

## 5. Fluxo de Telas

### Tela 1: Página Principal (app.py)
```
┌─────────────────────────────────────┐
│ OpenDSS MultiThread                 │
│ [Get Started] [Documentation]       │
│─────────────────────────────────────│
│ Key Features                         │
│ ▼ Parallel Simulation Engine         │
│   [Upload Archive]                  │
│   (Select .zip, .tar, etc)          │
│   [Marcar todas variáveis]          │
│   ├─ variable_1: V1 = 1.05          │
│   │  [✓] ±10% [offset slider]       │
│   ├─ variable_2: Sbase = 100        │
│   │  [ ] ±5%                        │
│   └─ ...                            │
│   Quantos casos? [3]                │
│   [Gerar casos e carregar]          │
└─────────────────────────────────────┘
```

### Tela 2: Execução e Resultados (loading.py)
```
┌─────────────────────────────────────┐
│ Modo: [Normal ▼]                    │
│ Carregando...                       │
│ Selecione monitores:                │
│ [✓] Vsection1  Target: [1.0]        │
│ [✓] Isource    Target: [100]        │
│ [Executar simulações]               │
│                                     │
│ Tempo: 15.32s | Workers: 4          │
│ ──────────────────────────────────  │
│ Overflow por monitor                │
│ Vsection1:    2 / 10 cases          │
│ Isource:      1 / 10 cases          │
│ ──────────────────────────────────  │
│ [Gráfico: Frequência de Violações]  │
│ ──────────────────────────────────  │
│ Cenário: [Case 1 ▼]                 │
│ [Tabela ↔ Gráfico]                  │
│ ├─ Série 1 [✓]                      │
│ ├─ Série 2 [✓]                      │
│ └─ ...                              │
│ [Gráfico de linha interativo]       │
│                                     │
│ [Gráfico: CI 95% - Monitor Vsec1]   │
│ Banda: CI + Linha: Média            │
└─────────────────────────────────────┘
```

---

## 6. Arquitetura de Dados

### 6.1 Estrutura de Diretórios
```
OpenDSSMultiThread/
├── src/
│   ├── app.py                    # Main Streamlit app
│   ├── pages/
│   │   └── loading.py            # Execution & results page
│   ├── utils/
│   │   └── run_case_worker.py    # Isolated worker subprocess
│   └── requirements.txt
├── data/
│   └── examples/                 # Sample circuits
├── docs/
│   └── ...                       # Documentation files
├── tests/
│   └── ...                       # Unit tests
├── .github/
│   └── workflows/                # CI/CD pipelines
└── README.md
```

### 6.2 Session State Schema
```python
{
  # Upload & Extraction
  "pending_main_file": str | None,
  "pending_extract_dir": str | None,
  "parsed_variables": dict[str, list[dict]],
  "parsed_variables_dir": str | None,
  
  # Randomization Plan
  "pending_random_plan": list[dict],
  "pending_case_count": int,
  
  # Monitors
  "pending_selected_monitors": list[str],
  "pending_monitor_offsets": dict[str, float],
  "pending_monitor_targets": dict[str, float],
  "cached_available_monitors": list[str],
  "monitors_cache_key": str,
  
  # Execution Results
  "solver_result": list[dict],  # Case results
  "last_parallel_duration": float | None,
  "last_serial_duration": float | None,
  "last_workers_used": int | None,
  "last_benchmark_mode": bool,
  "last_benchmark_option": str,
  "last_incremental_results": list[dict] | None,
  "current_run_seed": int,
  
  # UI State
  "results_view_mode": str,  # "table" or "chart"
  "selected_result_case": int | None,
}
```

### 6.3 Result Object Schema
```python
{
  "case": int,                      # Case index (1-N)
  "data": dict[str, dict] | None,   # Monitor data
  "monitors": list[str],            # Available monitors
  "scenario_dir": str,              # Temporary directory path
  "error": str | None,              # Error message if failed
}
```

### 6.4 Monitor Data Schema
```python
{
  "columns": ["sample", "hour", "V1", "V2", "V3", ...],
  "rows": [
    [sample_0, hour_0, value_0, value_0, value_0, ...],
    [sample_1, hour_1, value_1, value_1, value_1, ...],
    ...
  ]
}
```

---

## 7. Critérios de Aceitação

### CA-001: Upload e Extração
- [ ] Aceita .zip, .tar, .gz, .bz2, .xz
- [ ] Exibe lista de arquivos extraídos
- [ ] Seleciona arquivo .dss principal
- [ ] Mensagem de erro se nenhum .dss encontrado

### CA-002: Parsing de Variáveis
- [ ] Extrai todas as variáveis numéricas
- [ ] Identifica linha e ocorrência
- [ ] Interface para seleção com checkboxes
- [ ] Seleção de variáveis linkadas entre si ( verificar relações )
- [ ] Percentual de aleatoriedade configurável

### CA-003: Execução Paralela
- [ ] Múltiplos casos rodam simultaneamente
- [ ] Tempo paralelo < 50% tempo serial (para 4+ CPUs)
- [ ] Tratamento de erro em 1 caso não afeta outros
- [ ] Reprodutibilidade com seed

### CA-004: Visualização
- [ ] Gráficos de linha com múltiplas séries
- [ ] Toggle entre tabela e gráfico
- [ ] Intervalo de confiança calculado corretamente
- [ ] Frequência de violações em barras
- [ ] Exibição de todas as iterações de uma vez só

### CA-005: Exportação
- [ ] ZIP baixável com cenário modificado
- [ ] Todos os arquivos inclusos
- [x] Tamanho < 100 MB (typical)

---

## 8. Roadmap de Implementação

### Fase 1: MVP (Semana 1-2)
- [ ] Setup Streamlit básico
- [ ] Upload e extração de arquivos
- [ ] Parsing de variáveis
- [ ] Execução de caso único (serial)
- [ ] Visualização básica de monitor (tabela)

### Fase 2: Parallelização (Semana 3)
- [ ] ThreadPoolExecutor + subprocessos
- [ ] Worker isolado (run_case_worker.py)
- [ ] Execução paralela de múltiplos casos
- [ ] Medição de performance

### Fase 3: Análise Avançada (Semana 4-5)
- [ ] Intervalo de confiança
- [ ] Detecção de violações
- [ ] Frequência de violações
- [ ] Gráficos interativos com Altair

### Fase 4: Benchmarking (Semana 6)
- [ ] Modo serial vs. paralelo
- [ ] Modo incremental
- [ ] Comparação de performance

### Fase 5: Refinamento e Deploy (Semana 7-8)
- [ ] Testes automatizados (pytest)
- [ ] Tratamento robusto de erros
- [ ] Documentação completa
- [ ] Docker setup
- [ ] Deploy em staging/production

---

## 9. Métricas de Sucesso

| Métrica | Alvo | Status |
|---------|------|--------|
| Tempo extração (< 100MB) | < 5s | ⏳ |
| Tempo parsing variáveis | < 3s | ⏳ |
| Ganho paralelo (4 CPUs) | > 50% | ⏳ |
| Tempo resposta UI | < 1s | ⏳ |
| Reprodutibilidade | 100% | ⏳ |
| Cobertura de testes | > 70% | ⏳ |
| Uptime | > 99% | ⏳ |
---

## 10. Considerações Técnicas

### 10.1 Limitações Conhecidas
- OpenDSS COM interface (Windows) vs. Python wrapper (multiplataforma)
- Reentrância do OpenDSS → obrigatoriedade de subprocessos isolados
- ThreadPoolExecutor overhead vs. ProcessPoolExecutor (não usável com OpenDSS)

### 10.2 Pontos de Extensão
- Suporte a outros solvers (GridLAB-D, ETAP, etc.)
- Banco de dados para histórico de execuções
- API REST para integração
- Notificações via e-mail ou Slack
- Export para formatos: PDF, Excel, Parquet

### 10.3 Dependências Críticas
- `opendssdirect`: Python wrapper do OpenDSS COM
- `streamlit`: Framework web lightweight
- `pandas`: Data manipulation
- `altair`: Visualization grammar

---

## 11. Questões em Aberto

- [ ] Qual é o limite máximo de tamanho de arquivo a aceitar?
- [ ] Falar sobre tipo MIME e verificação de arquivo principal
- [ ] Falar sobre timeouts
- [ ] Falar sobre formato das VARS
- [ ] Falar sobre ferramenta de randomização previamente utilizada
- [ ] Falar sobre Octave


---

**Versão:** 1.0  
**Data:** 2026-06-11  
**Autor:** Pedro Ribeiro Filho  
**Status:** Aprovado
