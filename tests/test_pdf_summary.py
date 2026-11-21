from __future__ import annotations

from datetime import datetime

import pandas as pd
from pypdf import PdfReader

from stages_cleaning.quality_reporting.pdf_summary import export_pdf_summary


def _issues() -> pd.DataFrame:
    return pd.DataFrame({
        "issue_id": ["a", "b", "c"],
        "rule_id": ["MISSING_COMPANY", "SWIM_IN_FRANCE", "COUNTRY_LOW_CONFIDENCE"],
        "priority": ["URGENT", "IMPORTANT", "INFORMATION"],
        "priority_order": [1, 2, 4],
        "category": ["Dossier incomplet", "Mobilité internationale", "Traçabilité technique"],
        "title": ["Entreprise non renseignée", "SWIM en France", "Pays inféré confiance faible"],
        "stage_id": ["stg_1", "stg_2", "stg_3"],
        "affected_rows": [1, 1, 1],
        "recommended_action": ["Compléter.", "Vérifier.", "Aucune action."],
    })


def test_export_pdf_summary_creates_readable_pdf_without_history(tmp_path):
    issues = _issues()
    path = tmp_path / "resume.pdf"
    comparison = {"new": issues.iloc[0:0], "resolved": issues.iloc[0:0], "persisting": issues.iloc[0:0]}
    export_pdf_summary(issues, comparison, total_dossiers=100, path=path, generated_at=datetime(2026, 1, 1), has_history=False)
    assert path.exists()
    reader = PdfReader(str(path))
    assert len(reader.pages) >= 1
    text = "".join(page.extract_text() or "" for page in reader.pages)
    assert "Premier rapport" in text


def test_export_pdf_summary_shows_evolution_when_history_present(tmp_path):
    issues = _issues()
    path = tmp_path / "resume.pdf"
    business = issues.loc[issues["priority"].ne("INFORMATION")]
    comparison = {
        "new": business.iloc[[0]],
        "resolved": business.iloc[[1]],
        "persisting": business.iloc[0:0],
    }
    export_pdf_summary(issues, comparison, total_dossiers=100, path=path, generated_at=datetime(2026, 1, 1), has_history=True)
    reader = PdfReader(str(path))
    text = "".join(page.extract_text() or "" for page in reader.pages)
    assert "Évolution depuis le dernier rapport" in text
