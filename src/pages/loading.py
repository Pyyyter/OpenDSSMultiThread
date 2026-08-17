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

import pandas as pd
import opendssdirect as dss
import plotly.graph_objects as go
from plotly.subplots import make_subplots

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
        matrix = dss.Monitors.AsMatrix()
        headers = list(dss.Monitors.Header())
        hours = dss.Monitors.dblHour()
        rows = matrix.tolist() if hasattr(matrix, "tolist") else list(matrix)
        for idx, row in enumerate(rows):
            if idx < len(hours) and len(row) > 1:
                row[1] = hours[idx]
        columns = ["sample", "hour", *headers]
        if rows:
            row_width = len(rows[0])
            if len(columns) != row_width:
                if len(columns) < row_width:
                    columns.extend(f"col_{idx}" for idx in range(len(columns), row_width))
                else:
                    columns = columns[:row_width]
        return {"columns": columns, "rows": rows}
    else:
        return None


def monitor_payload_to_frame(payload):
    if isinstance(payload, list):
        if payload and isinstance(payload[0], list):
            return pd.DataFrame(payload)
        return pd.DataFrame({"valor": payload})
    if not isinstance(payload, dict):
        return None
    columns = payload.get("columns") or []
    rows = payload.get("rows") or []
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows, columns=columns)


def monitor_value_columns(frame: pd.DataFrame) -> list[str]:
    if frame.empty:
        return []
    columns = list(frame.columns)
    phase_columns = [col for col in columns if re.fullmatch(r"V\d+", str(col), flags=re.IGNORECASE)]
    if phase_columns:
        return phase_columns
    return [
        col
        for col in columns
        if str(col).lower() not in {"sample", "hour"} and "angle" not in str(col).lower()
    ]


def monitor_voltage_columns(frame: pd.DataFrame) -> list[str]:
    if frame.empty:
        return []
    return [col for col in frame.columns if re.fullmatch(r"V\d+", str(col), flags=re.IGNORECASE)]

 
def monitor_violation_series(frame: pd.DataFrame):
    value_columns = monitor_value_columns(frame)
    if not value_columns:
        return pd.Series(dtype=float)
    numeric_frame = frame[value_columns].apply(pd.to_numeric, errors="coerce")
    numeric_frame = numeric_frame.dropna(axis=1, how="all")
    if numeric_frame.empty:
        return pd.Series(dtype=float)
    return numeric_frame.max(axis=1)


def add_voltage_max_column(frame: pd.DataFrame) -> pd.DataFrame:
    voltage_columns = monitor_voltage_columns(frame)
    if not voltage_columns:
        return frame
    numeric_frame = frame[voltage_columns].apply(pd.to_numeric, errors="coerce")
    frame = frame.copy()
    frame["tensao_max_amostra"] = numeric_frame.max(axis=1)
    return frame


def safe_widget_key(*parts) -> str:
    raw_key = "_".join(str(part) for part in parts)
    return re.sub(r"[^0-9a-zA-Z_]+", "_", raw_key)


def get_case_result(results: list[dict], case_index: int):
    for result in results:
        if result.get("case") == case_index:
            return result
    return None


def frame_value_columns(frame: pd.DataFrame) -> list[str]:
    if frame.empty:
        return []
    value_columns: list[str] = []
    for column in frame.columns:
        if str(column).lower() in {"sample", "hour"}:
            continue
        numeric_values = pd.to_numeric(frame[column], errors="coerce")
        if numeric_values.notna().any():
            value_columns.append(column)
    return value_columns


def build_monitor_ci_frame(results: list[dict], monitor_name: str) -> pd.DataFrame:
    series_list = []
    for result in results:
        if result.get("error"):
            continue
        data_map = result.get("data") or {}
        frame = pick_monitor_values(data_map, monitor_name)
        if frame is None or frame.empty:
            continue
        value_columns = frame_value_columns(frame)
        if not value_columns:
            continue
        numeric_frame = frame[value_columns].apply(pd.to_numeric, errors="coerce")
        if numeric_frame.empty:
            continue
        mean_series = numeric_frame.mean(axis=1, skipna=True)
        if "hour" in frame.columns:
            hour_series = pd.to_numeric(frame["hour"], errors="coerce")
            mean_series.index = hour_series
        else:
            mean_series.index = pd.RangeIndex(start=0, stop=len(mean_series), step=1)
        series_list.append(mean_series)

    if not series_list:
        return pd.DataFrame()

    aligned = pd.concat(series_list, axis=1)
    aligned = aligned.dropna(how="all")
    count = aligned.count(axis=1)
    mean = aligned.mean(axis=1, skipna=True)
    std = aligned.std(axis=1, ddof=1, skipna=True).fillna(0.0)
    ci = 1.96 * std / count.replace(0, pd.NA).pow(0.5)
    ci = ci.fillna(0.0)
    frame = pd.DataFrame(
        {
            "iteracao": aligned.index,
            "media": mean,
            "ci_lower": mean - ci,
            "ci_upper": mean + ci,
            "amostras": count,
        }
    )
    return frame.dropna(subset=["iteracao", "media"])


