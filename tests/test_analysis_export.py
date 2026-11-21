from __future__ import annotations

import pandas as pd

from stages_cleaning.analysis_export import build_analysis_ready_frame, flag_analysis_exclusions


def _base_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "stage_id": ["a", "b", "c", "d", "e"],
        "entreprise": pd.array(["Acme", pd.NA, "SAS", "Beta", "Gamma"], dtype="string"),
        "ville": pd.array(["Paris", pd.NA, "Lyon", "Lyon", "Lyon"], dtype="string"),
        "pays": pd.array(["FR", pd.NA, "FR", "FR", "FR"], dtype="string"),
        "identity_variant_category": pd.array(["single", "single", "single", "divergence_reelle", "single"], dtype="string"),
        "entreprise_qualite": pd.array(["ok", "missing", "legal_form_only", "ok", "ok"], dtype="string"),
    })


def test_flags_each_motif_independently():
    result = flag_analysis_exclusions(_base_frame())
    by_id = result.set_index("stage_id")
    assert by_id.loc["a", "exclu_analyse"] == False
    assert pd.isna(by_id.loc["a", "motif_exclusion"])
    assert by_id.loc["b", "motif_exclusion"] == "dossier_vide"
    assert by_id.loc["c", "motif_exclusion"] == "entreprise_non_exploitable"
    assert by_id.loc["d", "motif_exclusion"] == "identite_divergente"
    assert by_id.loc["e", "exclu_analyse"] == False


def test_no_row_is_ever_dropped_by_flagging():
    result = flag_analysis_exclusions(_base_frame())
    assert len(result) == 5


def test_cumulative_motifs_are_joined():
    frame = _base_frame()
    # ligne "c" cumule entreprise non exploitable ET identité divergente
    frame.loc[frame["stage_id"] == "c", "identity_variant_category"] = "divergence_reelle"
    result = flag_analysis_exclusions(frame)
    motif = result.loc[result["stage_id"] == "c", "motif_exclusion"].iloc[0]
    assert "entreprise_non_exploitable" in motif
    assert "identite_divergente" in motif


def test_analysis_ready_frame_drops_only_flagged_rows_and_helper_columns():
    flagged = flag_analysis_exclusions(_base_frame())
    ready = build_analysis_ready_frame(flagged)
    assert set(ready["stage_id"]) == {"a", "e"}
    assert "exclu_analyse" not in ready.columns
    assert "motif_exclusion" not in ready.columns
