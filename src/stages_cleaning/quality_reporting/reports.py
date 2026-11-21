from __future__ import annotations

from pathlib import Path

import pandas as pd

from .engine import build_aggregate_view, build_business_summary
from .rules import RULES

HEADER_COLOR = "#1F4E78"
PRIORITY_COLORS = {
    "URGENT": "#F4CCCC",
    "IMPORTANT": "#FCE5CD",
    "A_VERIFIER": "#FFF2CC",
    "INFORMATION": "#DDEBF7",
}


def _safe_sheet_name(name: str) -> str:
    for char in "[]:*?/\\":
        name = name.replace(char, "_")
    return name[:31]


def _write_dataframe(writer, df: pd.DataFrame, sheet_name: str, startrow: int = 0) -> None:
    df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=startrow)
    workbook = writer.book
    worksheet = writer.sheets[sheet_name]
    header = workbook.add_format({
        "bold": True, "font_color": "#FFFFFF", "bg_color": HEADER_COLOR,
        "border": 1, "align": "center", "valign": "vcenter", "text_wrap": True,
    })
    body = workbook.add_format({"valign": "top", "text_wrap": True, "border": 1})
    for col_idx, column in enumerate(df.columns):
        worksheet.write(startrow, col_idx, column, header)
        worksheet.set_column(col_idx, col_idx, min(max(len(str(column)) + 2, 12), 38), body)
    if len(df):
        worksheet.autofilter(startrow, 0, startrow + len(df), max(len(df.columns) - 1, 0))
    worksheet.freeze_panes(startrow + 1, 0)
    worksheet.set_default_row(20)


