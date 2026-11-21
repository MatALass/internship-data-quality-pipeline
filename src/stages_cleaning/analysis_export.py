"""Marquage des lignes à exclure d'un usage analytique (rentrée, chatbot, reporting...).

Décision prise avec Mathieu (voir README, section « Export prêt pour la rentrée ») : certaines
lignes du dataset final sont trop peu fiables pour être exposées telles quelles à un usage aval
(recherche d'un stage, chatbot...), mais ne doivent jamais être supprimées silencieusement du
dataset canonique — c'est le principe suivi depuis le début du projet (cf. AUDIT_FIXES.md).

Ce module ajoute deux colonnes à ``stages_efrei_final.csv`` sans jamais retirer de ligne :
- ``exclu_analyse`` (bool) : True si la ligne ne doit pas être utilisée telle quelle en aval.
- ``motif_exclusion`` (string, NA si non exclue) : un ou plusieurs motifs, séparés par ``|``.

``build_analysis_export.py`` (racine du projet) consomme ces colonnes pour produire un export
filtré séparé, prêt à l'emploi.
"""
from __future__ import annotations

import pandas as pd

# Motifs d'exclusion et la condition qui les déclenche. Décidés le 06/08/2026 :
# - dossier_vide : ni entreprise, ni ville, ni pays renseignés (mêmes lignes que MISSING_COMPANY
#   et MISSING_LOCATION) — aucune donnée exploitable, à défaut de retour du service stages.
# - identite_divergente : deux graphies du nom étudiant trop différentes pour être fusionnées
#   automatiquement (IDENTITY_REAL_DIVERGENCE) — l'identité elle-même n'est pas fiable.
# - entreprise_non_exploitable : nom d'entreprise réduit à une forme juridique seule ou à un
#   libellé générique (COMPANY_QUALITY_SUSPECT), pas un identifiant utilisable de l'employeur.
EXCLUSION_REASONS: dict[str, str] = {
    "dossier_vide": "Aucune entreprise ni localisation renseignée",
    "identite_divergente": "Identité étudiante ambiguë (deux graphies trop différentes)",
    "entreprise_non_exploitable": "Nom d'entreprise non exploitable (forme juridique seule ou libellé générique)",
}


def flag_analysis_exclusions(frame: pd.DataFrame) -> pd.DataFrame:
    """Ajoute ``exclu_analyse`` et ``motif_exclusion`` sans jamais retirer de ligne."""
    df = frame.copy()

    dossier_vide = df["entreprise"].isna() & df["ville"].isna() & df["pays"].isna()
    identite_divergente = df["identity_variant_category"].eq("divergence_reelle")
    entreprise_non_exploitable = df["entreprise_qualite"].isin(["legal_form_only", "generic_label"])

    masks = {
        "dossier_vide": dossier_vide,
        "identite_divergente": identite_divergente,
        "entreprise_non_exploitable": entreprise_non_exploitable,
    }

    motifs = {idx: [] for idx in df.index}
    for label, mask in masks.items():
        for idx in df.index[mask]:
            motifs[idx].append(label)

    df["motif_exclusion"] = pd.Series(
        {idx: ("|".join(m) if m else pd.NA) for idx, m in motifs.items()}, dtype="string"
    ).reindex(df.index)
    df["exclu_analyse"] = df["motif_exclusion"].notna()
    return df


def build_analysis_ready_frame(flagged: pd.DataFrame) -> pd.DataFrame:
    """Retourne la sous-partie du dataset flaggé prête pour un usage analytique en aval."""
    return flagged.loc[~flagged["exclu_analyse"]].drop(columns=["exclu_analyse", "motif_exclusion"]).reset_index(drop=True)
