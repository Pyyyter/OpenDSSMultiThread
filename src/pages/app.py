import streamlit as st
from io import BytesIO
from pathlib import Path
import bz2
import gzip
import lzma
import tarfile
import tempfile
import zipfile
from shutil import copyfileobj

st.set_page_config(page_title="My Landing Page", page_icon="🌐", layout="wide")

# Hero section
with st.container():
    st.title("Welcome to OpenDSS MultiThread")
    st.write(
        """
        Accelerate your power system simulations with a modern, multi-threaded workflow.
        Explore features, documentation, and get started in minutes.
        """
    )
    col1, col2 = st.columns([1, 1])
    with col1:
        st.link_button("Get Started", "https://github.com/pyyyt/OpenDSSMultiThread")
    with col2:
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
                monitor_name = st.text_input("Nome do monitor a ser retornado", key=f"monitor_name_{idx}")
                if st.button("Ir para a página de carregamento", key=f"redirect_loading_{idx}"):
                    if main_file and monitor_name:
                        st.session_state["pending_main_file"] = main_file
                        st.session_state["pending_monitor_name"] = monitor_name
                        st.session_state["pending_extract_dir"] = str(extract_dir)
                        st.switch_page("pages/loading.py")
                    else:
                        st.warning("Preencha os campos antes de continuar.")

            except Exception as exc:
                st.error(f"Extraction failed: {exc}")
                
st.markdown("---")

# Call to action
st.subheader("Ready to contribute?")
st.write(
    "Join the community, report issues, and collaborate on improving the OpenDSS MultiThread platform."
)
st.link_button("View on GitHub", "https://github.com/pyyyt/OpenDSSMultiThread")