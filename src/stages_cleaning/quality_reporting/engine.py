from __future__ import annotations

import hashlib

import pandas as pd

from .rules import RULES

ISSUE_COLUMNS = [
    "issue_id", "rule_id", "priority", "priority_order", "category", "title",
    "status", "entity_key", "stage_id", "email", "etudiant", "annee_academique",
    "type_stage", "entreprise", "ville", "pays", "affected_rows",
    "message_business", "recommended_action", "message_technical", "source_dataset",
]


def _issue_id(rule_id: str, entity_key: object) -> str:
    payload = f"{rule_id}|{entity_key}".encode("utf-8")
    return "qi_" + hashlib.sha1(payload).hexdigest()[:16]


def _as_bool(series: pd.Series) -> pd.Series:
    if str(series.dtype) == "boolean":
        return series.fillna(False)
    return series.astype("string").str.strip().str.lower().map({"true": True, "false": False}).fillna(False)


def _safe_value(row: pd.Series, column: str):
    return row[column] if column in row.index else pd.NA


def _issue(rule_id: str, entity_key: object, row: pd.Series | None, *, message_business: str,
           message_technical: str, source_dataset: str, affected_rows: int = 1,
           status: str = "OPEN") -> dict:
    rule = RULES[rule_id]
    row = row if row is not None else pd.Series(dtype="object")
    return {
        "issue_id": _issue_id(rule_id, entity_key),
        "rule_id": rule.rule_id,
        "priority": rule.priority,
        "priority_order": rule.priority_order,
        "category": rule.category,
        "title": rule.title,
        "status": status,
        "entity_key": str(entity_key),
        "stage_id": _safe_value(row, "stage_id"),
        "email": _safe_value(row, "email"),
        "etudiant": _safe_value(row, "etudiant"),
        "annee_academique": _safe_value(row, "annee_academique"),
        "type_stage": _safe_value(row, "type_stage"),
        "entreprise": _safe_value(row, "entreprise"),
        "ville": _safe_value(row, "ville"),
        "pays": _safe_value(row, "pays"),
        "affected_rows": int(affected_rows),
        "message_business": message_business,
        "recommended_action": rule.action,
        "message_technical": message_technical,
        "source_dataset": source_dataset,
    }


def _append_stage_rows(issues: list[dict], frame: pd.DataFrame, mask: pd.Series, rule_id: str, *,
                       message_business: str, message_technical: str, source_dataset: str) -> None:
    for idx, row in frame.loc[mask].iterrows():
        issues.append(_issue(
            rule_id,
            row.get("stage_id", idx),
            row,
            message_business=message_business,
            message_technical=message_technical,
            source_dataset=source_dataset,
        ))


