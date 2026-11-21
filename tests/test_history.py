from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from stages_cleaning.quality_reporting.history import (
    compare_issues, list_snapshots, load_previous_snapshot, save_snapshot,
)


def _issues(ids: list[str]) -> pd.DataFrame:
    return pd.DataFrame({
        "issue_id": ids,
        "rule_id": ["MISSING_COMPANY"] * len(ids),
        "priority": ["URGENT"] * len(ids),
        "category": ["Dossier incomplet"] * len(ids),
        "title": ["Entreprise non renseignée"] * len(ids),
        "stage_id": [f"stg_{i}" for i in ids],
        "email": [f"{i}@efrei.net" for i in ids],
        "etudiant": ["X, Y"] * len(ids),
        "entreprise": [pd.NA] * len(ids),
        "annee_academique": ["2025-2026"] * len(ids),
        "type_stage": ["Stage"] * len(ids),
    })


def test_load_previous_snapshot_returns_none_on_first_run(tmp_path):
    assert load_previous_snapshot(tmp_path / "history") is None


def test_save_and_reload_snapshot_round_trips(tmp_path):
    history_dir = tmp_path / "history"
    issues = _issues(["a", "b"])
    save_snapshot(issues, history_dir, run_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    previous = load_previous_snapshot(history_dir)
    assert previous is not None
    assert set(previous["issue_id"]) == {"a", "b"}


def test_save_snapshot_prunes_old_snapshots_beyond_keep_last(tmp_path):
    history_dir = tmp_path / "history"
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(5):
        save_snapshot(_issues(["a"]), history_dir, run_at=base + timedelta(days=i), keep_last=2)
    assert len(list_snapshots(history_dir)) == 2


def test_compare_issues_first_run_has_no_previous():
    current = _issues(["a", "b"])
    result = compare_issues(current, None)
    assert set(result["new"]["issue_id"]) == {"a", "b"}
    assert result["resolved"].empty
    assert result["persisting"].empty


def test_compare_issues_detects_new_resolved_and_persisting():
    previous = _issues(["a", "b"])
    current = _issues(["b", "c"])
    result = compare_issues(current, previous)
    assert set(result["new"]["issue_id"]) == {"c"}
    assert set(result["resolved"]["issue_id"]) == {"a"}
    assert set(result["persisting"]["issue_id"]) == {"b"}
