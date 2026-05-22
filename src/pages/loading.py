import streamlit as st
from pathlib import Path
import json
from io import BytesIO
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import os
import zipfile

NUMERIC_PATTERN = re.compile(r"(?i)([a-z][\w%]*)\s*=\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")


def zip_directory_to_bytes(dir_path: Path) -> bytes:
    """Compress a directory into an in-memory zip for download."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in dir_path.rglob("*"):
            if file.is_file():
                zf.write(file, arcname=file.relative_to(dir_path))
    return buffer.getvalue()

def parse_worker_payload(raw_output: str) -> dict | None:
    raw = raw_output.strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    for line in reversed(raw.splitlines()):
        line = line.strip()
        if not line:
            continue
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def get_available_monitors(main_path: Path) -> tuple[list[str], str | None]:
    # Use the worker subprocess to avoid OpenDSS calls in Streamlit process.
    worker_path = Path(__file__).resolve().parent.parent / "utils" / "run_case_worker.py"
    cmd = [
        sys.executable,
        str(worker_path),
        "--main",
        str(main_path),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, cwd=worker_path.parent.parent)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "Worker falhou"
        return [], detail
    payload = parse_worker_payload(completed.stdout)
    if not payload:
        detail = completed.stderr.strip() or completed.stdout.strip() or "Saida do worker invalida"
        return [], detail
    if not payload.get("ok", False):
        return [], payload.get("error") or "Worker retornou erro"
    result = payload.get("result", {})
    monitors = result.get("monitors") or []
    return [str(m) for m in monitors], None


def randomize_value(base_value: float, threshold_pct: float, rng: random.Random) -> float:
    delta = rng.uniform(-threshold_pct, threshold_pct) / 100.0
    return base_value * (1 + delta)


def replace_key_value(text: str, selection: dict, rng: random.Random) -> str:
    key = selection["name"]
    occurrence = selection.get("match_index", 0)
    pattern = re.compile(rf"(?i)({re.escape(key)})\s*=\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    matches = list(pattern.finditer(text))
    if occurrence >= len(matches):
        return text
    match = matches[occurrence]
    new_val = randomize_value(selection["value"], selection["threshold_pct"], rng)
    return text[: match.start(2)] + f"{new_val:.6f}" + text[match.end(2) :]


def replace_line_value(text: str, selection: dict, rng: random.Random) -> str:
    lines = text.splitlines()
    idx = selection.get("line", 1) - 1
    if idx < 0 or idx >= len(lines):
        return text
    new_val = randomize_value(selection["value"], selection["threshold_pct"], rng)
    lines[idx] = re.sub(
        r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?",
        f"{new_val:.6f}",
        lines[idx],
        count=1,
    )
    return "\n".join(lines)


def apply_randomizations_for_file(file_path: Path, selections: list, scenario_idx: int, base_seed: int | None = None):
    if not selections:
        return
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    seed_material = f"{file_path}-{scenario_idx}-{base_seed}" if base_seed is not None else f"{file_path}-{scenario_idx}"
    rng = random.Random(seed_material)
    for selection in selections:
        if selection.get("kind") == "line_value":
            text = replace_line_value(text, selection, rng)
        else:
            text = replace_key_value(text, selection, rng)
    file_path.write_text(text, encoding="utf-8")


def prepare_randomized_dir(extract_dir: Path, selections: list, scenario_idx: int, base_seed: int | None = None) -> Path:
    scenario_dir = Path(tempfile.mkdtemp(prefix=f"scenario_{scenario_idx}_"))
    shutil.copytree(extract_dir, scenario_dir, dirs_exist_ok=True)

    grouped = {}
    for sel in selections:
        grouped.setdefault(sel["relative_path"], []).append(sel)

    for rel_path, vars_for_file in grouped.items():
        target = scenario_dir / rel_path
        if target.exists():
            apply_randomizations_for_file(target, vars_for_file, scenario_idx, base_seed)

    return scenario_dir


def pick_monitor_values(data_map: dict, monitor_name: str):
    if not isinstance(data_map, dict):
        return None
    for key, vals in data_map.items():
        if str(key).lower() == monitor_name.lower():
            return vals
    return None


def run_single_case(
    case_index: int,
    extract_dir: str,
    main_file: str,
    monitor_names: list[str],
    selections: list,
    base_seed: int | None = None,
):
    scenario_dir = prepare_randomized_dir(Path(extract_dir), selections, case_index, base_seed)
    main_path = scenario_dir / main_file

    # Run in isolated Python process to avoid OpenDSS reentrancy issues.
    worker_path = Path(__file__).resolve().parent.parent / "utils" / "run_case_worker.py"
    cmd = [
        sys.executable,
        str(worker_path),
        "--main",
        str(main_path),
    ]
    if monitor_names:
        cmd.extend(["--monitors", json.dumps(monitor_names)])
    completed = subprocess.run(cmd, capture_output=True, text=True, cwd=worker_path.parent.parent)
    if completed.returncode != 0:
        return {
            "case": case_index,
            "data": None,
            "monitors": [],
            "scenario_dir": str(scenario_dir),
            "error": completed.stderr.strip() or completed.stdout.strip() or "Worker failed",
        }

    payload = parse_worker_payload(completed.stdout)
    if not payload:
        return {
            "case": case_index,
            "data": None,
            "monitors": [],
            "scenario_dir": str(scenario_dir),
            "error": completed.stdout.strip() or "Failed to parse worker output",
        }

    if not payload.get("ok", False):
        return {
            "case": case_index,
            "data": None,
            "monitors": [],
            "scenario_dir": str(scenario_dir),
            "error": payload.get("error", "Worker error"),
        }

    result = payload.get("result", {})
    return {
        "case": case_index,
        "data": result.get("data"),
        "monitors": result.get("monitors", []),
        "scenario_dir": str(scenario_dir),
    }


def run_cases_parallel(
    case_count: int,
    extract_dir: str,
    main_file: str,
    monitor_names: list[str],
    selections: list,
    base_seed: int | None = None,
    max_workers_override: int | None = None,
):
    # Thread pool only orchestrates subprocesses; OpenDSS runs per-process.
    results = []
    from concurrent.futures import ThreadPoolExecutor, as_completed

    cpu_guess = os.cpu_count() or 4
    max_workers = min(case_count, max(1, cpu_guess))
    if max_workers_override is not None:
        max_workers = max(1, min(case_count, max_workers_override))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                run_single_case,
                idx + 1,
                extract_dir,
                main_file,
                monitor_names,
                selections,
                base_seed,
            ): idx + 1
            for idx in range(case_count)
        }
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:  # pragma: no cover - surfaced in UI
                results.append({"case": futures[future], "data": None, "monitors": [], "error": str(exc)})
    return sorted(results, key=lambda x: x.get("case", 0)), max_workers


def run_cases_serial(case_count: int, extract_dir: str, main_file: str, monitor_names: list[str], selections: list, base_seed: int | None = None):
    results = []
    for idx in range(case_count):
        results.append(
            run_single_case(
                case_index=idx + 1,
                extract_dir=extract_dir,
                main_file=main_file,
                monitor_names=monitor_names,
                selections=selections,
                base_seed=base_seed,
            )
        )
    return results, 1

st.set_page_config(page_title="Carregando", page_icon="⏳")

DEFAULT_SESSION_STATE = {
    "pending_main_file": None,
    "pending_extract_dir": None,
    "pending_random_plan": [],
    "pending_case_count": 1,
    "pending_selected_monitors": [],
    "pending_monitor_offsets": {},
}

for key, default in DEFAULT_SESSION_STATE.items():
    st.session_state.setdefault(key, default)

main_file = st.session_state["pending_main_file"]
extract_dir = st.session_state["pending_extract_dir"]
random_plan = st.session_state.get("pending_random_plan", [])
case_count = int(st.session_state.get("pending_case_count", 1))
stored_selected_monitors = st.session_state.get("pending_selected_monitors", [])
stored_monitor_offsets = st.session_state.get("pending_monitor_offsets", {})

# Unique seed per run to avoid identical randomizations across executions
run_seed = random.SystemRandom().getrandbits(64)

if not all([main_file, extract_dir]):
    st.warning("Dados pendentes não encontrados. Volte para a página inicial.")
    st.stop()

if not random_plan:
    st.warning("Nenhum plano de randomização foi enviado. Volte e selecione as variáveis.")
    st.stop()

st.write("Carregando...")
st.write(f"- Arquivo principal: {main_file}")
st.write(f"- Diretório extraído: {extract_dir}")
st.write(f"- Casos em paralelo: {case_count}")

benchmark_mode = st.checkbox("Modo benchmark (executar comparações)")
benchmark_option = "serial_parallel"
benchmark_max_workers = None
cpu_guess = os.cpu_count() or 4
max_workers_default = min(case_count, max(1, cpu_guess))
if benchmark_mode:
    benchmark_option = st.selectbox(
        "Tipo de benchmark",
        options=["Serial vs paralelo", "Benchmark incremental"],
        index=0,
    )
    if benchmark_option == "Benchmark incremental":
        benchmark_max_workers = st.number_input(
            "Maximo de workers para o benchmark",
            min_value=1,
            max_value=max_workers_default,
            value=max_workers_default,
            help="Executa todos os casos com 1..N workers e mede o tempo total.",
        )

main_path = Path(extract_dir) / main_file
available_monitors, monitor_error = get_available_monitors(main_path)

st.subheader("Selecione os monitores a acompanhar")
if not available_monitors:
    if monitor_error:
        st.error(f"Falha ao listar monitores: {monitor_error}")
    st.warning("Nenhum monitor encontrado no circuito carregado.")
    st.stop()

selected_monitors = st.multiselect(
    "Monitores disponíveis",
    options=available_monitors,
    default=stored_selected_monitors or available_monitors,
)

monitor_offsets: dict[str, float] = {}
for monitor in selected_monitors:
    monitor_offsets[monitor] = st.number_input(
        f"Offset máximo permitido para {monitor}",
        min_value=0.0,
        value=float(stored_monitor_offsets.get(monitor, 0.0)),
        key=f"offset_{monitor}",
        help="Se qualquer valor do monitor exceder este limite, o cenário é contado como estouro.",
    )

if not selected_monitors:
    st.warning("Selecione pelo menos um monitor para continuar.")
    st.stop()

if st.button("Executar simulações", type="primary"):
    st.session_state["pending_selected_monitors"] = selected_monitors
    st.session_state["pending_monitor_offsets"] = monitor_offsets
else:
    st.stop()

with st.spinner("Gerando casos randomizados e executando no OpenDSS..."):
    if benchmark_mode and benchmark_option == "Serial vs paralelo":
        serial_start = time.perf_counter()
        _, serial_workers = run_cases_serial(
            case_count=case_count,
            extract_dir=extract_dir,
            main_file=main_file,
            monitor_names=selected_monitors,
            selections=random_plan,
            base_seed=run_seed,
        )
        serial_duration = time.perf_counter() - serial_start

        parallel_start = time.perf_counter()
        results, workers_used = run_cases_parallel(
            case_count=case_count,
            extract_dir=extract_dir,
            main_file=main_file,
            monitor_names=selected_monitors,
            selections=random_plan,
            base_seed=run_seed,
        )
        parallel_duration = time.perf_counter() - parallel_start
        benchmark_series = None
    elif benchmark_mode and benchmark_option == "Benchmark incremental":
        max_workers = int(benchmark_max_workers or max_workers_default)
        benchmark_series = []
        results = []
        workers_used = max_workers
        for workers in range(1, max_workers + 1):
            run_start = time.perf_counter()
            run_results, _ = run_cases_parallel(
                case_count=case_count,
                extract_dir=extract_dir,
                main_file=main_file,
                monitor_names=selected_monitors,
                selections=random_plan,
                base_seed=run_seed,
                max_workers_override=workers,
            )
            duration = time.perf_counter() - run_start
            benchmark_series.append({"workers": workers, "seconds": duration})
            results = run_results
        parallel_duration = benchmark_series[-1]["seconds"] if benchmark_series else 0.0
        serial_duration = None
        serial_workers = None
    else:
        start = time.perf_counter()
        results, workers_used = run_cases_parallel(
            case_count=case_count,
            extract_dir=extract_dir,
            main_file=main_file,
            monitor_names=selected_monitors,
            selections=random_plan,
            base_seed=run_seed,
        )
        parallel_duration = time.perf_counter() - start
        serial_duration = None
        serial_workers = None
        benchmark_series = None

st.session_state["solver_result"] = results

overflow_counts = {m: 0 for m in selected_monitors}

for result in results:
    st.markdown(f"### Cenário {result.get('case')}")
    if result.get("error"):
        st.error(f"Falha ao executar: {result['error']}")
        continue
    data_map = result.get("data") or {}
    for monitor in selected_monitors:
        values = pick_monitor_values(data_map, monitor)
        if values is None:
            st.warning(f"Monitor {monitor} não retornou dados neste cenário.")
            continue
        st.write(f"Monitor: {monitor}")
        st.dataframe({"valor": values})
        offset = monitor_offsets.get(monitor, 0.0)
        if offset > 0 and any(abs(v) > offset for v in values):
            overflow_counts[monitor] += 1
    st.caption(f"Monitores disponíveis: {', '.join(result.get('monitors', []))}")
    scenario_dir = result.get("scenario_dir")
    if scenario_dir and Path(scenario_dir).exists():
        st.caption(f"Pasta do cenário: {scenario_dir}")
        zip_bytes = zip_directory_to_bytes(Path(scenario_dir))
        st.download_button(
            "Baixar pasta randomizada (.zip)",
            data=zip_bytes,
            file_name=f"cenario_{result.get('case')}_randomizado.zip",
            mime="application/zip",
            key=f"zip_case_{result.get('case')}",
        )

st.success("Processamento concluído.")

if benchmark_mode and benchmark_option == "Serial vs paralelo" and serial_duration is not None:
    gain_pct = ((serial_duration - parallel_duration) / serial_duration * 100) if serial_duration else 0.0
    st.info(
        f"Tempo sem paralelismo: {serial_duration:.2f} s (workers: {serial_workers}) | "
        f"Tempo com paralelismo: {parallel_duration:.2f} s (workers: {workers_used}) | "
        f"Ganho: {gain_pct:.1f}%"
    )
elif benchmark_mode and benchmark_option == "Benchmark incremental":
    if benchmark_series:
        st.subheader("Benchmark incremental (threads x tempo)")
        st.line_chart(benchmark_series, x="workers", y="seconds")
        st.dataframe(benchmark_series)
    st.info(f"Tempo com {workers_used} workers: {parallel_duration:.2f} s")
else:
    st.info(f"Tempo total: {parallel_duration:.2f} segundos | Workers usados: {workers_used}")

st.subheader("Estouro de offset por monitor")
for monitor in selected_monitors:
    count = overflow_counts.get(monitor, 0)
    st.metric(label=monitor, value=f"{count} / {case_count}", help="Cenários em que o valor ultrapassou o offset definido.")