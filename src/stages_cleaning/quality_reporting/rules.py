from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuleDefinition:
    rule_id: str
    priority: str
    priority_order: int
    category: str
    title: str
    action: str
    audience: str = "business"
    # "detail"    : chaque cas est listé ligne par ligne dans le rapport métier.
    # "aggregate" : trop volumineux pour être lisible ligne par ligne (ex. des centaines de
    #               pays non déterminés) ; affiché sous forme de compteurs par promotion/type de
    #               stage, le détail nominatif restant disponible dans le rapport technique.
    display_mode: str = "detail"


RULES: dict[str, RuleDefinition] = {
    "DUPLICATE_EXACT_STAGE": RuleDefinition("DUPLICATE_EXACT_STAGE", "URGENT", 1, "Doublons", "Stage présent plusieurs fois", "Vérifier qu'il s'agit bien d'un doublon puis conserver un seul enregistrement."),
    "MISSING_COMPANY": RuleDefinition("MISSING_COMPANY", "URGENT", 1, "Dossier incomplet", "Entreprise non renseignée", "Identifier l'entreprise d'accueil et compléter le dossier étudiant."),
    "COMPANY_QUALITY_SUSPECT": RuleDefinition(
        "COMPANY_QUALITY_SUSPECT", "A_VERIFIER", 3, "Entreprise",
        "Nom d'entreprise non exploitable (forme juridique seule ou libellé générique)",
        "Récupérer le nom réel de l'entreprise auprès de la source ou confirmer l'absence.",
    ),
    "MISSING_LOCATION": RuleDefinition("MISSING_LOCATION", "IMPORTANT", 2, "Dossier incomplet", "Localisation du stage absente", "Compléter au minimum la ville et le pays du lieu de stage réel."),
    "SWIM_IN_FRANCE": RuleDefinition("SWIM_IN_FRANCE", "IMPORTANT", 2, "Mobilité internationale", "SWIM enregistré avec une localisation en France", "Vérifier le type de stage et le pays réellement associé au lieu de mission."),
    "SWIM_COUNTRY_UNKNOWN": RuleDefinition("SWIM_COUNTRY_UNKNOWN", "IMPORTANT", 2, "Mobilité internationale", "SWIM sans pays exploitable", "Compléter ou corriger le pays avant validation du dossier."),
    "PROGRAMME_UNRECOGNIZED": RuleDefinition("PROGRAMME_UNRECOGNIZED", "IMPORTANT", 2, "Programme", "Programme non reconnu par le pipeline", "Vérifier le libellé du programme et compléter le mapping métier si le libellé est valide."),
    "MAJOR_UNKNOWN": RuleDefinition(
        "MAJOR_UNKNOWN", "IMPORTANT", 2, "Programme",
        "Majeure absente du référentiel officiel (ni connue, ni conservée, ni en attente)",
        "Ajouter le libellé à MAJOR_CANONICAL, MAJOR_KEEP_AS_IS ou MAJOR_PENDING_REVIEW dans programme.py après vérification.",
    ),
    "MAJOR_PENDING_REVIEW": RuleDefinition(
        "MAJOR_PENDING_REVIEW", "A_VERIFIER", 3, "Programme",
        "Majeure sans nom officiel confirmé (rattachement volontairement en attente)",
        "Décider du nom officiel définitif ou confirmer qu'aucune correspondance n'existe, puis mettre à jour MAJOR_CANONICAL.",
        display_mode="aggregate",
    ),
    "COUNTRY_UNRESOLVED": RuleDefinition("COUNTRY_UNRESOLVED", "A_VERIFIER", 3, "Localisation", "Pays non déterminé", "Compléter le pays lorsque l'information est disponible dans le dossier ou la convention.", display_mode="aggregate"),
    "POSTAL_UNRESOLVED": RuleDefinition("POSTAL_UNRESOLVED", "A_VERIFIER", 3, "Localisation", "Code postal non résolu", "Vérifier le code postal si cette information est nécessaire au suivi du dossier.", display_mode="aggregate"),
    "POSTAL_SUSPICIOUS_SOURCE": RuleDefinition("POSTAL_SUSPICIOUS_SOURCE", "A_VERIFIER", 3, "Localisation", "Valeur de code postal suspecte dans la source", "Remplacer la valeur source par le code postal réel ou laisser la donnée vide si elle est inconnue."),
    "IDENTITY_REAL_DIVERGENCE": RuleDefinition("IDENTITY_REAL_DIVERGENCE", "A_VERIFIER", 3, "Identité", "Identités réellement divergentes pour un même email", "Vérifier l'identité officielle. Ne pas corriger automatiquement sans source de référence."),
    "COUNTRY_LOW_CONFIDENCE": RuleDefinition("COUNTRY_LOW_CONFIDENCE", "INFORMATION", 4, "Traçabilité technique", "Pays inféré avec une confiance faible", "Aucune action immédiate ; conserver le cas visible pour audit si nécessaire.", "technical"),
    "POSTAL_PATTERN_UNSUPPORTED": RuleDefinition("POSTAL_PATTERN_UNSUPPORTED", "INFORMATION", 4, "Couverture technique", "Format postal non couvert par les règles de validation", "Étendre les règles uniquement si le volume ou le besoin métier le justifie.", "technical"),
    "COMPANY_MERGE_DECISIONS_PENDING": RuleDefinition(
        "COMPANY_MERGE_DECISIONS_PENDING", "INFORMATION", 4, "Traçabilité technique",
        "Paires candidates de fusion entreprise sans décision",
        "Renseigner la colonne decision (merge/distinct/review) dans company_merge_decisions.csv.",
        "technical",
    ),
}
