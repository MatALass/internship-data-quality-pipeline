from __future__ import annotations

import hashlib
from typing import Iterable

import pandas as pd


def build_stage_id(frame: pd.DataFrame, source_columns: Iterable[str] | None = None) -> pd.Series:
    """Construit un identifiant déterministe à partir de la ligne source brute.

    Les doublons exacts reçoivent volontairement le même identifiant. L'identifiant
    ne dépend ni de l'index pandas ni de l'ordre des lignes.
    """
    columns = list(source_columns or frame.columns)
    missing = set(columns) - set(frame.columns)
    if missing:
        raise ValueError(f"Colonnes absentes pour stage_id : {sorted(missing)}")

    def digest(row: pd.Series) -> str:
        payload = "\x1f".join("<NA>" if pd.isna(v) else str(v).strip() for v in row)
        return "stg_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]

    return frame[columns].apply(digest, axis=1).astype("string")
