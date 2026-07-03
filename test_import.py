#!/usr/bin/env python3
"""Quick test to verify imports and basic functionality."""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

try:
    print("Testing imports...")
    import streamlit as st
    print("✓ Streamlit imported")
    
    import plotly.graph_objects as go
    import plotly.express as px
    from plotly.subplots import make_subplots
    print("✓ Plotly imported")
    
    import pandas as pd
    print("✓ Pandas imported")
    
    print("\nTesting pages/loading.py...")
    from pages import loading
    print("✓ pages/loading.py imported successfully")
    
    print("\nAll imports successful!")
    
except Exception as e:
    print(f"❌ Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