def build_cumulative_voltage_frame(results: list[dict], monitor_names: list[str]) -> pd.DataFrame:
    rows = []

    for result in sorted(results, key=lambda item: item.get("case", 0)):
        if result.get("error"):
            continue

        data_map = result.get("data") or {}
        voltage_values = []

        for monitor_name in monitor_names:
            frame = pick_monitor_values(data_map, monitor_name)
            if frame is None or frame.empty:
                continue

            frame = add_voltage_max_column(frame)
            if "tensao_max_amostra" not in frame.columns:
                continue

            numeric_values = pd.to_numeric(frame["tensao_max_amostra"], errors="coerce").dropna()
            if numeric_values.empty:
                continue

            voltage_values.extend(float(value) for value in numeric_values.tolist())

        if voltage_values:
            series = pd.Series(voltage_values, dtype="float64")
            mean_value = float(series.mean())
            std_value = float(series.std(ddof=1)) if len(series) > 1 else 0.0
            ci_value = 1.96 * std_value / (len(series) ** 0.5) if len(series) > 1 else 0.0
            rows.append(
                {
                    "case": int(result.get("case", len(rows) + 1)),
                    "media_tensao_maxima": mean_value,
                    "desvio_padrao": std_value,
                    "ci_lower": mean_value - ci_value,
                    "ci_upper": mean_value + ci_value,
                    "amostras": len(voltage_values),
                }
            )

    if not rows:
        return pd.DataFrame()

    frame = pd.DataFrame(rows).sort_values("case")
    frame["media_acumulada"] = frame["media_tensao_maxima"].expanding().mean()
    frame["desvio_padrao_acumulado"] = frame["media_tensao_maxima"].expanding().std(ddof=1).fillna(0.0)
    cumulative_count = pd.Series(range(1, len(frame) + 1), index=frame.index, dtype="float64")
    cumulative_ci = 1.96 * frame["desvio_padrao_acumulado"] / cumulative_count.pow(0.5)
    frame["ci_lower_acumulado"] = frame["media_acumulada"] - cumulative_ci
    frame["ci_upper_acumulado"] = frame["media_acumulada"] + cumulative_ci
    frame["amostras_acumuladas"] = cumulative_count.astype(int)
    return frame


def build_voltage_max_distribution(results: list[dict], monitor_names: list[str]) -> pd.Series:
    voltage_values = []

    for result in sorted(results, key=lambda item: item.get("case", 0)):
        if result.get("error"):
            continue

        data_map = result.get("data") or {}

        for monitor_name in monitor_names:
            frame = pick_monitor_values(data_map, monitor_name)
            if frame is None or frame.empty:
                continue

            frame = add_voltage_max_column(frame)
            if "tensao_max_amostra" not in frame.columns:
                continue

            numeric_values = pd.to_numeric(frame["tensao_max_amostra"], errors="coerce").dropna()
            if numeric_values.empty:
                continue

            voltage_values.extend(float(value) for value in numeric_values.tolist())

    return pd.Series(voltage_values, dtype="float64")


def calculate_monitor_limits(target_value: float, offset_value: float, offset_mode: str) -> tuple[float, float]:
    if offset_mode == "relativo":
        delta = abs(target_value) * (offset_value / 100.0)
    else:
        delta = offset_value
    return target_value - delta, target_value + delta


def build_violation_summary_frame(
    results: list[dict],
    monitor_names: list[str],
    monitor_targets: dict[str, float],
    monitor_offsets: dict[str, float],
    offset_mode: str,
) -> pd.DataFrame:
    rows = []
    successful_cases = [result for result in results if not result.get("error")]
    successful_case_count = len(successful_cases)

    for monitor_name in monitor_names:
        target_value = float(monitor_targets.get(monitor_name, 0.0))
        offset_value = float(monitor_offsets.get(monitor_name, 0.0))
        lower_limit, upper_limit = calculate_monitor_limits(target_value, offset_value, offset_mode)

        total_samples = 0
        total_violations = 0
        cases_with_violation = 0

        for result in successful_cases:
            data_map = result.get("data") or {}
            frame = pick_monitor_values(data_map, monitor_name)
            if frame is None or frame.empty:
                continue

            values = monitor_violation_series(add_voltage_max_column(frame)).dropna()
            sample_count = int(len(values))
            if sample_count == 0:
                continue

            violation_count = int(((values < lower_limit) | (values > upper_limit)).sum())
            total_samples += sample_count
            total_violations += violation_count
            if violation_count > 0:
                cases_with_violation += 1

        rows.append(
            {
                "monitor": monitor_name,
                "valor_ideal": target_value,
                "offset": offset_value,
                "modo_offset": offset_mode,
                "limite_inferior": lower_limit,
                "limite_superior": upper_limit,
                "total_amostras": total_samples,
                "total_violacoes": total_violations,
                "casos_com_violacao": cases_with_violation,
                "casos_total": successful_case_count,
                "taxa_violacao_hora": (total_violations / total_samples) if total_samples else 0.0,
                "taxa_violacao_iteracao": (cases_with_violation / successful_case_count) if successful_case_count else 0.0,
            }
        )

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)


