from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from stages_cleaning.config import load_csv_config
from stages_cleaning.paths import dataset_paths
from stages_cleaning.provenance import build_stage_id
from stages_cleaning.quality import build_quality_report

from .engine import build_business_issues
from .history import compare_issues, load_previous_snapshot, save_snapshot
from .pdf_summary import export_pdf_summary
from .reports import export_business_report, export_technical_report


@dataclass(frozen=True)
class QualityReportPaths:
    business_report: Path
    technical_report: Path
    issue_registry: Path
    pdf_summary: Path


def _read_csv(path: Path, *, sep: str = ",") -> pd.DataFrame:
    return pd.read_csv(path, sep=sep, dtype="string", encoding="utf-8-sig", keep_default_na=False).replace("", pd.NA)


def generate_quality_reports(root: str | Path, run_at: datetime | None = None) -> QualityReportPaths:
    root = Path(root).resolve()
    dataset = dataset_paths(root)
    raw = _read_csv(dataset.raw, sep=";")
    if "stage_id" not in raw.columns:
        raw.insert(0, "stage_id", build_stage_id(raw))
    country = _read_csv(root / "data/interim/stages_efrei_with_country.csv")
    postal = _read_csv(root / "data/interim/stages_efrei_with_postal_code.csv")
    final = _read_csv(root / "data/processed/stages_efrei_final.csv")
    overrides = load_csv_config(dataset.identity_overrides, {"source_identity", "corrected_identity", "reason"})
    merge_decisions_path = root / "data/reference/company_merge_decisions.csv"
    company_merge_decisions = load_csv_config(
        merge_decisions_path, {"entreprise_1", "entreprise_2", "decision", "entreprise_canonique"}
    )

    issues = build_business_issues(raw, final, country, postal, company_merge_decisions)
    technical_summary, technical_anomalies = build_quality_report(raw, country, postal, final, overrides)

    report_dir = root / "data/reports"
    history_dir = report_dir / "history"
    report_dir.mkdir(parents=True, exist_ok=True)
    paths = QualityReportPaths(
        business_report=report_dir / "rapport_qualite_metier.xlsx",
        technical_report=report_dir / "rapport_qualite_technique.xlsx",
        issue_registry=report_dir / "quality_issues.csv",
        pdf_summary=report_dir / "resume_qualite.pdf",
    )

    # L'instantané précédent doit être chargé AVANT d'écrire celui du run courant, sinon on se
    # comparerait à soi-même.
    previous_snapshot = load_previous_snapshot(history_dir)
    business_issues = issues.loc[~issues["priority"].eq("INFORMATION")].copy()
    comparison = compare_issues(business_issues, previous_snapshot)

    export_business_report(issues, paths.business_report, total_dossiers=len(final))
    export_technical_report(issues, technical_summary, technical_anomalies, paths.technical_report)
    issues.to_csv(paths.issue_registry, index=False, encoding="utf-8-sig")
    export_pdf_summary(
        issues, comparison, total_dossiers=len(final), path=paths.pdf_summary,
        generated_at=run_at, has_history=previous_snapshot is not None,
    )
    save_snapshot(business_issues, history_dir, run_at=run_at)
    return paths
