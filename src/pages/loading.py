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

import opendssdirect as dss

SOLVER = "OpenDSS"

NUMERIC_PATTERN = re.compile(r"(?i)([a-z][\w%]*)\s*=\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")


def zip_directory_to_bytes(dir_path: Path) -> bytes:
    """Compress a directory into an in-memory zip for download."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in dir_path.rglob("*"):
            if file.is_file():
                zf.write(file, arcname=file.relative_to(dir_path))
    return buffer.getvalue()

def solveFile(solver, path):
    # Ensure a clean state before each run
    dss.Basic.ClearAll()
    dss.Text.Command(f"redirect {path}")
    dss.Monitors.SaveAll()
    return dss.Monitors.AllNames()

def getMonitorDataByName(monitor_name, monitors):
    # Find the index of the specified monitor
    index = None
    for i, name in enumerate(monitors):
        if name.lower() == monitor_name.lower():
            index = i
            break

    if index is not None:
        dss.Monitors.Name(monitors[index])
        # Get monitor data as a matrix (list of floats)
        data = dss.Monitors.Channel(1)  # channel 1 usually corresponds to active power in kW
        return data
    else:
        return None
    
def run_solver_with_monitor(solver, path, monitor_name=None):
    monitors = solveFile(solver, path)
    if monitor_name is None:
        return monitors
    return getMonitorDataByName(monitor_name, monitors)


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


def run_single_case(case_index: int, extract_dir: str, main_file: str, monitor_name: str, selections: list, base_seed: int | None = None):
    scenario_dir = prepare_randomized_dir(Path(extract_dir), selections, case_index, base_seed)
    main_path = scenario_dir / main_file

    # Run in isolated Python process to avoid OpenDSS reentrancy issues.
    worker_path = Path(__file__).resolve().parent.parent / "utils" / "run_case_worker.py"
    cmd = [
        sys.executable,
        str(worker_path),
        "--main",
        str(main_path),
        "--monitor",
        monitor_name,
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, cwd=worker_path.parent.parent)
    if completed.returncode != 0:
        return {
            "case": case_index,
            "data": None,
            "monitors": [],
            "scenario_dir": str(scenario_dir),
            "error": completed.stderr.strip() or completed.stdout.strip() or "Worker failed",
        }

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
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


def run_cases_parallel(case_count: int, extract_dir: str, main_file: str, monitor_name: str, selections: list, base_seed: int | None = None):
    # Thread pool only orchestrates subprocesses; OpenDSS runs per-process.
    results = []
    from concurrent.futures import ThreadPoolExecutor, as_completed

    cpu_guess = os.cpu_count() or 4
    max_workers = min(case_count, max(1, cpu_guess))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(run_single_case, idx + 1, extract_dir, main_file, monitor_name, selections, base_seed): idx + 1
            for idx in range(case_count)
        }
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:  # pragma: no cover - surfaced in UI
                results.append({"case": futures[future], "data": None, "monitors": [], "error": str(exc)})
    return sorted(results, key=lambda x: x.get("case", 0)), max_workers


def run_cases_serial(case_count: int, extract_dir: str, main_file: str, monitor_name: str, selections: list, base_seed: int | None = None):
    results = []
    for idx in range(case_count):
        results.append(
            run_single_case(
                case_index=idx + 1,
                extract_dir=extract_dir,
                main_file=main_file,
                monitor_name=monitor_name,
                selections=selections,
                base_seed=base_seed,
            )
        )
    return results, 1

st.set_page_config(page_title="Carregando", page_icon="⏳")

DEFAULT_SESSION_STATE = {
    "pending_main_file": None,
    "pending_monitor_name": None,
    "pending_extract_dir": None,
    "pending_random_plan": [],
    "pending_case_count": 1,
}

for key, default in DEFAULT_SESSION_STATE.items():
    st.session_state.setdefault(key, default)

main_file = st.session_state["pending_main_file"]
monitor_name = st.session_state["pending_monitor_name"]
extract_dir = st.session_state["pending_extract_dir"]
random_plan = st.session_state.get("pending_random_plan", [])
case_count = int(st.session_state.get("pending_case_count", 1))

# Unique seed per run to avoid identical randomizations across executions
run_seed = random.SystemRandom().getrandbits(64)

if not all([main_file, monitor_name, extract_dir]):
    st.warning("Dados pendentes não encontrados. Volte para a página inicial.")
    st.stop()

if not random_plan:
    st.warning("Nenhum plano de randomização foi enviado. Volte e selecione as variáveis.")
    st.stop()

st.write("Carregando...")
st.write(f"- Arquivo principal: {main_file}")
st.write(f"- Nome do monitor: {monitor_name}")
st.write(f"- Diretório extraído: {extract_dir}")
st.write(f"- Casos em paralelo: {case_count}")

benchmark_mode = st.checkbox("Modo benchmark (executar série + paralelo)")

with st.spinner("Gerando casos randomizados e executando no OpenDSS..."):
    if benchmark_mode:
        serial_start = time.perf_counter()
        _, serial_workers = run_cases_serial(
            case_count=case_count,
            extract_dir=extract_dir,
            main_file=main_file,
            monitor_name=monitor_name,
            selections=random_plan,
            base_seed=run_seed,
        )
        serial_duration = time.perf_counter() - serial_start

        parallel_start = time.perf_counter()
        results, workers_used = run_cases_parallel(
            case_count=case_count,
            extract_dir=extract_dir,
            main_file=main_file,
            monitor_name=monitor_name,
            selections=random_plan,
            base_seed=run_seed,
        )
        parallel_duration = time.perf_counter() - parallel_start
    else:
        start = time.perf_counter()
        results, workers_used = run_cases_parallel(
            case_count=case_count,
            extract_dir=extract_dir,
            main_file=main_file,
            monitor_name=monitor_name,
            selections=random_plan,
            base_seed=run_seed,
        )
        parallel_duration = time.perf_counter() - start
        serial_duration = None
        serial_workers = None

st.session_state["solver_result"] = results

for result in results:
    st.markdown(f"### Cenário {result.get('case')}")
    if result.get("error"):
        st.error(f"Falha ao executar: {result['error']}")
        continue
    if result.get("data") is None:
        st.warning("Monitor não encontrado para este cenário.")
        continue
    st.dataframe({"valor": result.get("data", [])})
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

if benchmark_mode and serial_duration is not None:
    gain_pct = ((serial_duration - parallel_duration) / serial_duration * 100) if serial_duration else 0.0
    st.info(
        f"Tempo sem paralelismo: {serial_duration:.2f} s (workers: {serial_workers}) | "
        f"Tempo com paralelismo: {parallel_duration:.2f} s (workers: {workers_used}) | "
        f"Ganho: {gain_pct:.1f}%"
    )
else:
    st.info(f"Tempo total: {parallel_duration:.2f} segundos | Workers usados: {workers_used}")