def build_monitor_convergence_frame(results: list[dict], monitor_names: list[str]) -> pd.DataFrame:
    """Build a frame showing each variable of each monitor's mean value over iterations (for convergence visualization)."""
    convergence_data = []
    
    for monitor_name in monitor_names:
        # Collect all frames for this monitor from all results
        all_columns = set()
        monitor_frames_per_result = []
        
        for result in results:
            if result.get("error"):
                continue
            data_map = result.get("data") or {}
            frame = pick_monitor_values(data_map, monitor_name)
            if frame is None or frame.empty:
                continue
            
            value_columns = frame_value_columns(frame)
            if not value_columns:
                continue
            
            all_columns.update(value_columns)
            
            numeric_frame = frame[value_columns].apply(pd.to_numeric, errors="coerce")
            if numeric_frame.empty:
                continue
            
            monitor_frames_per_result.append(numeric_frame)
        
        if not monitor_frames_per_result or not all_columns:
            continue
        
        # For each variable/column in this monitor
        for column in sorted(all_columns):
            # Collect values of this column from all results
            column_data_per_result = []
            
            for numeric_frame in monitor_frames_per_result:
                if column in numeric_frame.columns:
                    col_data = pd.to_numeric(numeric_frame[column], errors="coerce").values
                    column_data_per_result.append(col_data)
            
            if not column_data_per_result:
                continue
            
            # Find max iterations
            max_len = max(len(vals) for vals in column_data_per_result) if column_data_per_result else 0
            
            # For each iteration, calculate mean across all cases
            for iteration in range(max_len):
                values_at_iteration = []
                for col_vals in column_data_per_result:
                    if iteration < len(col_vals):
                        val = col_vals[iteration]
                        if pd.notna(val):
                            values_at_iteration.append(float(val))
                
                if values_at_iteration:
                    mean_val = float(pd.Series(values_at_iteration).mean())
                    min_val = float(pd.Series(values_at_iteration).min())
                    max_val = float(pd.Series(values_at_iteration).max())
                    std_val = float(pd.Series(values_at_iteration).std())
                    
                    # Replace NaN std with 0 (occurs when there's only 1 value)
                    if pd.isna(std_val):
                        std_val = 0.0
                    
                    convergence_data.append({
                        "monitor": monitor_name,
                        "variavel": str(column),
                        "iteracao": iteration,
                        "media": mean_val,
                        "min": min_val,
                        "max": max_val,
                        "std": std_val,
                    })
    
    if not convergence_data:
        return pd.DataFrame()
    
    return pd.DataFrame(convergence_data)


def build_case_long_frame(result: dict, monitor_names: list[str]) -> pd.DataFrame:
    data_map = result.get("data") or {}
    chart_frames = []
    for monitor in monitor_names:
        frame = pick_monitor_values(data_map, monitor)
        if frame is None or frame.empty:
            continue
        frame = add_voltage_max_column(frame)
        frame = frame.copy()
        if "hour" in frame.columns:
            hour_series = pd.to_numeric(frame["hour"], errors="coerce")
        else:
            hour_series = pd.Series(range(len(frame)), index=frame.index, dtype="float64")
        for column in frame_value_columns(frame):
            value_series = pd.to_numeric(frame[column], errors="coerce")
            part = pd.DataFrame(
                {
                    "hour": hour_series,
                    "value": value_series,
                    "series": f"{monitor} | {column}",
                    "monitor": monitor,
                    "column": column,
                }
            ).dropna(subset=["hour", "value"])
            if not part.empty:
                chart_frames.append(part)
    if not chart_frames:
        return pd.DataFrame(columns=["hour", "value", "series", "monitor", "column"])
    long_frame = pd.concat(chart_frames, ignore_index=True)
    return long_frame.sort_values(["series", "hour"])


def build_case_chart_frame(result: dict, monitor_names: list[str], selected_series: list[str] | None = None) -> pd.DataFrame:
    long_frame = build_case_long_frame(result, monitor_names)
    if long_frame.empty:
        return pd.DataFrame()
    if selected_series is not None:
        long_frame = long_frame[long_frame["series"].isin(selected_series)]
    if long_frame.empty:
        return pd.DataFrame()
    chart_frame = long_frame.pivot_table(
        index="hour",
        columns="series",
        values="value",
        aggfunc="mean",
    ).sort_index()
    return chart_frame.dropna(axis=1, how="all")
    
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


def pick_monitor_values(data_map: dict, monitor_name: str):
    if not isinstance(data_map, dict):
        return None
    for key, vals in data_map.items():
        if str(key).lower() == monitor_name.lower():
            return monitor_payload_to_frame(vals)
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


def run_cases_parallel(
    case_count: int,
    extract_dir: str,
    main_file: str,
    monitor_names: list[str],
    selections: list,
    base_seed: int | None = None,
    max_workers: int | None = None,
):
    # Thread pool only orchestrates subprocesses; OpenDSS runs per-process.
    results = []
    from concurrent.futures import ThreadPoolExecutor, as_completed

    cpu_guess = os.cpu_count() or 4
    capped_workers = min(case_count, max(1, cpu_guess))
    if max_workers is None:
        max_workers = capped_workers
    else:
        max_workers = max(1, min(case_count, max_workers))

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

