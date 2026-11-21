from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from .identity import check_identity, classify_identity_variants, normalize_identity_display, normalize_identity_key
from .normalize import normalize_city_key, normalize_country_code, normalize_text_key
from .postal import normalize_postal_code, postal_code_status, zero_lost
from .programme import VALID_YEARS

FR_CEDEX_PAIRS = {
    frozenset(pair) for pair in [
        ("92130", "92441"), ("91300", "91883"), ("78280", "78084"),
        ("92400", "92903"), ("92130", "92449"), ("94800", "94805"),
        ("75006", "75275"), ("75016", "75220"), ("92120", "92547"),
        ("33000", "33067"), ("92100", "92012"), ("92240", "92247"),
        ("93110", "93117"), ("92800", "92092"), ("75015", "75726"),
        ("78530", "78533"), ("94150", "94628"), ("31400", "31402"),
        ("75001", "75049"), ("75008", "75401"), ("92000", "92022"),
        ("75015", "75509"), ("94200", "94768"), ("94320", "94321"),
    ]
}


def add_meta(frame: pd.DataFrame, severity: str, status: str, category: str | None = None) -> pd.DataFrame:
    result = frame.copy()
    result.insert(0, "severite", severity)
    result.insert(1, "statut", status)
    if category is not None:
        result.insert(2, "categorie", category)
    return result


def _address_token_key(value) -> str:
    return " ".join(sorted(re.findall(r"[a-z0-9]+", normalize_text_key(value))))


