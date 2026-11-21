"""Chemins d'entrée selon le jeu de données utilisé : export réel (local) ou démo (versionnée).

`STAGES_DATASET` vaut `real`, `demo` ou `auto` (défaut). En `auto`, l'export réel est utilisé
s'il est présent dans `data/raw/`, sinon le jeu de démonstration : un clone public du dépôt
tourne donc tel quel, et la machine qui a l'export continue de travailler sur le vrai.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REAL_RAW = Path("data") / "raw" / "stages_efrei_raw.csv"
DEMO_RAW = Path("data") / "demo" / "stages_demo_raw.csv"


@dataclass(frozen=True)
class DatasetPaths:
    name: str
    raw: Path
    identity_overrides: Path
    location_overrides: Path
    postal_overrides: Path


def resolve_dataset(root: Path, env: dict[str, str] | None = None) -> str:
    value = (env if env is not None else os.environ).get("STAGES_DATASET", "auto").strip().lower()
    if value not in {"auto", "real", "demo"}:
        raise ValueError(f"STAGES_DATASET doit valoir auto, real ou demo (reçu : {value!r})")
    if value == "auto":
        return "real" if (root / REAL_RAW).exists() else "demo"
    return value


def dataset_paths(root: Path, env: dict[str, str] | None = None) -> DatasetPaths:
    root = Path(root)
    name = resolve_dataset(root, env)
    if name == "real":
        paths = DatasetPaths(
            name="real",
            raw=root / REAL_RAW,
            identity_overrides=root / "data" / "reference" / "identity_overrides.csv",
            location_overrides=root / "config" / "location_overrides.csv",
            postal_overrides=root / "config" / "postal_overrides.csv",
        )
    else:
        paths = DatasetPaths(
            name="demo",
            raw=root / DEMO_RAW,
            identity_overrides=root / "config" / "demo" / "identity_overrides.csv",
            location_overrides=root / "config" / "demo" / "location_overrides.csv",
            postal_overrides=root / "config" / "demo" / "postal_overrides.csv",
        )
    if not paths.raw.exists():
        raise FileNotFoundError(f"Jeu « {name} » introuvable : {paths.raw}")
    return paths


def network_enabled(env: dict[str, str] | None = None) -> bool:
    """Géocodage Nominatim activé sauf si STAGES_RUN_NETWORK=0 (CI, run hors ligne)."""
    return (env if env is not None else os.environ).get("STAGES_RUN_NETWORK", "1") != "0"
