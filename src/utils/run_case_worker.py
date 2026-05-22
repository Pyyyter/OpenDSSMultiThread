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


def solve(main_path: str, monitor_names: list[str] | None):
    dss.Basic.ClearAll()
    dss.Text.Command(f"redirect {main_path}")
    dss.Monitors.SaveAll()
    monitors = dss.Monitors.AllNames()
    data = {}
    if monitor_names:
        targets = {m.lower() for m in monitor_names}
        for name in monitors:
            if name.lower() in targets:
                dss.Monitors.Name(name)
                data[name] = to_serializable(dss.Monitors.Channel(1))
    return {
        "monitors": to_serializable(monitors),
        "data": data,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--main", required=True)
    parser.add_argument("--monitor")
    parser.add_argument("--monitors", help="JSON list of monitor names")
    args = parser.parse_args(argv)
    try:
        monitors = None
        if args.monitors:
            try:
                monitors = json.loads(args.monitors)
            except Exception:
                monitors = None
        if not monitors and args.monitor:
            monitors = [args.monitor]
        result = solve(args.main, monitors or [])
        print(json.dumps({"ok": True, "result": result}))
    except Exception as exc:  # pragma: no cover
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