def build_business_issues(raw: pd.DataFrame, final: pd.DataFrame,
                          country: pd.DataFrame, postal: pd.DataFrame,
                          company_merge_decisions: pd.DataFrame | None = None) -> pd.DataFrame:
    """Create the normalized issue registry used by both reports.

    Rules are conservative: they flag inconsistencies for human review without asserting
    a correction when the data does not prove which field is wrong.
    """
    issues: list[dict] = []

    duplicate_counts = raw.groupby("stage_id", dropna=False).size()
    for stage_id, occurrences in duplicate_counts[duplicate_counts > 1].items():
        row = raw.loc[raw["stage_id"].eq(stage_id)].iloc[0]
        issues.append(_issue(
            "DUPLICATE_EXACT_STAGE", stage_id, row,
            affected_rows=int(occurrences), source_dataset="raw",
            message_business=(f"Le même stage apparaît {int(occurrences)} fois dans le fichier source "
                              f"({int(occurrences) - 1} ligne(s) en trop)."),
            message_technical=f"stage_id={stage_id} possède {int(occurrences)} occurrences strictement identiques.",
        ))

    company_missing = final["entreprise"].isna() | final["entreprise"].astype("string").str.strip().eq("")
    _append_stage_rows(issues, final, company_missing, "MISSING_COMPANY",
                       message_business="Aucune entreprise d'accueil n'est renseignée pour ce stage.",
                       message_technical="entreprise est NULL ou vide après trim dans le dataset final.",
                       source_dataset="final")

    if "entreprise_qualite" in final.columns:
        suspect_company = final["entreprise_qualite"].isin(["legal_form_only", "generic_label"])
    else:
        suspect_company = pd.Series(False, index=final.index)
    _append_stage_rows(issues, final, suspect_company, "COMPANY_QUALITY_SUSPECT",
                       message_business="Le nom d'entreprise ne permet pas d'identifier l'employeur.",
                       message_technical="entreprise_qualite in ('legal_form_only','generic_label').",
                       source_dataset="final")

    location_columns = [c for c in ["adresse", "code_postal", "ville", "pays"] if c in final.columns]
    location_missing = final[location_columns].isna().all(axis=1)
    _append_stage_rows(issues, final, location_missing, "MISSING_LOCATION",
                       message_business="Aucune localisation exploitable n'est disponible pour ce stage.",
                       message_technical=f"Toutes les colonnes {location_columns} sont NULL.",
                       source_dataset="final")

    swim = _as_bool(final["is_swim_stage"])
    swim_fr = swim & final["pays"].eq("FR")
    _append_stage_rows(issues, final, swim_fr, "SWIM_IN_FRANCE",
                       message_business=("Ce stage est enregistré comme SWIM mais la localisation actuelle est en France. "
                                         "Le type de stage ou la localisation doit être vérifié."),
                       message_technical="is_swim_stage=True AND pays='FR'.", source_dataset="final")

    swim_country_unknown = swim & final["pays"].isna()
    _append_stage_rows(issues, final, swim_country_unknown, "SWIM_COUNTRY_UNKNOWN",
                       message_business="Ce stage est enregistré comme SWIM mais aucun pays n'a pu être déterminé.",
                       message_technical="is_swim_stage=True AND pays IS NULL.", source_dataset="final")

    programme_unrecognized = final["programme"].notna() & final["real_program"].isna()
    _append_stage_rows(issues, final, programme_unrecognized, "PROGRAMME_UNRECOGNIZED",
                       message_business="Le programme renseigné n'est pas reconnu par les règles actuelles.",
                       message_technical="programme IS NOT NULL AND real_program IS NULL.", source_dataset="final")

    if "major_canonical_status" in final.columns:
        major_unknown = final["major_canonical"].notna() & final["major_canonical_status"].isna()
        _append_stage_rows(issues, final, major_unknown, "MAJOR_UNKNOWN",
                           message_business="La majeure renseignée n'est couverte par aucune règle de rattachement connue.",
                           message_technical="major_canonical IS NOT NULL AND major_canonical_status IS NULL.",
                           source_dataset="final")

        major_pending = final["major_canonical_status"].eq("pending_review")
        _append_stage_rows(issues, final, major_pending, "MAJOR_PENDING_REVIEW",
                           message_business="Cette majeure n'a pas encore de nom officiel confirmé (programme réel mais absent du menu actuel du site).",
                           message_technical="major_canonical_status='pending_review'.",
                           source_dataset="final")

    country_unresolved = country["country_resolution_method"].eq("unresolved")
    _append_stage_rows(issues, country, country_unresolved, "COUNTRY_UNRESOLVED",
                       message_business="Le pays du stage n'a pas pu être déterminé à partir des données disponibles.",
                       message_technical="country_resolution_method='unresolved'.", source_dataset="country_interim")

    postal_unresolved = postal["postal_code_final_status"].eq("unresolved")
    _append_stage_rows(issues, postal, postal_unresolved, "POSTAL_UNRESOLVED",
                       message_business="Aucun code postal final exploitable n'est disponible pour ce stage.",
                       message_technical="postal_code_final_status='unresolved'.", source_dataset="postal_interim")

    suspicious_postal = postal["postal_code_source_status"].eq("suspicious_placeholder")
    _append_stage_rows(issues, postal, suspicious_postal, "POSTAL_SUSPICIOUS_SOURCE",
                       message_business="La valeur renseignée comme code postal ressemble à une valeur fictive ou de remplissage.",
                       message_technical="postal_code_source_status='suspicious_placeholder'.", source_dataset="postal_interim")

    identity_rows = final.loc[_as_bool(final["identity_requires_review"])].copy()
    for email, group in identity_rows.groupby("email", dropna=False):
        representations = sorted(group["etudiant"].dropna().astype(str).unique())
        issues.append(_issue(
            "IDENTITY_REAL_DIVERGENCE", email, group.iloc[0], affected_rows=len(group), source_dataset="final",
            message_business=("Plusieurs identités réellement différentes sont associées au même email : "
                              + " | ".join(representations)),
            message_technical=f"identity_variant_category='divergence_reelle'; variantes={representations!r}.",
        ))

    low_confidence = country["country_resolution_confidence"].isin(["low", "geocoded_low"])
    _append_stage_rows(issues, country, low_confidence, "COUNTRY_LOW_CONFIDENCE",
                       message_business="Le pays a été inféré avec un niveau de preuve faible.",
                       message_technical="country_resolution_confidence in ('low','geocoded_low').",
                       source_dataset="country_interim")

    unsupported_pattern = postal["postal_code_final_status"].eq("unvalidated_pattern_unsupported")
    _append_stage_rows(issues, postal, unsupported_pattern, "POSTAL_PATTERN_UNSUPPORTED",
                       message_business="Le code postal est conservé mais son format n'est pas couvert par les règles actuelles.",
                       message_technical="postal_code_final_status='unvalidated_pattern_unsupported'.",
                       source_dataset="postal_interim")

    if company_merge_decisions is not None and not company_merge_decisions.empty and "decision" in company_merge_decisions.columns:
        pending = company_merge_decisions["decision"].fillna("").astype(str).str.strip().eq("")
        n_pending = int(pending.sum())
        if n_pending:
            issues.append(_issue(
                "COMPANY_MERGE_DECISIONS_PENDING", "company_merge_decisions", None,
                affected_rows=n_pending, source_dataset="company_merge_decisions",
                message_business=f"{n_pending} paire(s) d'entreprises candidates à une fusion n'ont pas encore de décision.",
                message_technical="company_merge_decisions.csv: decision vide.",
            ))

    if not issues:
        return pd.DataFrame(columns=ISSUE_COLUMNS)
    return pd.DataFrame(issues, columns=ISSUE_COLUMNS).sort_values(
        ["priority_order", "rule_id", "annee_academique", "email"], na_position="last"
    ).reset_index(drop=True)


