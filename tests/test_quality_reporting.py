from __future__ import annotations

import pandas as pd

from stages_cleaning.quality_reporting.engine import build_aggregate_view, build_business_issues, build_business_summary


def _frames():
    raw = pd.DataFrame([
        {"stage_id": "s1", "email": "a@efrei.net", "etudiant": "A, ALICE", "annee_academique": "2025-2026", "type_stage": "Stage", "entreprise": "X", "ville": "Paris", "pays": "FR"},
        {"stage_id": "s1", "email": "a@efrei.net", "etudiant": "A, ALICE", "annee_academique": "2025-2026", "type_stage": "Stage", "entreprise": "X", "ville": "Paris", "pays": "FR"},
        {"stage_id": "s2", "email": "b@efrei.net", "etudiant": "B, BOB", "annee_academique": "2025-2026", "type_stage": "SWIM", "entreprise": pd.NA, "ville": "Lyon", "pays": "FR"},
    ])
    final = pd.DataFrame([
        {"stage_id": "s1", "email": "a@efrei.net", "etudiant": "A, ALICE", "annee_academique": "2025-2026", "type_stage": "Stage", "entreprise": "X", "adresse": "1 rue X", "code_postal": "75001", "ville": "Paris", "pays": "FR", "is_swim_stage": "False", "programme": "Ingénieur 1", "real_program": "Ingénieur", "identity_requires_review": "False"},
        {"stage_id": "s2", "email": "b@efrei.net", "etudiant": "B, BOB", "annee_academique": "2025-2026", "type_stage": "SWIM", "entreprise": pd.NA, "adresse": pd.NA, "code_postal": pd.NA, "ville": "Lyon", "pays": "FR", "is_swim_stage": "True", "programme": "Ingénieur 2", "real_program": "Ingénieur", "identity_requires_review": "False"},
    ])
    country = final[["stage_id", "email", "etudiant", "annee_academique", "type_stage", "entreprise", "ville", "pays"]].copy()
    country["country_resolution_method"] = ["source", "source"]
    country["country_resolution_confidence"] = ["high", "high"]
    postal = final[["stage_id", "email", "etudiant", "annee_academique", "type_stage", "entreprise", "ville", "pays"]].copy()
    postal["postal_code_final_status"] = ["valid_country_pattern", "unresolved"]
    postal["postal_code_source_status"] = ["valid", "missing"]
    return raw, final, country, postal


def test_business_rules_prioritize_duplicate_missing_company_and_swim_france():
    raw, final, country, postal = _frames()
    issues = build_business_issues(raw, final, country, postal)
    counts = issues["rule_id"].value_counts().to_dict()
    assert counts["DUPLICATE_EXACT_STAGE"] == 1
    assert counts["MISSING_COMPANY"] == 1
    assert counts["SWIM_IN_FRANCE"] == 1
    duplicate = issues.loc[issues["rule_id"].eq("DUPLICATE_EXACT_STAGE")].iloc[0]
    assert duplicate["affected_rows"] == 2
    assert duplicate["priority"] == "URGENT"


def test_summary_distinguishes_cases_and_affected_rows():
    raw, final, country, postal = _frames()
    issues = build_business_issues(raw, final, country, postal)
    summary = build_business_summary(issues)
    duplicate = summary.loc[summary["rule_id"].eq("DUPLICATE_EXACT_STAGE")].iloc[0]
    assert duplicate["cases_detected"] == 1
    assert duplicate["rows_affected"] == 2


def test_identity_divergence_is_grouped_by_email():
    raw, final, country, postal = _frames()
    template = final.iloc[0].to_dict()
    extra = pd.DataFrame([
        {**template, "stage_id": "s3", "email": "same@efrei.net", "etudiant": "DUPONT, JEAN", "identity_requires_review": "True"},
        {**template, "stage_id": "s4", "email": "same@efrei.net", "etudiant": "MARTIN, PAUL", "identity_requires_review": "True"},
    ])
    final = pd.concat([final, extra], ignore_index=True)
    country_extra = extra[["stage_id", "email", "etudiant", "annee_academique", "type_stage", "entreprise", "ville", "pays"]].copy()
    country_extra["country_resolution_method"] = "source"
    country_extra["country_resolution_confidence"] = "high"
    country = pd.concat([country, country_extra], ignore_index=True)
    postal_extra = extra[["stage_id", "email", "etudiant", "annee_academique", "type_stage", "entreprise", "ville", "pays"]].copy()
    postal_extra["postal_code_final_status"] = "valid_country_pattern"
    postal_extra["postal_code_source_status"] = "valid"
    postal = pd.concat([postal, postal_extra], ignore_index=True)
    issues = build_business_issues(raw, final, country, postal)
    identity = issues.loc[issues["rule_id"].eq("IDENTITY_REAL_DIVERGENCE")]
    assert len(identity) == 1
    assert identity.iloc[0]["affected_rows"] == 2


def test_aggregate_view_groups_high_volume_rules_by_promotion_and_type():
    raw, final, country, postal = _frames()
    country["country_resolution_method"] = ["unresolved", "unresolved"]
    issues = build_business_issues(raw, final, country, postal)
    aggregate = build_aggregate_view(issues)
    assert set(aggregate["title"]) == {"Pays non déterminé", "Code postal non résolu"}
    row = aggregate.loc[aggregate["annee_academique"].eq("2025-2026") & aggregate["type_stage"].eq("Stage")].iloc[0]
    assert row["cases"] == 1


def test_aggregate_view_excludes_low_volume_detail_rules():
    raw, final, country, postal = _frames()
    issues = build_business_issues(raw, final, country, postal)
    aggregate = build_aggregate_view(issues)
    assert "MISSING_COMPANY" not in set(issues.loc[issues["issue_id"].isin(aggregate.index), "rule_id"])
    assert aggregate.empty or "Entreprise non renseignée" not in set(aggregate["title"])
