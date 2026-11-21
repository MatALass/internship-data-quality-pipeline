from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from .engine import build_business_summary

HEADER_COLOR = colors.HexColor("#1F4E78")
PRIORITY_COLORS = {
    "URGENT": colors.HexColor("#F4CCCC"),
    "IMPORTANT": colors.HexColor("#FCE5CD"),
    "A_VERIFIER": colors.HexColor("#FFF2CC"),
}
PRIORITY_LABELS = {"URGENT": "URGENT", "IMPORTANT": "IMPORTANT", "A_VERIFIER": "À VÉRIFIER"}


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], textColor=colors.white, fontSize=20, leading=24),
        "subtitle": ParagraphStyle("subtitle", parent=base["Normal"], fontSize=10, textColor=colors.HexColor("#444444")),
        "section": ParagraphStyle("section", parent=base["Heading2"], textColor=HEADER_COLOR, spaceBefore=14, spaceAfter=6),
        "body": ParagraphStyle("body", parent=base["Normal"], fontSize=9, leading=12),
        "note": ParagraphStyle("note", parent=base["Normal"], fontSize=8, textColor=colors.HexColor("#666666"), leading=11),
        "kpi_label": ParagraphStyle("kpi_label", parent=base["Normal"], fontSize=9, textColor=colors.white, alignment=1),
        "kpi_value": ParagraphStyle("kpi_value", parent=base["Normal"], fontSize=18, alignment=1, leading=22),
    }


def _title_block(styles: dict, generated_at: datetime) -> list:
    title_table = Table(
        [[Paragraph("Résumé qualité — données de stages", styles["title"])]],
        colWidths=[17 * cm],
    )
    title_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), HEADER_COLOR),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    subtitle = Paragraph(
        f"Généré automatiquement le {generated_at.strftime('%d/%m/%Y à %H:%M')}. "
        "Ce document résume la qualité des données de stages et son évolution depuis le dernier "
        "rapport. Le détail complet, dossier par dossier, est disponible dans "
        "<b>rapport_qualite_metier.xlsx</b>.",
        styles["subtitle"],
    )
    return [title_table, Spacer(1, 6), subtitle]


def _kpi_block(styles: dict, counts: dict[str, int], dossiers_concernes: int, total_dossiers: int) -> Table:
    labels = ["URGENT", "IMPORTANT", "À VÉRIFIER", "DOSSIERS CONCERNÉS"]
    values = [
        str(counts.get("URGENT", 0)), str(counts.get("IMPORTANT", 0)), str(counts.get("A_VERIFIER", 0)),
        f"{dossiers_concernes} / {total_dossiers}",
    ]
    label_row = [Paragraph(label, styles["kpi_label"]) for label in labels]
    value_row = [Paragraph(value, styles["kpi_value"]) for value in values]
    table = Table([label_row, value_row], colWidths=[4.25 * cm] * 4, rowHeights=[0.8 * cm, 1.3 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_COLOR),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return table


def _summary_table(styles: dict, summary: pd.DataFrame) -> Table:
    header = ["Priorité", "Catégorie", "Problème", "Cas", "Lignes"]
    rows = [header]
    row_priorities = ["header"]
    for _, row in summary.iterrows():
        rows.append([
            PRIORITY_LABELS.get(row["priority"], row["priority"]),
            row["category"],
            row["title"],
            str(int(row["cases_detected"])),
            str(int(row["rows_affected"])),
        ])
        row_priorities.append(row["priority"])

    table = Table(rows, colWidths=[2.4 * cm, 3.4 * cm, 7.2 * cm, 1.5 * cm, 1.5 * cm], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_COLOR),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS" if False else "BACKGROUND", (0, 1), (-1, -1), colors.white),
    ]
    for i, priority in enumerate(row_priorities):
        if i == 0 or priority not in PRIORITY_COLORS:
            continue
        style.append(("BACKGROUND", (0, i), (0, i), PRIORITY_COLORS[priority]))
    table.setStyle(TableStyle(style))
    return table


def _evolution_block(styles: dict, comparison: dict[str, pd.DataFrame], has_history: bool) -> list:
    story: list = [Paragraph("Évolution depuis le dernier rapport", styles["section"])]
    if not has_history:
        story.append(Paragraph(
            "Premier rapport généré : aucun historique disponible pour établir une comparaison. "
            "Le prochain rapport comparera l'état des données à celui-ci.",
            styles["note"],
        ))
        return story

    new_counts = comparison["new"]["priority"].value_counts().to_dict() if len(comparison["new"]) else {}
    resolved_counts = comparison["resolved"]["priority"].value_counts().to_dict() if len(comparison["resolved"]) else {}
    n_new, n_resolved, n_persisting = len(comparison["new"]), len(comparison["resolved"]), len(comparison["persisting"])

    rows = [["", "Nouveaux cas", "Cas résolus"]]
    for priority in ["URGENT", "IMPORTANT", "A_VERIFIER"]:
        rows.append([PRIORITY_LABELS[priority], str(new_counts.get(priority, 0)), str(resolved_counts.get(priority, 0))])
    rows.append(["Total", str(n_new), str(n_resolved)])

    table = Table(rows, colWidths=[3.5 * cm, 4 * cm, 4 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_COLOR),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EEEEEE")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
    ]))
    story.append(table)
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"{n_persisting} cas signalés lors du rapport précédent restent ouverts. "
        "Un « cas résolu » signifie que la donnée a changé (corrigée en amont ou complétée) — "
        "cela ne garantit pas que la correction est juste, seulement que le signalement a disparu.",
        styles["note"],
    ))
    return story


def export_pdf_summary(
    issues: pd.DataFrame,
    comparison: dict[str, pd.DataFrame],
    total_dossiers: int,
    path: str | Path,
    generated_at: datetime | None = None,
    has_history: bool = True,
) -> None:
    """Génère un résumé PDF d'une à deux pages : KPI, synthèse par règle, évolution depuis le
    dernier rapport. Conçu pour être lu, imprimé ou transféré par email sans logiciel spécifique.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    generated_at = generated_at or datetime.now()
    styles = _styles()

    business = issues.loc[~issues["priority"].eq("INFORMATION")].copy()
    summary = build_business_summary(business)
    counts = business.groupby("priority")["issue_id"].nunique().to_dict()
    dossiers_concernes = int(business["stage_id"].nunique())

    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        title="Résumé qualité — données de stages",
    )
    story: list = []
    story += _title_block(styles, generated_at)
    story.append(Spacer(1, 10))
    story.append(_kpi_block(styles, counts, dossiers_concernes, total_dossiers))
    story.append(KeepTogether(_evolution_block(styles, comparison, has_history)))
    story.append(Paragraph("Synthèse par règle", styles["section"]))
    story.append(_summary_table(styles, summary))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Un signalement indique une incohérence ou une information manquante détectée "
        "automatiquement ; il ne constitue pas une correction automatique. Le détail nominatif "
        "complet (nom, email, entreprise) est disponible dans rapport_qualite_metier.xlsx.",
        styles["note"],
    ))
    doc.build(story)
