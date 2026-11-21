from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_csv_config(path: str | Path, required_columns: set[str]) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=sorted(required_columns), dtype="string")
    frame = pd.read_csv(path, dtype="string", encoding="utf-8-sig", keep_default_na=False).replace("", pd.NA)
    missing = required_columns - set(frame.columns)
    if missing:
        raise ValueError(f"Configuration {path.name} incomplète : {sorted(missing)}")
    return frame
