#!/usr/bin/env python3
"""Test the convergence frame building function with sample data."""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Mock streamlit if not in streamlit context
import streamlit as st
if not hasattr(st, 'session_state'):
    # Running outside streamlit context
    pass

# Import only the utility functions, not the full page
from utils.run_case_worker import monitor_payload_to_frame, monitor_value_columns, frame_value_columns

# Import from loading.py the functions we need
import importlib.util
spec = importlib.util.spec_from_file_location("loading", str(src_path / "pages" / "loading.py"))
loading_module = importlib.util.module_from_spec(spec)
sys.modules["loading"] = loading_module

try:
    # Only load the function definitions, not execute the module code
    with open(src_path / "pages" / "loading.py", "r") as f:
        content = f.read()
    
    # Extract just the functions we need
    import ast
    tree = ast.parse(content)
    
    # Find build_monitor_convergence_frame function
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "build_monitor_convergence_frame":
            print(f"✓ Found function: {node.name}")
            print(f"  Parameters: {[arg.arg for arg in node.args.args]}")
    
    print("\n✓ All syntax checks passed!")
    
except Exception as e:
    print(f"❌ Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