st.set_page_config(page_title="Carregando", page_icon="ÔÅ│")

DEFAULT_SESSION_STATE = {
    "pending_main_file": None,
    "pending_extract_dir": None,
    "pending_random_plan": [],
    "pending_case_count": 1,
    "pending_selected_monitors": [],
    "pending_monitor_offsets": {},
    "pending_monitor_targets": {},
    "pending_violation_offset_mode": "absoluto",
    "solver_result": None,
    "last_parallel_duration": None,
    "last_serial_duration": None,
    "last_workers_used": None,
    "last_serial_workers": None,
    "last_benchmark_mode": False,
    "last_benchmark_option": "Normal",
    "last_incremental_results": None,
    "last_incremental_workers": None,
    "last_violation_offset_mode": "absoluto",
    "current_run_seed": None,
    "results_view_mode": "table",
}

for key, default in DEFAULT_SESSION_STATE.items():
    st.session_state.setdefault(key, default)

main_file = st.session_state["pending_main_file"]
extract_dir = st.session_state["pending_extract_dir"]
random_plan = st.session_state.get("pending_random_plan", [])
case_count = int(st.session_state.get("pending_case_count", 1))
stored_selected_monitors = st.session_state.get("pending_selected_monitors", [])
stored_monitor_offsets = st.session_state.get("pending_monitor_offsets", {})
stored_monitor_targets = st.session_state.get("pending_monitor_targets", {})
stored_violation_offset_mode = st.session_state.get("pending_violation_offset_mode", "absoluto")

if not all([main_file, extract_dir]):
    st.warning("Dados pendentes não encontrados. Volte para a p├ígina inicial.")
    st.stop()

if not random_plan:
    st.warning("Nenhum plano de randomização foi enviado. Volte e selecione as vari├íveis.")
    st.stop()

st.write("Carregando...")
st.write(f"- Arquivo principal: {main_file}")
st.write(f"- Diret├│rio extra├¡do: {extract_dir}")
st.write(f"- Casos em paralelo: {case_count}")

benchmark_options = ["Normal", "Benchmark (serial + paralelo)", "Benchmark incremental"]
stored_benchmark_option = st.session_state.get("last_benchmark_option")
benchmark_option = st.selectbox(
    "Modo de execução",
    options=benchmark_options,
    index=benchmark_options.index(stored_benchmark_option)
    if stored_benchmark_option in benchmark_options
    else 0,
)
benchmark_mode = benchmark_option != "Normal"
incremental_workers = None
if benchmark_option == "Benchmark incremental":
    incremental_workers = st.number_input(
        "Quantidade m├íxima de workers para o benchmark incremental",
        min_value=1,
        value=int(st.session_state.get("last_incremental_workers") or min(case_count, (os.cpu_count() or 4))),
        help="Executa os casos com 1..N workers e mede o tempo em cada etapa.",
        key="benchmark_incremental_workers",
    )

main_path = Path(extract_dir) / main_file
monitors_cache_key = f"{main_path}"

# Avoid rerunning OpenDSS on every widget change; cache monitor discovery per main file
if (
    st.session_state.get("monitors_cache_key") != monitors_cache_key
    or "cached_available_monitors" not in st.session_state
):
    try:
        st.session_state["cached_available_monitors"] = run_solver_with_monitor(
            SOLVER, str(main_path), monitor_name=None
        )
        st.session_state["monitors_cache_key"] = monitors_cache_key
        st.session_state["cached_monitor_error"] = None
    except Exception as exc:  # pragma: no cover - surfaced in UI
        st.session_state["cached_available_monitors"] = []
        st.session_state["cached_monitor_error"] = str(exc)

if st.session_state.get("cached_monitor_error"):
    st.error(f"Falha ao carregar os monitores: {st.session_state['cached_monitor_error']}")
    st.stop()

available_monitors = st.session_state.get("cached_available_monitors", [])

st.subheader("Selecione os monitores a acompanhar")
if not available_monitors:
    st.warning("Nenhum monitor encontrado no circuito carregado.")
    st.stop()

selected_monitors = st.multiselect(
    "Monitores dispon├¡veis",
    options=available_monitors,
    default=stored_selected_monitors or available_monitors,
)

violation_offset_mode = st.radio(
    "Modo do offset",
    options=["absoluto", "relativo"],
    format_func=lambda value: "Absoluto" if value == "absoluto" else "Relativo (%)",
    index=0 if stored_violation_offset_mode == "absoluto" else 1,
    horizontal=True,
    help="No modo relativo, o offset é interpretado como porcentagem do valor ideal.",
)