def build_business_summary(issues: pd.DataFrame) -> pd.DataFrame:
    columns = ["priority", "priority_order", "category", "rule_id", "title",
               "cases_detected", "rows_affected", "recommended_action"]
    if issues.empty:
        return pd.DataFrame(columns=columns)
    grouped = issues.groupby(
        ["priority", "priority_order", "category", "rule_id", "title", "recommended_action"],
        dropna=False, as_index=False,
    ).agg(cases_detected=("issue_id", "nunique"), rows_affected=("affected_rows", "sum"))
    grouped = grouped.sort_values(["priority_order", "cases_detected", "rule_id"], ascending=[True, False, True])
    return grouped[columns]


def build_aggregate_view(issues: pd.DataFrame) -> pd.DataFrame:
    """Regroupe les règles à fort volume (`display_mode="aggregate"`) par promotion et type de
    stage plutôt que de lister chaque cas individuellement.

    Ces règles (ex. pays non déterminé sur des centaines de lignes) sont réelles mais peu
    actionnables une par une pour un lecteur métier : le compte par promotion/type de stage donne
    une vision exploitable (« telle promo a X dossiers concernés ») sans noyer le rapport. Le
    détail nominatif reste disponible dans le rapport technique (feuille `ALL_ISSUES`).
    """
    columns = ["priority", "category", "title", "annee_academique", "type_stage", "cases", "recommended_action"]
    aggregate_rule_ids = {rule_id for rule_id, rule in RULES.items() if rule.display_mode == "aggregate"}
    subset = issues.loc[issues["rule_id"].isin(aggregate_rule_ids)]
    if subset.empty:
        return pd.DataFrame(columns=columns)
    grouped = subset.groupby(
        ["priority", "category", "title", "annee_academique", "type_stage", "recommended_action"],
        dropna=False, as_index=False,
    ).agg(cases=("issue_id", "nunique"))
    grouped = grouped.sort_values(["cases"], ascending=False)
    return grouped[columns]
