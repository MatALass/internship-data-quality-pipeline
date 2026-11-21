"""Construit l'export « prêt pour la rentrée » à partir du dataset final.

    python build_analysis_export.py

Écrit dans data/processed/ :
- stages_efrei_final_flagge.csv : toutes les lignes + exclu_analyse et motif_exclusion ;
- stages_efrei_pret_rentree.csv : uniquement les lignes exploitables, sans ces deux colonnes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from stages_cleaning.analysis_export import (  # noqa: E402
    build_analysis_ready_frame,
    flag_analysis_exclusions,
)

PROCESSED = ROOT / "data" / "processed"

if __name__ == "__main__":
    final = pd.read_csv(
        PROCESSED / "stages_efrei_final.csv", dtype="string", encoding="utf-8-sig", keep_default_na=False
    ).replace("", pd.NA)
    flagged = flag_analysis_exclusions(final)
    ready = build_analysis_ready_frame(flagged)
    flagged.to_csv(PROCESSED / "stages_efrei_final_flagge.csv", index=False, encoding="utf-8-sig")
    ready.to_csv(PROCESSED / "stages_efrei_pret_rentree.csv", index=False, encoding="utf-8-sig")
    print(f"{len(flagged)} lignes flaggées, {len(ready)} prêtes pour un usage aval")