monitor_offsets: dict[str, float] = {}
monitor_targets: dict[str, float] = {}
for monitor in selected_monitors:
    monitor_targets[monitor] = st.number_input(
        f"Valor desejado para {monitor}",
        value=float(stored_monitor_targets.get(monitor, 0.0)),
        key=f"target_{monitor}",
        help="Refer├¬ncia central esperada para o monitor.",
    )
    offset_label = "Offset relativo (%)" if violation_offset_mode == "relativo" else "Offset absoluto"
    monitor_offsets[monitor] = st.number_input(
        f"{offset_label} para {monitor}",
        min_value=0.0,
        value=float(stored_monitor_offsets.get(monitor, 0.0)),
        key=f"offset_{monitor}",
        help=(
            "Estouro ocorre se algum valor ficar fora do intervalo ideal. "
            "No modo relativo, o offset é aplicado como porcentagem do valor ideal."
        ),
    )

if not selected_monitors:
    st.warning("Selecione pelo menos um monitor para continuar.")
    st.stop()

run_requested = st.button("Executar simulaç├Áes", type="primary")
if run_requested:
    st.session_state["pending_selected_monitors"] = selected_monitors
    st.session_state["pending_monitor_offsets"] = monitor_offsets
    st.session_state["pending_monitor_targets"] = monitor_targets
    st.session_state["pending_violation_offset_mode"] = violation_offset_mode
    st.session_state["current_run_seed"] = random.SystemRandom().getrandbits(64)
    st.session_state["last_benchmark_mode"] = benchmark_mode
    st.session_state["last_benchmark_option"] = benchmark_option
    st.session_state["last_violation_offset_mode"] = violation_offset_mode
    if incremental_workers is not None:
        st.session_state["last_incremental_workers"] = int(incremental_workers)
elif st.session_state.get("solver_result") is None:
    st.stop()

run_seed = st.session_state.get("current_run_seed")
if run_seed is None:
    run_seed = random.SystemRandom().getrandbits(64)
    st.session_state["current_run_seed"] = run_seed

should_run = run_requested or st.session_state.get("solver_result") is None

if should_run:
    with st.spinner("Gerando casos randomizados e executando no OpenDSS..."):
        try:
            incremental_results = None
            if benchmark_option == "Benchmark (serial + paralelo)":
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
            elif benchmark_option == "Benchmark incremental":
                serial_duration = None
                serial_workers = None
                workers_used = None
                incremental_results = []
                max_workers = int(incremental_workers or 1)
                for worker_count in range(1, max_workers + 1):
                    start = time.perf_counter()
                    results, workers_used = run_cases_parallel(
                        case_count=case_count,
                        extract_dir=extract_dir,
                        main_file=main_file,
                        monitor_names=selected_monitors,
                        selections=random_plan,
                        base_seed=run_seed,
                        max_workers=worker_count,
                    )
                    duration = time.perf_counter() - start
                    incremental_results.append({"workers": worker_count, "seconds": duration})
                parallel_duration = None
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
        except Exception as exc:
            st.error(f"Erro ao executar simulaç├Áes: {type(exc).__name__}: {str(exc)}")
            import traceback
            st.error(traceback.format_exc())
            st.stop()
    st.session_state["solver_result"] = results
    st.session_state["last_parallel_duration"] = parallel_duration
    st.session_state["last_serial_duration"] = serial_duration
    st.session_state["last_workers_used"] = workers_used
    st.session_state["last_serial_workers"] = serial_workers
    st.session_state["last_benchmark_mode"] = benchmark_mode
    st.session_state["last_benchmark_option"] = benchmark_option
    st.session_state["last_incremental_results"] = incremental_results
else:
    results = st.session_state.get("solver_result", [])
    parallel_duration = st.session_state.get("last_parallel_duration")
    serial_duration = st.session_state.get("last_serial_duration")
    workers_used = st.session_state.get("last_workers_used")
    serial_workers = st.session_state.get("last_serial_workers")
    benchmark_mode = st.session_state.get("last_benchmark_mode", benchmark_mode)
    benchmark_option = st.session_state.get("last_benchmark_option", benchmark_option)
    incremental_results = st.session_state.get("last_incremental_results")
    violation_offset_mode = st.session_state.get("last_violation_offset_mode", violation_offset_mode)

overflow_counts = {m: 0 for m in selected_monitors}
violations_per_case: list[int] = []

for result in results:
    if result.get("error"):
        continue
    data_map = result.get("data") or {}
    case_violation_count = 0
    for monitor in selected_monitors:
        frame = pick_monitor_values(data_map, monitor)
        if frame is None or frame.empty:
            continue
        frame = add_voltage_max_column(frame)
        target = monitor_targets.get(monitor, 0.0)
        offset = monitor_offsets.get(monitor, 0.0)
        lower = target - offset
        upper = target + offset
        values = monitor_violation_series(frame)
        if not values.empty and any((v < lower) or (v > upper) for v in values.dropna()):
            overflow_counts[monitor] += 1
            case_violation_count += 1
    violations_per_case.append(case_violation_count)

st.success("Processamento conclu├¡do.")

if benchmark_option == "Benchmark (serial + paralelo)" and serial_duration is not None and parallel_duration is not None:
    if serial_duration > 0:
        gain_pct = (serial_duration - parallel_duration) / serial_duration * 100
        gain_msg = f" | Ganho: {gain_pct:.1f}%"
    else:
        gain_msg = " | Ganho: n/d (tempo serial ~0s)"
    st.info(
        f"Tempo sem paralelismo: {serial_duration:.2f} s (workers: {serial_workers}) | "
        f"Tempo com paralelismo: {parallel_duration:.2f} s (workers: {workers_used})" + gain_msg
    )
