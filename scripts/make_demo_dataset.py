"""Génère le jeu de démonstration versionné à partir de l'export réel (local uniquement).

    python scripts/make_demo_dataset.py
    python scripts/make_demo_dataset.py --raw chemin/export.csv --seed 42

Écrit data/demo/stages_demo_raw.csv et config/demo/*_overrides.csv, puis vérifie qu'aucun
nom complet ni aucune partie locale d'email réels ne se retrouve dans le résultat.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stages_cleaning.config import load_csv_config  # noqa: E402
from stages_cleaning.synthetic import (  # noqa: E402
    leaked_values,
    make_synthetic,
    remap_identity_overrides,
    remap_stage_overrides,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw", type=Path, default=ROOT / "data" / "raw" / "stages_efrei_raw.csv")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    raw = pd.read_csv(args.raw, sep=";", dtype="string", encoding="utf-8-sig", keep_default_na=False)
    raw = raw.replace("", pd.NA)
    result = make_synthetic(raw, seed=args.seed)

    leaks = leaked_values(raw, result.frame)
    if any(leaks.values()):
        print(f"Fuite détectée {leaks} : relancer avec une autre --seed.", file=sys.stderr)
        return 1

    demo_dir, config_dir = ROOT / "data" / "demo", ROOT / "config" / "demo"
    demo_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    result.frame.to_csv(demo_dir / "stages_demo_raw.csv", sep=";", index=False, encoding="utf-8-sig")

    for name, columns in (
        ("location_overrides.csv", {"stage_id", "corrected_city", "corrected_country", "reason"}),
        ("postal_overrides.csv", {"stage_id", "corrected_postal_code", "reason"}),
    ):
        real = load_csv_config(ROOT / "config" / name, columns)
        remap_stage_overrides(real, result.stage_id_map).to_csv(
            config_dir / name, index=False, encoding="utf-8-sig"
        )
    identity_cols = {"source_identity", "corrected_identity", "reason"}
    identity = load_csv_config(ROOT / "data" / "reference" / "identity_overrides.csv", identity_cols)
    remap_identity_overrides(identity, result).to_csv(
        config_dir / "identity_overrides.csv", index=False, encoding="utf-8-sig"
    )
    print(f"Jeu de démo écrit : {len(result.frame)} lignes, fuites {leaks}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
