import streamlit as st

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
    "Parallel Simulation Engine": "Run multiple OpenDSS cases simultaneously with an optimized scheduler.",
    "Automation Toolkit": "Utilities for batch processing, results aggregation, and reporting.",
    "Extensible Architecture": "Plugin-friendly design to customize simulation workflows."
}
for title, desc in features.items():
    with st.expander(title, expanded=True):
        st.write(desc)

st.markdown("---")

# Call to action
st.subheader("Ready to contribute?")
st.write(
    "Join the community, report issues, and collaborate on improving the OpenDSS MultiThread platform."
)
st.link_button("View on GitHub", "https://github.com/pyyyt/OpenDSSMultiThread")