elif benchmark_option == "Benchmark incremental":
    st.info("Benchmark incremental conclu├¡do. Confira o gr├ífico abaixo.")
else:
    if parallel_duration is not None and workers_used is not None:
        st.info(f"Tempo total: {parallel_duration:.2f} segundos | Workers usados: {workers_used}")

if benchmark_option == "Benchmark incremental" and incremental_results:
    bench_frame = pd.DataFrame(incremental_results)
    if not bench_frame.empty:
        bench_frame = bench_frame.sort_values("workers")
        st.subheader("Benchmark incremental")
        st.caption("Tempo total por quantidade de workers.")
        fig_bench = go.Figure()
        fig_bench.add_trace(go.Scatter(
            x=bench_frame["workers"],
            y=bench_frame["seconds"],
            mode="lines+markers",
            name="Tempo (s)",
            line=dict(color="#636EFA", width=3),
            marker=dict(size=8)
        ))
        fig_bench.update_layout(
            title="Tempo de Execução vs Quantidade de Workers",
            xaxis_title="N├║mero de Workers",
            yaxis_title="Tempo (segundos)",
            hovermode="x unified",
            height=400,
            template="plotly_white",
            margin=dict(l=50, r=50, t=80, b=50)
        )
        st.plotly_chart(fig_bench, use_container_width=True)

violation_summary_frame = build_violation_summary_frame(
    results,
    selected_monitors,
    monitor_targets,
    monitor_offsets,
    violation_offset_mode,
)

st.subheader("Verificação de violações por monitor")
st.caption(
    "A verificação é independente da simulação: ao final, cada monitor é comparado ao valor ideal e ao offset escolhido."
)

if violation_summary_frame.empty:
    st.warning("Não há dados suficientes para calcular violações por monitor.")
else:
    total_violations = int(violation_summary_frame["total_violacoes"].sum())
    total_samples = int(violation_summary_frame["total_amostras"].sum())
    total_rate_hour = (total_violations / total_samples) if total_samples else 0.0
    total_cases = int(violation_summary_frame["casos_total"].max())
    monitors_with_violation = int((violation_summary_frame["casos_com_violacao"] > 0).sum())

    metric_cols = st.columns(3)
    metric_cols[0].metric(
        "Taxa global por hora",
        f"{total_rate_hour:.4f}",
        help=f"{total_violations} violações em {total_samples} amostras totais.",
    )
    metric_cols[1].metric(
        "Monitores com violação",
        f"{monitors_with_violation} / {len(violation_summary_frame)}",
        help="Quantidade de monitores que tiveram ao menos um estouro em alguma iteração.",
    )
    metric_cols[2].metric(
        "Casos analisados",
        f"{total_cases}",
        help="Número de iterações/casos considerados no denominador da taxa por iteração.",
    )

    chart_col, table_col = st.columns([2, 1])
    with chart_col:
        fig_violations = go.Figure()
        fig_violations.add_trace(
            go.Bar(
                x=violation_summary_frame["monitor"],
                y=violation_summary_frame["taxa_violacao_hora"] * 100,
                name="Taxa por hora (%)",
                marker=dict(color="#1f77b4"),
                customdata=violation_summary_frame[
                    ["total_violacoes", "total_amostras", "casos_com_violacao", "casos_total"]
                ].values,
                hovertemplate=(
                    "<b>%{x}</b><br>Taxa por hora: %{y:.2f}%<br>"
                    "Violações: %{customdata[0]} / %{customdata[1]}<extra></extra>"
                ),
            )
        )
        fig_violations.add_trace(
            go.Bar(
                x=violation_summary_frame["monitor"],
                y=violation_summary_frame["taxa_violacao_iteracao"] * 100,
                name="Taxa por iteração (%)",
                marker=dict(color="#ff7f0e"),
                customdata=violation_summary_frame[
                    ["total_violacoes", "total_amostras", "casos_com_violacao", "casos_total"]
                ].values,
                hovertemplate=(
                    "<b>%{x}</b><br>Taxa por iteração: %{y:.2f}%<br>"
                    "Iterações com violação: %{customdata[2]} / %{customdata[3]}<extra></extra>"
                ),
            )
        )
        fig_violations.update_layout(
            title="Violação por monitor",
            xaxis_title="Monitor",
            yaxis_title="Taxa (%)",
            hovermode="x",
            barmode="group",
            height=450,
            template="plotly_white",
            margin=dict(l=50, r=30, t=80, b=50),
        )
        st.plotly_chart(fig_violations, use_container_width=True)

    with table_col:
        display_frame = violation_summary_frame.copy()
        display_frame["taxa_violacao_hora"] = display_frame["taxa_violacao_hora"].map(lambda value: f"{value:.4%}")
        display_frame["taxa_violacao_iteracao"] = display_frame["taxa_violacao_iteracao"].map(lambda value: f"{value:.4%}")
        st.dataframe(
            display_frame[
                [
                    "monitor",
                    "valor_ideal",
                    "offset",
                    "modo_offset",
                    "limite_inferior",
                    "limite_superior",
                    "total_violacoes",
                    "total_amostras",
                    "taxa_violacao_hora",
                    "casos_com_violacao",
                    "casos_total",
                    "taxa_violacao_iteracao",
                ]
            ],
            use_container_width=True,
        )

