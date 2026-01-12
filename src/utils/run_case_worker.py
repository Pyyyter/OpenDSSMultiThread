import argparse
import json
import sys
from typing import Any

import opendssdirect as dss


def to_serializable(obj: Any):
    try:
        import numpy as np  # type: ignore

        if isinstance(obj, np.ndarray):
            return obj.tolist()
    except Exception:
        pass
    if isinstance(obj, (list, tuple)):
        return [to_serializable(x) for x in obj]
    return obj


def solve(main_path: str, monitor_name: str):
    dss.Basic.ClearAll()
    dss.Text.Command(f"redirect {main_path}")
    dss.Monitors.SaveAll()
    monitors = dss.Monitors.AllNames()
    target = None
    for name in monitors:
        if name.lower() == monitor_name.lower():
            dss.Monitors.Name(name)
            target = dss.Monitors.Channel(1)
            break
    return {
        "monitors": to_serializable(monitors),
        "data": to_serializable(target),
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--main", required=True)
    parser.add_argument("--monitor", required=True)
    args = parser.parse_args(argv)
    try:
        result = solve(args.main, args.monitor)
        print(json.dumps({"ok": True, "result": result}))
    except Exception as exc:  # pragma: no cover
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