def build_quality_report(
    raw: pd.DataFrame,
    country: pd.DataFrame,
    postal: pd.DataFrame,
    final: pd.DataFrame,
    identity_overrides: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    anomalies: dict[str, pd.DataFrame] = {}
    coverage: dict[str, tuple[int, int]] = {}
    total = len(raw)

    mask = raw[["entreprise", "adresse", "ville", "pays"]].isna().all(axis=1)
    cols = [c for c in ["stage_id", "etudiant", "email", "programme", "annee_academique", "type_stage", "libelle_stage"] if c in raw.columns]
    anomalies["lignes_sans_localisation"] = add_meta(raw.loc[mask, cols], "erreur", "a_corriger_source")
    coverage["lignes_sans_localisation"] = (total, total)

    exact = raw[raw.duplicated(subset=[c for c in raw.columns if c != "stage_id"], keep=False)].sort_values(["email", "entreprise"])
    anomalies["doublons_exacts"] = add_meta(exact, "erreur", "corrige_pipeline")
    logical_keys = ["email", "annee_academique", "type_stage", "entreprise"]
    logical = raw[raw.duplicated(subset=logical_keys, keep=False) & ~raw.index.isin(exact.index)]
    anomalies["doublons_logiques"] = add_meta(logical, "a_arbitrer", "a_verifier_source")
    coverage["doublons_exacts"] = coverage["doublons_logiques"] = (total, total)

    country_iso = raw["pays"].map(normalize_country_code).astype("string")
    postal_norm = pd.Series([normalize_postal_code(cp, c) for cp, c in zip(raw["code_postal"], country_iso)], index=raw.index, dtype="string")
    source_status = pd.Series([postal_code_status(cp, norm, c, city) for cp, norm, c, city in zip(raw["code_postal"], postal_norm, country_iso, raw["ville"])], index=raw.index, dtype="string")
    zero_mask = pd.Series([zero_lost(cp, c) for cp, c in zip(raw["code_postal"], country_iso)], index=raw.index)
    zero_report = raw.loc[zero_mask, [c for c in ["stage_id", "etudiant", "entreprise", "adresse", "code_postal", "ville", "pays"] if c in raw.columns]].copy()
    zero_report["code_postal_corrige"] = postal_norm[zero_report.index]
    anomalies["cp_zeros_perdus"] = add_meta(zero_report, "info", "corrige_pipeline")
    invalid_mask = postal["postal_code_source_status"].str.contains(r"invalid_format|not_postal_code|suspicious_placeholder", regex=True, na=False)
    invalid_cols = [c for c in ["stage_id", "etudiant", "email", "entreprise", "adresse", "code_postal_source_raw", "code_postal_normalized_source", "code_postal", "ville", "pays", "postal_code_source_status", "postal_code_final_status", "postal_code_resolution_method"] if c in postal.columns]
    invalid_report = postal.loc[invalid_mask, invalid_cols].copy()
    invalid_report.insert(0, "severite", "erreur")
    invalid_report.insert(1, "statut", "a_corriger_source")
    invalid_report.loc[invalid_report["code_postal"].notna() & ~invalid_report["postal_code_final_status"].str.startswith("unvalidated", na=False), "statut"] = "corrige_pipeline"
    anomalies["cp_source_invalides"] = invalid_report
    coverage["cp_zeros_perdus"] = coverage["cp_source_invalides"] = (total, total)

    mask = ~raw["email"].str.endswith("@efrei.net", na=False)
    anomalies["emails_personnels"] = add_meta(raw.loc[mask, [c for c in ["stage_id", "etudiant", "email", "programme", "annee_academique"] if c in raw.columns]].drop_duplicates(), "a_arbitrer", "a_verifier_source")
    coverage["emails_personnels"] = (total, total)

    issues = raw[[c for c in ["stage_id", "etudiant", "email", "programme", "annee_academique"] if c in raw.columns]].copy()
    issues["anomalie"] = [check_identity(e, m) for e, m in zip(raw["etudiant"], raw["email"])]
    issues = issues[issues["anomalie"].notna()].drop_duplicates(subset=["stage_id"] if "stage_id" in issues.columns else ["etudiant", "email"])
    correction_keys = {normalize_identity_key(v) for v in identity_overrides["source_identity"].dropna()} if not identity_overrides.empty else set()
    corrected_mask = issues["etudiant"].map(normalize_identity_key).isin(correction_keys)
    issues["statut"] = "a_verifier_source"; issues.loc[corrected_mask, "statut"] = "corrige_pipeline"
    sev_map = {"prenom_et_nom_differents": "erreur", "nom_different": "erreur", "prenom_different": "a_arbitrer", "email_sans_separateur": "a_arbitrer"}
    issues["severite"] = issues["anomalie"].map(sev_map).fillna("a_arbitrer"); issues.loc[corrected_mask, "severite"] = "info"
    anomalies["identite_vs_email"] = issues[["severite", "statut", "anomalie"] + [c for c in issues.columns if c not in {"severite", "statut", "anomalie"}]]
    coverage["identite_vs_email"] = (int(raw["email"].notna().sum()), total)

    variants = raw.assign(_id=raw["etudiant"].map(normalize_identity_display)).groupby("email")["_id"].agg(lambda s: sorted(s.unique())).loc[lambda s: s.str.len() > 1].reset_index().rename(columns={"_id": "_graphies_list"})
    variants["categorie"] = variants["_graphies_list"].map(classify_identity_variants)
    variants["n_graphies"] = variants["_graphies_list"].str.len(); variants["graphies"] = variants["_graphies_list"].str.join("  |  "); variants = variants.drop(columns="_graphies_list")
    severity = {"divergence_reelle": "erreur", "accents_espaces": "info", "prenoms_secondaires": "info"}
    status = {"divergence_reelle": "a_verifier_source", "accents_espaces": "harmonise_pipeline", "prenoms_secondaires": "harmonise_pipeline"}
    variants["severite"] = variants["categorie"].map(severity); variants["statut"] = variants["categorie"].map(status)
    anomalies["graphies_multiples"] = variants[["severite", "statut", "categorie", "email", "n_graphies", "graphies"]]
    coverage["graphies_multiples"] = (int(raw["email"].notna().sum()), total)

    ref = raw.dropna(subset=["adresse", "ville", "code_postal"]).copy()
    ref["_addr"] = ref["adresse"].map(_address_token_key); ref["_city"] = ref["ville"].map(normalize_city_key); ref["_country"] = ref["pays"].map(normalize_country_code)
    ref["_cp_norm"] = pd.Series([normalize_postal_code(cp, c) for cp, c in zip(ref["code_postal"], ref["_country"])], index=ref.index, dtype="string")
    conflicts = ref.groupby(["_addr", "_city"])["code_postal"].nunique(); keys = conflicts[conflicts > 1].index
    conflicting = ref.loc[pd.MultiIndex.from_frame(ref[["_addr", "_city"]]).isin(keys)].copy()
    rows = []
    for _, group in conflicting.groupby(["_addr", "_city"]):
        raw_codes = sorted(group["code_postal"].dropna().unique()); norm_codes = sorted(group["_cp_norm"].dropna().unique()); pair = frozenset(norm_codes)
        has_cedex = group["ville"].str.contains(r"(?i)\bcedex\b", na=False).any() or group["adresse"].str.contains(r"(?i)\bcedex\b", na=False).any()
        if len(norm_codes) == 1:
            cat, sev, stat = "formatage_uniquement", "info", "corrige_pipeline"
        elif pair == frozenset({"75016", "75116"}):
            cat, sev, stat = "paris_16_deux_codes_valides", "info", "variation_legitime"
        elif pair in FR_CEDEX_PAIRS:
            cat, sev, stat = "cedex_vs_voirie_verifie", "info", "variation_legitime"
        elif has_cedex and set(group["_country"].dropna().unique()) <= {"FR"}:
            cat, sev, stat = "cedex_detecte_non_verifie", "a_arbitrer", "a_verifier_source"
        else:
            cat, sev, stat = "conflit_residuel", "a_arbitrer", "a_verifier_source"
        for idx in group.index:
            rows.append({"severite": sev, "statut": stat, "categorie": cat, "stage_id": group.at[idx, "stage_id"] if "stage_id" in group.columns else pd.NA, "entreprise": group.at[idx, "entreprise"], "adresse": group.at[idx, "adresse"], "code_postal_source": group.at[idx, "code_postal"], "code_postal_normalise": group.at[idx, "_cp_norm"], "ville": group.at[idx, "ville"], "pays": group.at[idx, "pays"], "codes_source_du_groupe": " | ".join(raw_codes), "codes_normalises_du_groupe": " | ".join(norm_codes)})
    anomalies["cp_incoherents"] = pd.DataFrame(rows, columns=["severite", "statut", "categorie", "stage_id", "entreprise", "adresse", "code_postal_source", "code_postal_normalise", "ville", "pays", "codes_source_du_groupe", "codes_normalises_du_groupe"])
    coverage["cp_incoherents"] = (len(ref), total)

    cross = raw.copy(); cross["_city"] = cross["ville"].map(normalize_city_key).replace("", pd.NA); cross["_country"] = cross["pays"].map(normalize_country_code)
    trusted_methods = country["country_resolution_method"].astype("string").str.contains(r"geocode|manual_override", regex=True, na=False)
    trusted_geo = country.loc[trusted_methods, ["ville", "pays"]].dropna().copy(); trusted_geo["_city"] = trusted_geo["ville"].map(normalize_city_key).replace("", pd.NA); trusted_geo["_country"] = trusted_geo["pays"].map(normalize_country_code)
    sets = trusted_geo.groupby("_city")["_country"].agg(lambda s: sorted(set(s.dropna())))
    ref_country = sets[sets.str.len() == 1].map(lambda x: x[0])
    cross["pays_reference_ville"] = cross["_city"].map(ref_country)
    mask_country = cross["_country"].notna() & cross["pays_reference_ville"].notna() & cross["_country"].fillna("").ne(cross["pays_reference_ville"].fillna(""))
    cols = [c for c in ["stage_id", "etudiant", "email", "entreprise", "adresse", "code_postal", "ville", "pays"] if c in cross.columns]
    report = cross.loc[mask_country, cols].copy(); report["pays_iso_source"] = cross.loc[mask_country, "_country"]; report["pays_reference_ville"] = cross.loc[mask_country, "pays_reference_ville"]
    report = add_meta(report, "erreur", "a_verifier_source")
    corrected_stage_ids = set(country.loc[country["country_resolution_method"].eq("source_conflict_corrected_city_geocode"), "stage_id"].dropna())
    if "stage_id" in report.columns:
        report.loc[report["stage_id"].isin(corrected_stage_ids), "statut"] = "corrige_pipeline"
    anomalies["coherence_ville_pays"] = report
    controllable_country = int(cross["pays_reference_ville"].notna().sum()); coverage["coherence_ville_pays"] = (controllable_country, total)

    fr = cross[cross["_country"].eq("FR")].copy(); fr["_cp"] = pd.Series([normalize_postal_code(cp, "FR") for cp in fr["code_postal"]], index=fr.index, dtype="string"); fr["_dept"] = fr["_cp"].where(fr["_cp"].str.fullmatch(r"\d{5}", na=False)).str[:2]
    dept_counts = fr.dropna(subset=["_city", "_dept"]).groupby(["_city", "_dept"]).size().rename("n").reset_index(); dept_total = dept_counts.groupby("_city")["n"].sum().rename("total")
    ranked = dept_counts.sort_values(["_city", "n"], ascending=[True, False]).drop_duplicates("_city").join(dept_total, on="_city"); ranked["dominance"] = ranked["n"] / ranked["total"]
    city_dept_ref = ranked[(ranked["n"] >= 50) & (ranked["dominance"] >= 0.97)].set_index("_city")["_dept"]
    fr["dept_reference_ville"] = fr["_city"].map(city_dept_ref); mask_dept = fr["_dept"].notna() & fr["dept_reference_ville"].notna() & fr["_dept"].fillna("").ne(fr["dept_reference_ville"].fillna(""))
    cols = [c for c in ["stage_id", "etudiant", "email", "entreprise", "adresse", "code_postal", "ville", "pays"] if c in fr.columns]
    report = fr.loc[mask_dept, cols].copy(); report["departement_cp"] = fr.loc[mask_dept, "_dept"]; report["departement_reference_ville"] = fr.loc[mask_dept, "dept_reference_ville"]
    anomalies["coherence_ville_cp_fr"] = add_meta(report, "erreur", "a_verifier_source"); coverage["coherence_ville_cp_fr"] = (int(fr["dept_reference_ville"].notna().sum()), total)

    cols = [c for c in ["stage_id", "prenom", "nom", "email", "entreprise", "adresse", "ville", "pays", "code_postal_source_raw", "postal_code_source_status", "postal_code_final_status"] if c in postal.columns]
    unresolved_country = country[country["country_resolution_method"].eq("unresolved")]
    unresolved_cp = postal[postal["postal_code_final_status"].eq("unresolved")]
    anomalies["pays_non_resolus"] = add_meta(unresolved_country[[c for c in cols if c in unresolved_country.columns]], "a_arbitrer", "a_completer_source")
    anomalies["cp_non_resolus"] = add_meta(unresolved_cp[cols], "a_arbitrer", "a_completer_source")
    coverage["pays_non_resolus"] = coverage["cp_non_resolus"] = (total, total)

    # Programme / features finales
    program_present = final["programme"].notna(); unparsed = final.loc[program_present & final["real_program"].isna()]
    anomalies["programmes_non_reconnus"] = add_meta(unparsed[[c for c in ["stage_id", "programme"] if c in unparsed.columns]], "erreur", "a_corriger_pipeline")
    invalid_year = pd.Series(False, index=final.index)
    for program, years in VALID_YEARS.items():
        invalid_year |= final["real_program"].eq(program) & ~final["program_year"].astype("Int64").isin(years)
    year_report = final.loc[invalid_year, [c for c in ["stage_id", "programme", "real_program", "program_year"] if c in final.columns]]
    anomalies["programme_annee_invalide"] = add_meta(year_report, "erreur", "a_corriger_pipeline")
    coverage["programmes_non_reconnus"] = coverage["programme_annee_invalide"] = (int(program_present.sum()), total)

    # Synthèse avec couverture explicite
    summary_rows = []
    for name, frame in anomalies.items():
        checked, denominator = coverage.get(name, (total, total))
        pct = round(checked / denominator * 100, 2) if denominator else 0.0
        if frame.empty:
            summary_rows.append({"anomalie": name, "severite": "—", "nb_lignes": 0, "lignes_controlables": checked, "couverture_pct": pct})
        elif "severite" in frame.columns:
            for sev, count in frame["severite"].value_counts().items():
                summary_rows.append({"anomalie": name, "severite": sev, "nb_lignes": int(count), "lignes_controlables": checked, "couverture_pct": pct})
        else:
            summary_rows.append({"anomalie": name, "severite": "—", "nb_lignes": len(frame), "lignes_controlables": checked, "couverture_pct": pct})
    summary = pd.DataFrame(summary_rows)
    order = pd.Categorical(summary["severite"], categories=["erreur", "a_arbitrer", "info", "—"], ordered=True)
    summary = summary.assign(_order=order).sort_values(["_order", "nb_lignes"], ascending=[True, False]).drop(columns="_order")
    return summary, anomalies


def export_quality_report(summary: pd.DataFrame, anomalies: dict[str, pd.DataFrame], path: str | Path) -> None:
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        summary.to_excel(writer, sheet_name="synthese", index=False)
        for name, frame in anomalies.items():
            frame.to_excel(writer, sheet_name=name[:31], index=False)
