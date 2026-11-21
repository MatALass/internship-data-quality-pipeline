from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

SNAPSHOT_PREFIX = "issues_snapshot_"
SNAPSHOT_SUFFIX = ".csv"
SNAPSHOT_COLUMNS = [
    "issue_id", "rule_id", "priority", "category", "title",
    "stage_id", "email", "etudiant", "entreprise", "annee_academique", "type_stage",
]


def _snapshot_path(history_dir: Path, run_at: datetime) -> Path:
    return history_dir / f"{SNAPSHOT_PREFIX}{run_at.strftime('%Y%m%dT%H%M%SZ')}{SNAPSHOT_SUFFIX}"


def list_snapshots(history_dir: str | Path) -> list[Path]:
    history_dir = Path(history_dir)
    if not history_dir.exists():
        return []
    return sorted(history_dir.glob(f"{SNAPSHOT_PREFIX}*{SNAPSHOT_SUFFIX}"))


def load_previous_snapshot(history_dir: str | Path) -> pd.DataFrame | None:
    """Charge l'instantané le plus récent déjà enregistré (avant l'écriture de celui du run courant).

    Retourne None au tout premier run (aucun historique à comparer).
    """
    snapshots = list_snapshots(history_dir)
    if not snapshots:
        return None
    return pd.read_csv(snapshots[-1], dtype="string", encoding="utf-8-sig", keep_default_na=False).replace("", pd.NA)


def save_snapshot(issues: pd.DataFrame, history_dir: str | Path, run_at: datetime | None = None, keep_last: int = 24) -> Path:
    """Enregistre un instantané léger du registre d'anomalies pour permettre une comparaison future.

    Ne conserve que les colonnes utiles au rapprochement (pas les messages complets), et purge les
    instantanés les plus anciens au-delà de `keep_last` pour éviter une croissance illimitée.
    """
    history_dir = Path(history_dir)
    history_dir.mkdir(parents=True, exist_ok=True)
    run_at = run_at or datetime.now(timezone.utc)
    columns = [c for c in SNAPSHOT_COLUMNS if c in issues.columns]
    snapshot = issues[columns].copy()
    path = _snapshot_path(history_dir, run_at)
    snapshot.to_csv(path, index=False, encoding="utf-8-sig")

    for stale in list_snapshots(history_dir)[:-keep_last]:
        stale.unlink(missing_ok=True)
    return path


def compare_issues(current: pd.DataFrame, previous: pd.DataFrame | None) -> dict[str, pd.DataFrame]:
    """Compare le registre courant au dernier instantané enregistré.

    Le rapprochement se fait par `issue_id`, déterministe (hash de la règle + de l'entité
    concernée, voir `engine._issue_id`) : un même problème sur le même dossier garde le même
    identifiant d'un run à l'autre, ce qui permet de distinguer nouveaux cas, cas résolus et cas
    toujours ouverts sans dépendre de l'ordre des lignes.
    """
    empty = current.iloc[0:0].copy()
    if previous is None or previous.empty:
        return {"new": current.copy(), "resolved": empty.copy(), "persisting": empty.copy()}
    current_ids, previous_ids = set(current["issue_id"]), set(previous["issue_id"])
    return {
        "new": current.loc[current["issue_id"].isin(current_ids - previous_ids)].copy(),
        "resolved": previous.loc[previous["issue_id"].isin(previous_ids - current_ids)].copy(),
        "persisting": current.loc[current["issue_id"].isin(current_ids & previous_ids)].copy(),
    }
