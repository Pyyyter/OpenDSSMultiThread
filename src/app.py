import streamlit as st
from collections import defaultdict
from io import BytesIO
from pathlib import Path
import bz2
import gzip
import lzma
import re
import tarfile
import tempfile
import zipfile
from shutil import copyfileobj

st.set_page_config(page_title="OpenDSS MultiThread", page_icon="🌐", layout="wide")

DEFAULT_SESSION_STATE = {
    "pending_main_file": None,
    "pending_monitor_name": None,
    "pending_extract_dir": None,
    "pending_random_plan": [],
    "pending_case_count": 3,
    "parsed_variables": {},
    "parsed_variables_dir": None,
}

for key, default in DEFAULT_SESSION_STATE.items():
    st.session_state.setdefault(key, default)


NUMERIC_PATTERN = re.compile(r"(?i)([a-z][\w%]*)\s*=\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")


def parse_file_variables(path: Path, root: Path):
    """Extract numeric parameters from DSS/TXT files so the user can randomize them."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    variables = []

    if path.suffix.lower() == ".txt":
        for idx, raw in enumerate(text.splitlines(), start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                value = float(stripped.replace(",", "."))
            except ValueError:
                continue
            variables.append(
                {
                    "id": f"line-{idx}",
                    "name": f"linha {idx}",
                    "value": value,
                    "line": idx,
                    "kind": "line_value",
                    "match_index": idx - 1,
                    "relative_path": str(path.relative_to(root)),
                }
            )
        return variables

    for idx, match in enumerate(NUMERIC_PATTERN.finditer(text)):
        key, raw_value = match.groups()
        try:
            value = float(raw_value)
        except ValueError:
            continue
        line = text.count("\n", 0, match.start()) + 1
        variables.append(
            {
                "id": f"kv-{idx}",
                "name": key,
                "value": value,
                "line": line,
                "kind": "key_value",
                "match_index": idx,
                "relative_path": str(path.relative_to(root)),
            }
        )
    return variables


def parse_numeric_variables(extract_dir: Path):
    """Scan extracted files for numeric parameters."""
    parsed = defaultdict(list)
    for path in extract_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".dss", ".txt"}:
            continue
        parsed[str(path.relative_to(extract_dir))] = parse_file_variables(path, extract_dir)
    return dict(parsed)

header_col, action_col = st.columns([3, 2])
with header_col:
    st.header("OpenDSS MultiThread")
    st.caption("Accelerate your power system simulations with a modern, multi-threaded workflow.")
with action_col:
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        st.link_button("Get Started", "https://github.com/pyyyt/OpenDSSMultiThread")
    with btn_col2:
        st.link_button("Documentation", "https://github.com/pyyyt/OpenDSSMultiThread/wiki")

st.markdown("---")

# Features section
st.subheader("Key Features")
features = {
    "Parallel Simulation Engine": "Run multiple OpenDSS cases simultaneously with an optimized scheduler."
}

for idx, (title, desc) in enumerate(features.items()):
    with st.expander(title, expanded=True):
        st.write(desc)

        uploaded_file = st.file_uploader(
            "Upload a compressed archive",
            type=["zip", "tar", "gz", "bz2", "xz", "tgz", "tbz", "tbz2", "txz"],
            key=f"archive_upload_{idx}",
        )

        if uploaded_file:
            extract_dir = Path(tempfile.mkdtemp(prefix="extracted_"))
            payload = uploaded_file.read()
            name = uploaded_file.name.lower()

            try:
                if any(name.endswith(ext) for ext in (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz", ".tbz2", ".tar.xz", ".txz")):
                    with tarfile.open(fileobj=BytesIO(payload), mode="r:*") as archive:
                        archive.extractall(extract_dir)
                elif name.endswith(".zip"):
                    with zipfile.ZipFile(BytesIO(payload)) as archive:
                        archive.extractall(extract_dir)
                elif name.endswith(".gz"):
                    target = extract_dir / Path(uploaded_file.name).with_suffix("")
                    with gzip.GzipFile(fileobj=BytesIO(payload)) as src, open(target, "wb") as dst:
                        copyfileobj(src, dst)
                elif name.endswith(".bz2"):
                    target = extract_dir / Path(uploaded_file.name).with_suffix("")
                    target.write_bytes(bz2.decompress(payload))
                elif name.endswith(".xz"):
                    target = extract_dir / Path(uploaded_file.name).with_suffix("")
                    target.write_bytes(lzma.decompress(payload))
                else:
                    st.error("Unsupported archive format.")
                    raise ValueError

                extracted = [str(p.relative_to(extract_dir)) for p in extract_dir.rglob("*")]

                st.success(f"Files extracted to {extract_dir}")
                st.session_state["pending_extract_dir"] = str(extract_dir)
                st.write(extracted)
                dss_files = sorted(str(p.relative_to(extract_dir)) for p in extract_dir.rglob("*.dss"))

                if dss_files:
                    main_file = st.selectbox(
                        "Selecione o arquivo principal (.dss)",
                        options=dss_files,
                        key=f"main_file_{idx}",
                    )
                else:
                    st.warning("Nenhum arquivo .dss encontrado no diretório extraído.")
                    main_file = None

                monitor_name = st.text_input(
                    "Nome do monitor a ser retornado", key=f"monitor_name_{idx}"
                )

                if extract_dir:
                    if st.session_state.get("parsed_variables_dir") != str(extract_dir):
                        st.session_state["parsed_variables"] = parse_numeric_variables(extract_dir)
                        st.session_state["parsed_variables_dir"] = str(extract_dir)

                    variables_by_file = st.session_state.get("parsed_variables", {})
                    st.markdown("---")
                    st.subheader("Randomização das variáveis")
                    st.caption(
                        "Selecione quais parâmetros deseja variar e o limite percentual de aleatoriedade."
                    )

                    if st.button("Marcar todas as variáveis", key=f"mark_all_{idx}"):
                        for rel_path, vars_list in variables_by_file.items():
                            for var in vars_list:
                                safe_key = f"var_{idx}_{rel_path}_{var['id']}".replace("/", "_").replace(":", "_")
                                child_key = f"chk_{safe_key}"
                                st.session_state[child_key] = True

                    case_count = st.number_input(
                        "Quantos casos paralelos você quer rodar?",
                        min_value=1,
                        max_value=200,
                        value=st.session_state.get("pending_case_count", 3),
                        help="Cada cenário roda em um subprocesso isolado; aumente conforme sua CPU/tempo suportar.",
                        key=f"case_count_{idx}",
                    )

                    selected_plan = []
                    for rel_path, vars_list in variables_by_file.items():
                        st.markdown(f"**{rel_path}**")
                        master_key = f"select_all_{idx}_{rel_path}".replace("/", "_").replace(":", "_")
                        select_all = st.checkbox("Marcar todas deste arquivo", key=f"chk_{master_key}")
                        for var in vars_list:
                            safe_key = f"var_{idx}_{rel_path}_{var['id']}".replace(
                                "/", "_"
                            ).replace(":", "_")
                            child_key = f"chk_{safe_key}"
                            if select_all and not st.session_state.get(child_key, False):
                                st.session_state[child_key] = True
                            label = f"{var['name']} = {var['value']} (linha {var['line']})"
                            checked = st.checkbox(label, key=child_key)
                            threshold = st.number_input(
                                "Limite de aleatoriedade (%)",
                                min_value=0.0,
                                max_value=100.0,
                                value=10.0,
                                key=f"thr_{safe_key}",
                            )
                            if checked:
                                selected_plan.append({**var, "threshold_pct": threshold})
                        st.divider()

                    if st.button("Gerar casos e carregar", key=f"redirect_loading_{idx}"):
                        try:
                            if not main_file or not monitor_name:
                                raise ValueError("Preencha o arquivo principal e o monitor.")
                            if not selected_plan:
                                raise ValueError("Selecione pelo menos uma variável para randomizar.")

                            st.session_state["pending_main_file"] = main_file
                            st.session_state["pending_monitor_name"] = monitor_name
                            st.session_state["pending_extract_dir"] = str(extract_dir)
                            st.session_state["pending_random_plan"] = selected_plan
                            st.session_state["pending_case_count"] = int(case_count)
                            st.switch_page("pages/loading.py")
                        except Exception as exc:
                            st.error(f"Erro : {exc}")
            except Exception as exc:
                st.error(f"Extraction failed: {exc}")
                
st.markdown("---")

# Call to action
st.subheader("Ready to contribute?")
st.write(
    "Join the community, report issues, and collaborate on improving the OpenDSS MultiThread platform."
)
st.link_button("View on GitHub", "https://github.com/pyyyt/OpenDSSMultiThread")