st.subheader("Resultados do caso")
case_options = [result.get("case") for result in results]
if not case_options:
    st.warning("Nenhum cen├írio conclu├¡do com sucesso para exibir.")
else:
    default_case = case_options[0]
    selected_case = st.selectbox(
        "Cen├írio",
        options=case_options,
        index=case_options.index(st.session_state.get("selected_result_case", default_case))
        if st.session_state.get("selected_result_case", default_case) in case_options
        else 0,
        key="selected_result_case",
    )

    view_mode = st.session_state.get("results_view_mode", "table")
    toggle_label = "Alternar para gr├ífico" if view_mode == "table" else "Alternar para tabela"
    if st.button(toggle_label, key="toggle_results_view"):
        st.session_state["results_view_mode"] = "chart" if view_mode == "table" else "table"
        st.rerun()

    selected_result = get_case_result(results, int(selected_case)) if selected_case is not None else None
    if selected_result is None:
        st.warning("Não foi poss├¡vel localizar o cen├írio selecionado.")
    elif selected_result.get("error"):
        st.error(f"Falha ao executar o cen├írio {selected_result.get('case')}: {selected_result['error']}")
    else:
        scenario_dir = selected_result.get("scenario_dir")
        if scenario_dir and Path(scenario_dir).exists():
            st.caption(f"Pasta do cen├írio: {scenario_dir}")
            zip_bytes = zip_directory_to_bytes(Path(scenario_dir))
            st.download_button(
                "Baixar pasta randomizada (.zip)",
                data=zip_bytes,
                file_name=f"cenario_{selected_result.get('case')}_randomizado.zip",
                mime="application/zip",
                key=f"zip_case_{selected_result.get('case')}",
            )

        if st.session_state.get("results_view_mode", "table") == "chart":
            st.caption("Marque as séries que deseja exibir no gr├ífico. As alteraç├Áes aparecem em tempo real.")
            series_frame = build_case_long_frame(selected_result, selected_monitors)
            if series_frame.empty:
                st.warning("Nenhuma série numérica foi encontrada para este cen├írio.")
            else:
                series_options = list(series_frame["series"].dropna().unique())
                selected_series = []
                checkbox_cols = st.columns(2)
                for idx, series_name in enumerate(series_options):
                    col = checkbox_cols[idx % 2]
                    with col:
                        if st.checkbox(
                            series_name,
                            value=True,
                            key=safe_widget_key("series_visible", selected_case, series_name),
                        ):
                            selected_series.append(series_name)

                chart_frame = build_case_chart_frame(selected_result, selected_monitors, selected_series)
                if chart_frame.empty:
                    st.info("Selecione pelo menos uma série para exibir o gr├ífico.")
                else:
                    fig_series = go.Figure()
                    for column in chart_frame.columns:
                        fig_series.add_trace(go.Scatter(
                            x=chart_frame.index,
                            y=chart_frame[column],
                            mode="lines",
                            name=str(column),
                            line=dict(width=2)
                        ))
                    fig_series.update_layout(
                        title=f"Séries do Cen├írio {selected_case}",
                        xaxis_title="Hora",
                        yaxis_title="Valor",
                        hovermode="x unified",
                        height=450,
                        template="plotly_white",
                        margin=dict(l=50, r=50, t=80, b=50)
                    )
                    st.plotly_chart(fig_series, use_container_width=True)
        else:
            data_map = selected_result.get("data") or {}
            for monitor in selected_monitors:
                frame = pick_monitor_values(data_map, monitor)
                if frame is None or frame.empty:
                    st.warning(f"Monitor {monitor} não retornou dados neste cen├írio.")
                    continue
                frame = add_voltage_max_column(frame)
                st.write(f"Monitor: {monitor}")
                st.dataframe(frame, use_container_width=True)
            st.caption(f"Monitores dispon├¡veis: {', '.join(selected_result.get('monitors', []))}")

st.subheader("Média e intervalo de confiança")
ci_monitor = st.selectbox(
    "Monitor para média",
    options=selected_monitors,
    index=0,
    key="ci_monitor",
)
ci_frame = build_monitor_ci_frame(results, ci_monitor)
if ci_frame.empty:
    st.warning("Não h├í dados suficientes para calcular a média e o intervalo de confiança.")
