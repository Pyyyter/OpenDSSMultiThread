import streamlit as st
from pathlib import Path
import json
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import os

import opendssdirect as dss

SOLVER = "OpenDSS"

NUMERIC_PATTERN = re.compile(r"(?i)([a-z][\w%]*)\s*=\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")

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


def apply_randomizations_for_file(file_path: Path, selections: list, scenario_idx: int):
    if not selections:
        return
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    rng = random.Random(f"{file_path}-{scenario_idx}")
    for selection in selections:
        if selection.get("kind") == "line_value":
            text = replace_line_value(text, selection, rng)
        else:
            text = replace_key_value(text, selection, rng)
    file_path.write_text(text, encoding="utf-8")


def prepare_randomized_dir(extract_dir: Path, selections: list, scenario_idx: int) -> Path:
    scenario_dir = Path(tempfile.mkdtemp(prefix=f"scenario_{scenario_idx}_"))
    shutil.copytree(extract_dir, scenario_dir, dirs_exist_ok=True)

    grouped = {}
    for sel in selections:
        grouped.setdefault(sel["relative_path"], []).append(sel)

    for rel_path, vars_for_file in grouped.items():
        target = scenario_dir / rel_path
        if target.exists():
            apply_randomizations_for_file(target, vars_for_file, scenario_idx)

    return scenario_dir


def run_single_case(case_index: int, extract_dir: str, main_file: str, monitor_name: str, selections: list):
    scenario_dir = prepare_randomized_dir(Path(extract_dir), selections, case_index)
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


def run_cases_parallel(case_count: int, extract_dir: str, main_file: str, monitor_name: str, selections: list):
    # Thread pool only orchestrates subprocesses; OpenDSS runs per-process.
    results = []
    from concurrent.futures import ThreadPoolExecutor, as_completed

    cpu_guess = os.cpu_count() or 4
    max_workers = min(case_count, max(1, cpu_guess))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(run_single_case, idx + 1, extract_dir, main_file, monitor_name, selections): idx + 1
            for idx in range(case_count)
        }
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:  # pragma: no cover - surfaced in UI
                results.append({"case": futures[future], "data": None, "monitors": [], "error": str(exc)})
    return sorted(results, key=lambda x: x.get("case", 0)), max_workers

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

with st.spinner("Gerando casos randomizados e executando no OpenDSS..."):
    start = time.perf_counter()
    results, workers_used = run_cases_parallel(
        case_count=case_count,
        extract_dir=extract_dir,
        main_file=main_file,
        monitor_name=monitor_name,
        selections=random_plan,
    )
    duration = time.perf_counter() - start

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

st.success("Processamento concluído.")
st.info(f"Tempo total: {duration:.2f} segundos | Workers usados: {workers_used}")