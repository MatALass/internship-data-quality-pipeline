"""Génère les rapports qualité (métier, technique, registre, résumé PDF) sans passer par un notebook.

    python generate_quality_reports.py

Lit les sorties du pipeline (data/interim, data/processed) et le jeu d'entrée choisi par
STAGES_DATASET (réel s'il est présent, sinon démo). Écrit dans data/reports/.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from stages_cleaning.quality_reporting.runner import generate_quality_reports  # noqa: E402

if __name__ == "__main__":
    paths = generate_quality_reports(ROOT)
    for label, path in vars(paths).items():
        print(f"{label:>18} : {path.relative_to(ROOT)}")