else:
    fig_ci = go.Figure()
    # Banda de confiança (intervalo de confiança)
    fig_ci.add_trace(go.Scatter(
        x=ci_frame["iteracao"],
        y=ci_frame["ci_upper"],
        mode="lines",
        line=dict(width=0),
        showlegend=False,
        hoverinfo="skip"
    ))
    fig_ci.add_trace(go.Scatter(
        x=ci_frame["iteracao"],
        y=ci_frame["ci_lower"],
        mode="lines",
        line=dict(width=0),
        fillcolor="rgba(122, 174, 214, 0.3)",
        fill="tonexty",
        name="IC 95%",
        hoverinfo="skip"
    ))
    # Linha de média
    fig_ci.add_trace(go.Scatter(
        x=ci_frame["iteracao"],
        y=ci_frame["media"],
        mode="lines+markers",
        name="Média",
        line=dict(color="#1f4f7a", width=3),
        marker=dict(size=4)
    ))
    fig_ci.update_layout(
        title=f"Média e Intervalo de Confiança - {ci_monitor}",
        xaxis_title="Iteraç├Áes",
        yaxis_title="Tensão (pu)",
        hovermode="x unified",
        height=450,
        template="plotly_white",
        margin=dict(l=50, r=50, t=80, b=50)
    )
    st.plotly_chart(fig_ci, use_container_width=True)

if benchmark_option == "Benchmark incremental":
    st.subheader("Média acumulada da tensão máxima")
    st.caption(
        "Para cada iteração, calcula a média diária da tensão máxima e acumula os resultados para mostrar a evolução do benchmark incremental."
    )
    cumulative_voltage_frame = build_cumulative_voltage_frame(results, selected_monitors)
    if cumulative_voltage_frame.empty:
        st.warning("Não há dados suficientes para calcular a média acumulada da tensão máxima.")
    else:
        final_row = cumulative_voltage_frame.iloc[-1]
        metric_cols = st.columns(4)
        metric_cols[0].metric("Média acumulada final", f"{final_row['media_acumulada']:.6f}")
        metric_cols[1].metric("Desvio padrão", f"{final_row['desvio_padrao_acumulado']:.6f}")
        metric_cols[2].metric(
            "IC 95%",
            f"{final_row['ci_lower_acumulado']:.6f} a {final_row['ci_upper_acumulado']:.6f}",
        )
        metric_cols[3].metric("Iterações", f"{int(final_row['case'])}")

        cumulative_col, boxplot_col = st.columns([2, 1])

        with cumulative_col:
            fig_cumulative = go.Figure()
            fig_cumulative.add_trace(
                go.Scatter(
                    x=cumulative_voltage_frame["case"],
                    y=cumulative_voltage_frame["media_tensao_maxima"],
                    mode="lines+markers",
                    name="Média por iteração",
                    line=dict(color="#8bc34a", width=2, dash="dot"),
                    marker=dict(size=6),
                )
            )
            fig_cumulative.add_trace(
                go.Scatter(
                    x=cumulative_voltage_frame["case"],
                    y=cumulative_voltage_frame["media_acumulada"],
                    mode="lines+markers",
                    name="Média acumulada",
                    line=dict(color="#1f4f7a", width=3),
                    marker=dict(size=7),
                )
            )
            fig_cumulative.add_trace(
                go.Scatter(
                    x=cumulative_voltage_frame["case"],
                    y=cumulative_voltage_frame["ci_upper_acumulado"],
                    mode="lines",
                    line=dict(width=0),
                    showlegend=False,
                    hoverinfo="skip",
                )
            )
            fig_cumulative.add_trace(
                go.Scatter(
                    x=cumulative_voltage_frame["case"],
                    y=cumulative_voltage_frame["ci_lower_acumulado"],
                    mode="lines",
                    line=dict(width=0),
                    fillcolor="rgba(31, 79, 122, 0.18)",
                    fill="tonexty",
                    name="IC 95% acumulado",
                    hoverinfo="skip",
                )
            )
            fig_cumulative.update_layout(
                title="Média acumulada da tensão máxima por iteração",
                xaxis_title="Iteração",
                yaxis_title="Tensão máxima média (pu)",
                hovermode="x unified",
                height=450,
                template="plotly_white",
                margin=dict(l=50, r=50, t=80, b=50),
            )
            st.plotly_chart(fig_cumulative, use_container_width=True)
            st.dataframe(
                cumulative_voltage_frame[
                    [
                        "case",
                        "amostras",
                        "media_tensao_maxima",
                        "desvio_padrao",
                        "ci_lower",
                        "ci_upper",
                        "media_acumulada",
                        "desvio_padrao_acumulado",
                        "ci_lower_acumulado",
                        "ci_upper_acumulado",
                    ]
                ],
                use_container_width=True,
            )

        with boxplot_col:
            voltage_distribution = build_voltage_max_distribution(results, selected_monitors)
            fig_boxplot = go.Figure()
            fig_boxplot.add_trace(
                go.Box(
                    y=voltage_distribution,
                    name="Todos os máximos",
                    boxpoints="all",
                    jitter=0.35,
                    pointpos=-1.8,
                    marker=dict(color="#1f77b4", size=6, opacity=0.7),
                    line=dict(color="#1f77b4"),
                )
            )
            fig_boxplot.update_layout(
                title="Distribuição dos máximos de tensão",
                yaxis_title="Tensão máxima (pu)",
                height=450,
                template="plotly_white",
                margin=dict(l=50, r=30, t=80, b=50),
            )
            st.plotly_chart(fig_boxplot, use_container_width=True)