def export_business_report(issues: pd.DataFrame, path: str | Path, total_dossiers: int | None = None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    business = issues.loc[~issues["priority"].eq("INFORMATION")].copy()
    detail_rule_ids = {rule_id for rule_id, rule in RULES.items() if rule.display_mode == "detail"}
    business_detail = business.loc[business["rule_id"].isin(detail_rule_ids)].copy()
    aggregate_view = build_aggregate_view(business)
    summary = build_business_summary(business)

    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        workbook = writer.book
        title = workbook.add_format({
            "bold": True, "font_size": 18, "font_color": "#FFFFFF",
            "bg_color": HEADER_COLOR, "align": "left", "valign": "vcenter",
        })
        subtitle = workbook.add_format({"font_size": 10, "text_wrap": True, "valign": "top"})
        kpi_label = workbook.add_format({
            "bold": True, "font_color": "#FFFFFF", "bg_color": HEADER_COLOR,
            "align": "center", "valign": "vcenter", "border": 1,
        })
        kpi_value = workbook.add_format({
            "bold": True, "font_size": 18, "align": "center", "valign": "vcenter", "border": 1,
        })
        section = workbook.add_format({"bold": True, "font_size": 12, "font_color": HEADER_COLOR})
        note = workbook.add_format({"italic": True, "font_color": "#666666", "text_wrap": True})
        body_text = workbook.add_format({"font_size": 10, "text_wrap": True, "valign": "top"})
        table_header = workbook.add_format({
            "bold": True, "font_color": "#FFFFFF", "bg_color": HEADER_COLOR,
            "border": 1, "align": "center", "valign": "vcenter", "text_wrap": True,
        })
        body = workbook.add_format({"border": 1, "valign": "top", "text_wrap": True})

        # ---------------------------------------------------------------
        # 0. Mode d'emploi — pour un lecteur qui ouvre ce fichier pour la première fois.
        # ---------------------------------------------------------------
        ws0 = workbook.add_worksheet("0_MODE_EMPLOI")
        writer.sheets["0_MODE_EMPLOI"] = ws0
        ws0.merge_range("A1:F2", "Comment lire ce rapport", title)
        ws0.set_column("A:A", 100)
        lines = [
            "Ce classeur liste les incohérences détectées automatiquement dans les données de stages. "
            "Chaque ligne signale un fait observé (donnée manquante, contradictoire ou suspecte) — "
            "aucune correction n'est appliquée automatiquement, une vérification humaine est nécessaire.",
            "",
            "Onglet 1_SYNTHESE : vue d'ensemble chiffrée, à consulter en premier.",
            "Onglet 2_URGENT : à traiter en priorité (dossiers incomplets ou dupliqués).",
            "Onglet 3_IMPORTANT : à traiter ensuite (mobilité internationale, programme non reconnu).",
            "Onglet 4_A_VERIFIER : cas isolés à vérifier au cas par cas (peu nombreux).",
            "Onglet 5_A_COMPLETER_EN_MASSE : données manquantes en grand nombre (ex. pays non renseigné "
            "sur d'anciennes promotions). Regroupées par promotion et type de stage plutôt que ligne par "
            "ligne — le détail nominatif complet reste disponible sur demande dans le rapport technique.",
            "",
            "Chaque ligne de détail explique « Pourquoi ce cas est signalé » et propose une « Action "
            "recommandée ». Un même dossier peut apparaître dans plusieurs onglets s'il cumule plusieurs "
            "signalements.",
        ]
        for i, line in enumerate(lines):
            ws0.write(3 + i, 0, line, body_text)

        # ---------------------------------------------------------------
        # 1. Synthèse
        # ---------------------------------------------------------------
        ws = workbook.add_worksheet("1_SYNTHESE")
        writer.sheets["1_SYNTHESE"] = ws

        ws.merge_range("A1:H2", "Rapport qualité métier — données de stages", title)
        ws.merge_range(
            "A3:H4",
            "Ce rapport priorise les cas nécessitant une action ou une vérification humaine. "
            "Un signalement indique une incohérence ou une information manquante ; il ne constitue pas une correction automatique. "
            "Voir l'onglet 0_MODE_EMPLOI pour le détail de chaque onglet.",
            subtitle,
        )

        counts = business.groupby("priority")["issue_id"].nunique().to_dict()
        total = int(total_dossiers) if total_dossiers is not None else int(issues["stage_id"].nunique())
        dossiers_concernes = int(business["stage_id"].nunique())
        kpis = [
            ("URGENT", int(counts.get("URGENT", 0))),
            ("IMPORTANT", int(counts.get("IMPORTANT", 0))),
            ("À VÉRIFIER", int(counts.get("A_VERIFIER", 0))),
            ("DOSSIERS CONCERNÉS", f"{dossiers_concernes} / {total}"),
        ]
        for (label, value), col in zip(kpis, [0, 2, 4, 6]):
            ws.merge_range(5, col, 5, col + 1, label, kpi_label)
            ws.merge_range(6, col, 7, col + 1, value, kpi_value)

        ws.write("A9", (
            "Les cas URGENT et IMPORTANT sont à traiter en premier. Un même dossier peut cumuler plusieurs "
            "signalements. « Dossiers concernés » = nombre de dossiers avec au moins un signalement, sur le "
            "nombre total de dossiers analysés."
        ), note)
        ws.write(9, 0, "Synthèse des règles déclenchées", section)

        summary_display = summary.rename(columns={
            "priority": "Priorité",
            "category": "Catégorie",
            "title": "Problème",
            "cases_detected": "Cas détectés",
            "rows_affected": "Lignes concernées",
            "recommended_action": "Action recommandée",
        }).drop(columns=["priority_order", "rule_id"], errors="ignore")
        summary_display = summary_display[["Priorité", "Catégorie", "Problème", "Cas détectés", "Lignes concernées", "Action recommandée"]]
        summary_display.to_excel(writer, sheet_name="1_SYNTHESE", index=False, startrow=10)
        for col_idx, column in enumerate(summary_display.columns):
            ws.write(10, col_idx, column, table_header)
        widths = [14, 28, 44, 14, 16, 60]
        for col_idx, width in enumerate(widths[: len(summary_display.columns)]):
            ws.set_column(col_idx, col_idx, width, body)
        if len(summary_display):
            ws.autofilter(10, 0, 10 + len(summary_display), len(summary_display.columns) - 1)
        ws.freeze_panes(11, 0)

        priority_series = pd.DataFrame({
            "Priorité": ["URGENT", "IMPORTANT", "A_VERIFIER"],
            "Cas": [int(counts.get(p, 0)) for p in ["URGENT", "IMPORTANT", "A_VERIFIER"]],
        })
        priority_series.to_excel(writer, sheet_name="1_SYNTHESE", index=False, startrow=10, startcol=8)
        chart = workbook.add_chart({"type": "column"})
        chart.add_series({
            "name": "Cas",
            "categories": "='1_SYNTHESE'!$I$12:$I$14",
            "values": "='1_SYNTHESE'!$J$12:$J$14",
            "data_labels": {"value": True},
        })
        chart.set_title({"name": "Cas par niveau de priorité"})
        chart.set_legend({"none": True})
        chart.set_y_axis({"major_gridlines": {"visible": False}, "min": 0})
        ws.insert_chart("I16", chart, {"x_scale": 1.15, "y_scale": 1.15})
        ws.set_column("I:J", 16)

        # ---------------------------------------------------------------
        # 2-4. Détail par priorité (uniquement les règles à volume raisonnable)
        # ---------------------------------------------------------------
        detail_columns = [
            "priority", "category", "title", "etudiant", "email", "annee_academique",
            "type_stage", "entreprise", "ville", "pays", "message_business", "recommended_action",
        ]
        detail_names = {
            "priority": "Priorité", "category": "Catégorie", "title": "Problème",
            "etudiant": "Étudiant", "email": "Email", "annee_academique": "Année académique",
            "type_stage": "Type de stage", "entreprise": "Entreprise", "ville": "Ville",
            "pays": "Pays", "message_business": "Pourquoi ce cas est signalé",
            "recommended_action": "Action recommandée",
        }
        for priority, sheet_name in {
            "URGENT": "2_URGENT", "IMPORTANT": "3_IMPORTANT", "A_VERIFIER": "4_A_VERIFIER"
        }.items():
            subset = business_detail.loc[business_detail["priority"].eq(priority), detail_columns].rename(columns=detail_names)
            _write_dataframe(writer, subset, sheet_name)
            worksheet = writer.sheets[sheet_name]
            worksheet.set_column(0, 0, 14)
            worksheet.set_column(1, 2, 28)
            worksheet.set_column(3, 4, 34)
            worksheet.set_column(5, 9, 20)
            worksheet.set_column(10, 11, 62)
            if len(subset):
                priority_format = workbook.add_format({"bg_color": PRIORITY_COLORS[priority], "bold": True})
                worksheet.conditional_format(1, 0, len(subset), 0, {
                    "type": "text", "criteria": "containing", "value": priority, "format": priority_format,
                })

        # ---------------------------------------------------------------
        # 5. Données manquantes en masse — agrégées, pas ligne par ligne.
        # ---------------------------------------------------------------
        aggregate_view = aggregate_view.assign(cases=aggregate_view["cases"].astype(int)) if len(aggregate_view) else aggregate_view
        aggregate_display = aggregate_view.rename(columns={
            "priority": "Priorité", "category": "Catégorie", "title": "Problème",
            "annee_academique": "Année académique", "type_stage": "Type de stage",
            "cases": "Dossiers concernés", "recommended_action": "Action recommandée",
        })
        _write_dataframe(writer, aggregate_display, "5_A_COMPLETER_EN_MASSE")
        worksheet = writer.sheets["5_A_COMPLETER_EN_MASSE"]
        worksheet.set_column(0, 2, 22)
        worksheet.set_column(3, 4, 22)
        worksheet.set_column(5, 5, 16)
        worksheet.set_column(6, 6, 60)
        if len(aggregate_display):
            worksheet.write(len(aggregate_display) + 2, 0, (
                "Le détail nominatif (nom, email, entreprise) de ces cas est disponible dans le rapport "
                "technique, feuille ALL_ISSUES."
            ), note)


def export_technical_report(issues: pd.DataFrame, technical_summary: pd.DataFrame,
                            technical_anomalies: dict[str, pd.DataFrame], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rule_summary = build_business_summary(issues)
    rules_df = pd.DataFrame([{
        "rule_id": rule.rule_id,
        "priority": rule.priority,
        "category": rule.category,
        "title": rule.title,
        "recommended_action": rule.action,
        "audience": rule.audience,
    } for rule in RULES.values()]).sort_values(["priority", "rule_id"])

    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        _write_dataframe(writer, rule_summary, "RULE_SUMMARY")
        _write_dataframe(writer, rules_df, "RULE_CATALOG")
        _write_dataframe(writer, issues, "ALL_ISSUES")
        _write_dataframe(writer, technical_summary, "TECH_SUMMARY")
        for name, frame in technical_anomalies.items():
            _write_dataframe(writer, frame, _safe_sheet_name(name))
