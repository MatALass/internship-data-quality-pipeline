"""Jeu de démonstration : mêmes défauts de qualité que l'export réel, aucune vraie personne.

Le pipeline doit pouvoir tourner en public sans exposer un seul étudiant. Remplacer les noms
par des identifiants ne suffit pas : l'email contient le nom, et le trio programme + année +
entreprise est unique pour près de 9 lignes sur 10, donc un camarade de promo reconnaît la
personne même sans nom. Ce module produit donc un jeu en trois opérations :

1. **Identités fictives.** Chaque mot d'un nom réel (clé normalisée, sans accents ni casse) est
   remplacé partout par le même mot fictif, tiré des listes de prénoms et noms de Faker. La
   casse, les accents, les séparateurs, les prénoms collés et les emails mal découpés sont
   reproduits : les catégories d'anomalies du notebook 01 restent les mêmes.
2. **Stages mélangés.** Les colonnes du stage (entreprise, adresse, ville, intitulé...) sont
   permutées entre étudiants de même niveau de programme. Le lien étudiant ↔ stage est cassé,
   les statistiques par entreprise et par programme ne bougent pas.
3. **Numéros de rue fictifs.** Une adresse de stage peut être celle de l'étudiant (télétravail) :
   les nombres des adresses sont remplacés, de façon identique pour une même adresse.

Les overrides ciblés par `stage_id` sont recalculés pour suivre le stage déplacé.
Le jeu réel n'est jamais versionné ; seul le résultat de ce module l'est.
"""

from __future__ import annotations

import hashlib
import importlib
import random
import re
import unicodedata
from dataclasses import dataclass, field

import pandas as pd

from stages_cleaning.provenance import build_stage_id

IDENTITY_COLUMNS = ["etudiant", "email"]
STUDENT_COLUMNS = ["programme", "annee_academique"]
STAGE_COLUMNS = [
    "type_stage",
    "entreprise",
    "adresse",
    "code_postal",
    "ville",
    "pays",
    "intitule_poste",
    "libelle_stage",
]
# Particules et mots courts : ils n'identifient personne et leur présence fait partie des
# variantes que le notebook 01 doit savoir traiter.
KEPT_WORDS = frozenset(
    "de du des da di do dos das del della van von der den ter le la el al ben bin bint "
    "abu ibn mc mac st y e".split()
)
FAKER_LOCALES = (
    "fr_FR", "de_DE", "es_ES", "it_IT", "pt_PT", "nl_NL", "en_GB", "pl_PL", "en_US",
    "tr_TR", "sv_SE", "da_DK", "cs_CZ", "ro_RO", "hu_HU", "fi_FI", "no_NO",
)
TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
ACCENTS = {"e": "é", "a": "à", "i": "ï", "o": "ô", "u": "ü", "c": "ç"}


def norm_token(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", text.lower())


def _fold(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()


def load_name_pools() -> tuple[list[str], list[str]]:
    """Prénoms et noms fictifs (ASCII, sans espace ni tiret), dédoublonnés, triés."""
    first: set[str] = set()
    last: set[str] = set()
    for locale in FAKER_LOCALES:
        try:
            provider = importlib.import_module(f"faker.providers.person.{locale}").Provider
        except ModuleNotFoundError:
            continue
        for attr, bucket in (("first_names", first), ("last_names", last)):
            values = getattr(provider, attr, ())
            for value in values.keys() if isinstance(values, dict) else values:
                folded = _fold(str(value))
                if folded.isalpha() and len(folded) >= 3:
                    bucket.add(folded.capitalize())
    return sorted(first), sorted(last)


def apply_case(source: str, fake: str) -> str:
    """Reporte la casse et la présence d'accents du mot source sur le mot fictif."""
    if source.isupper():
        out = fake.upper()
    elif source.islower():
        out = fake.lower()
    elif source[:1].isupper() and source[1:].islower():
        out = fake.capitalize()
    else:  # casse mixte : on recopie le motif lettre à lettre
        pattern = (source * (len(fake) // max(len(source), 1) + 1))[: len(fake)]
        out = "".join(c.upper() if p.isupper() else c.lower() for c, p in zip(fake, pattern))
    if _fold(source) != source:  # le mot source avait un accent : le fictif aussi
        for i, ch in enumerate(out):
            low = ch.lower()
            if low in ACCENTS:
                accented = ACCENTS[low]
                out = out[:i] + (accented.upper() if ch.isupper() else accented) + out[i + 1 :]
                break
    return out


@dataclass
class TokenMapper:
    """Correspondance stable mot réel -> mot fictif, sans collision entre mots fictifs."""

    first_pool: list[str]
    last_pool: list[str]
    rng: random.Random
    mapping: dict[str, str] = field(default_factory=dict)
    _used: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.rng.shuffle(self.first_pool)
        self.rng.shuffle(self.last_pool)

    def fake_for(self, key: str, role: str) -> str:
        if key in self.mapping:
            return self.mapping[key]
        pool = self.first_pool if role == "first" else self.last_pool
        fake = None
        while pool:
            candidate = pool.pop()
            ckey = norm_token(candidate)
            if ckey not in self._used and ckey not in self.mapping:
                fake = candidate
                break
        if fake is None:  # listes épuisées : mot inventé, prononçable
            fake = self._invent()
        self._used.add(norm_token(fake))
        self.mapping[key] = fake
        return fake

    def _invent(self) -> str:
        syllables = ["ba", "lo", "mi", "ra", "ten", "vor", "li", "dan", "sel", "mo", "ru", "ka"]
        while True:
            word = "".join(self.rng.choice(syllables) for _ in range(3)).capitalize()
            if norm_token(word) not in self._used:
                return word


def _split_name(value: str) -> tuple[str, str]:
    if "," in value:
        nom, prenoms = value.split(",", 1)
        return nom, prenoms
    return value, ""


def _roles(identities: pd.Series) -> dict[str, str]:
    """Rôle majoritaire de chaque mot : nom (avant la virgule) ou prénom (après)."""
    votes: dict[str, list[int]] = {}
    for value in identities.dropna().astype(str):
        nom, prenoms = _split_name(value)
        for part, idx in ((nom, 0), (prenoms, 1)):
            for token in TOKEN_RE.findall(part):
                key = norm_token(token)
                if key:
                    votes.setdefault(key, [0, 0])[idx] += 1
    return {k: ("last" if v[0] >= v[1] else "first") for k, v in votes.items()}


def _is_kept(key: str) -> bool:
    return key in KEPT_WORDS


EMAIL_SPLIT_RE = re.compile(r"([._\-]|\d+)")


def _email_chunks(email: str) -> list[str]:
    local = email.split("@", 1)[0] if "@" in email else ""
    return [p for p in EMAIL_SPLIT_RE.split(local) if p and not p.isdigit() and p not in "._-"]


def _segment(key: str, parts: list[str]) -> list[str] | None:
    """Découpe une clé en une suite d'autres clés du contexte (prénoms collés, noms composés)."""
    best: dict[int, list[str]] = {0: []}
    for i in range(len(key)):
        if i not in best:
            continue
        for part in parts:
            if part != key and part and key.startswith(part, i):
                j = i + len(part)
                if j not in best or len(best[j]) > len(best[i]) + 1:
                    best[j] = best[i] + [part]
    found = best.get(len(key))
    return found if found and len(found) >= 2 else None


class IdentityFaker:
    """Remplace les mots d'identité en gardant les relations entre nom affiché et email.

    Le contexte d'un mot est l'ensemble des mots (nom affiché + email) des lignes qui partagent
    le même email : c'est là que le notebook 01 compare les variantes. Un mot collé
    (« JEANPIERRE ») devient la concaténation des mots fictifs de « jean » et « pierre », une
    initiale devient l'initiale du mot fictif correspondant, un nom tronqué reste tronqué.
    """

    def __init__(self, mapper: TokenMapper, roles: dict[str, str]) -> None:
        self.mapper = mapper
        self.roles = roles
        self.ident_words: list[str] = []  # mots du nom affiché du groupe en cours

    def _fake(self, key: str) -> str:
        return norm_token(self.mapper.fake_for(key, self.roles.get(key, "last")))

    def _part(self, key: str) -> str:
        return key if _is_kept(key) or len(key) == 1 else self._fake(key)

    def resolve(self, key: str, context: list[str], *, in_email: bool = False) -> str | None:
        """Clé fictive normalisée, ou None pour garder le mot tel quel."""
        if not key or _is_kept(key):
            return None
        if len(key) == 1:
            if not in_email or key in context:  # lettre isolée aussi dans le nom affiché
                return None
            # initiale ou lettre d'un mot du nom : même position dans le mot fictif
            for full in self.ident_words or context:
                if len(full) >= 2 and not _is_kept(full) and key in full:
                    fake = self.rendered(full, context)
                    return fake[min(full.index(key), len(fake) - 1)]
            return None
        # morceaux autorisés : mots du contexte, particules, lettres isolées du contexte
        parts_pool = [c for c in context if c != key]
        parts = _segment(key, parts_pool)
        if parts and any(len(p) >= 2 and not _is_kept(p) for p in parts):
            return "".join(self._part(p) for p in parts)
        longer = [c for c in context if len(c) >= 2 and not _is_kept(c) and c != key]
        if key in self.mapper.mapping:
            return self._fake(key)
        if 2 <= len(key) <= 4:  # initiales du nom (règle acceptée par check_identity)
            for size in range(len(key), 1, -1):
                for i in range(len(longer) - size + 1):
                    seq = longer[i : i + size]
                    if "".join(c[0] for c in seq) == key:
                        return "".join(self._fake(c)[0] for c in seq)
        if len(key) >= 3:
            for full in sorted(longer, key=len):
                if full.startswith(key) and full in self.roles:
                    fake = self._fake(full)
                    return fake[: len(key)] if len(fake) >= len(key) else fake
        return self._fake(key)

    def rendered(self, word: str, context: list[str]) -> str:
        """Forme fictive normalisée d'un mot du nom affiché (telle qu'écrite dans la colonne)."""
        fake = self.resolve(word, context)
        return word if fake is None else fake

    def resolve_email(self, key: str, context: list[str]) -> str | None:
        """Un morceau d'email suit le nom affiché du même étudiant, tel qu'il a été réécrit."""
        if not key or _is_kept(key) or len(key) == 1:
            return self.resolve(key, context, in_email=True)
        parts = _segment(key, [c for c in context if c != key])
        if parts and any(len(p) >= 2 and not _is_kept(p) for p in parts):
            return "".join(self._part(p) for p in parts)
        if key in self.ident_words:
            return self.rendered(key, context)
        for full in self.ident_words:  # morceau d'un mot collé du nom affiché
            sub = _segment(full, [c for c in context if c != full])
            if sub and key in sub:
                return self._fake(key)
        if len(key) >= 3:
            for full in self.ident_words:  # morceau contenu dans un mot du nom affiché
                pos = full.find(key)
                if pos >= 0 and len(full) > len(key) and not _is_kept(full):
                    fake = self.rendered(full, context)
                    if len(fake) >= pos + len(key):
                        return fake[pos : pos + len(key)]
                    return fake
        return self.resolve(key, context, in_email=True)

    def _render(self, token: str, context: list[str], *, in_email: bool = False) -> str:
        key = norm_token(token)
        fake = self.resolve_email(key, context) if in_email else self.resolve(key, context)
        return token if fake is None else apply_case(token, fake)

    def identity(self, value: str, context: list[str]) -> str:
        return TOKEN_RE.sub(lambda m: self._render(m.group(0), context), value)

    def email(self, email: str, context: list[str], rng: random.Random) -> str:
        if "@" not in email:
            return email
        local, domain = email.split("@", 1)
        out = []
        for piece in EMAIL_SPLIT_RE.split(local):
            if not piece:
                continue
            if piece.isdigit():
                out.append("".join(str(rng.randint(0, 9)) for _ in piece))
            elif piece in "._-":
                out.append(piece)
            else:
                out.append(self._render(piece, context, in_email=True).lower())
        return "".join(out) + "@" + domain


def fake_identity(value: str, mapper: TokenMapper, roles: dict[str, str]) -> str:
    """Version sans contexte (overrides d'identité) : mot à mot."""
    faker = IdentityFaker(mapper, roles)
    return faker.identity(value, [norm_token(t) for t in TOKEN_RE.findall(value)])


def fake_address(value: str, seed: int) -> str:
    if not value:
        return value
    rng = random.Random(int(hashlib.sha256(f"{seed}:{value}".encode()).hexdigest()[:12], 16))

    def repl(match: re.Match[str]) -> str:
        digits = match.group(0)
        low = 10 ** (len(digits) - 1) if len(digits) > 1 else 1
        high = 10 ** len(digits) - 1
        new = rng.randint(low, high)
        if str(new) == digits:  # jamais le numéro d'origine
            new = low if new == high else new + 1
        return str(new)

    return re.sub(r"\d+", repl, value)


def programme_level(value: str) -> str:
    """Niveau comparable pour mélanger les stages sans créer d'incohérences grossières."""
    text = str(value)
    match = re.match(r"\s*(Prépa|Ingénieur|Ingé|Bachelor|BTS|M1|M2|MSc|PEx)\s*(\d)?", text, re.I)
    if not match:
        return "autre"
    return f"{match.group(1).lower()} {match.group(2) or ''}".strip()


def _derangement(members: list[int], rng: random.Random) -> dict[int, int]:
    """Chaque unité reçoit le stage d'une autre (jamais le sien), si au moins deux unités."""
    order = members[:]
    rng.shuffle(order)
    if len(order) < 2:
        return {m: m for m in order}
    return {order[i]: order[(i + 1) % len(order)] for i in range(len(order))}


@dataclass
class SyntheticResult:
    frame: pd.DataFrame
    stage_id_map: dict[str, list[str]]
    token_map: dict[str, str]


def make_synthetic(raw: pd.DataFrame, seed: int = 42) -> SyntheticResult:
    """Construit le jeu de démonstration à partir de l'export réel (colonnes brutes)."""
    missing = set(IDENTITY_COLUMNS + STUDENT_COLUMNS + STAGE_COLUMNS) - set(raw.columns)
    if missing:
        raise ValueError(f"Colonnes absentes de l'export : {sorted(missing)}")
    rng = random.Random(seed)
    first_pool, last_pool = load_name_pools()
    mapper = TokenMapper(first_pool, last_pool, rng)
    src = raw.fillna("").astype(str).reset_index(drop=True)
    roles = _roles(src["etudiant"])

    # 1. identités : contexte = tous les mots (nom affiché + email) des lignes du même email
    out = src.copy()
    group_key = src["email"].str.lower().where(src["email"].ne(""), src["etudiant"])
    contexts: dict[str, list[str]] = {}
    ident_words: dict[str, list[str]] = {}
    for key, ident, email in zip(group_key, src["etudiant"], src["email"]):
        iw = ident_words.setdefault(key, [])
        iw.extend(w for w in (norm_token(t) for t in TOKEN_RE.findall(ident)) if w and w not in iw)
        words = [norm_token(t) for t in TOKEN_RE.findall(ident)] + [
            norm_token(c) for c in _email_chunks(email) if len(norm_token(c)) >= 2
        ]
        bucket = contexts.setdefault(key, [])
        bucket.extend(w for w in words if w and w not in bucket)
    # mots atomiques d'abord, dans un ordre stable : les mots collés se composent ensuite
    for ctx in contexts.values():
        for word in ctx:
            if len(word) >= 2 and not _is_kept(word) and not _segment(word, [c for c in ctx if c != word]):
                mapper.fake_for(word, roles.get(word, "last"))
    faker = IdentityFaker(mapper, roles)
    names = []
    for value, key in zip(src["etudiant"], group_key):
        faker.ident_words = ident_words[key]
        names.append(faker.identity(value, contexts[key]))
    out["etudiant"] = names
    email_rng = random.Random(seed + 1)
    emails = []
    for email, key in zip(src["email"], group_key):
        faker.ident_words = ident_words[key]
        emails.append(faker.email(email, contexts[key], email_rng))
    out["email"] = emails

    # 2. stages : une unité = un étudiant (email) et un stage ; même taille et même niveau
    unit = src.groupby(
        [src["email"].str.lower()] + [src[c] for c in STAGE_COLUMNS], sort=False
    ).ngroup()
    units = pd.DataFrame({"unit": unit, "level": src["programme"].map(programme_level)})
    unit_rows = units.groupby("unit").groups
    unit_info = (
        units.groupby("unit").agg(level=("level", "first"), size=("level", "size")).reset_index()
    )
    receiving_to_source: dict[int, int] = {}
    strata = unit_info.groupby(["level", "size"])["unit"].apply(list)
    leftovers: dict[int, list[int]] = {}
    for (_, size), members in strata.items():
        if len(members) < 3:  # trop peu pour mélanger sans révéler : on regroupe par taille
            leftovers.setdefault(size, []).extend(members)
            continue
        receiving_to_source.update(_derangement(members, rng))
    for members in leftovers.values():
        receiving_to_source.update(_derangement(members, rng))

    for receiving, source in receiving_to_source.items():
        dst = list(unit_rows[receiving])
        src_rows = list(unit_rows[source])
        out.loc[dst, STAGE_COLUMNS] = src.loc[src_rows, STAGE_COLUMNS].to_numpy()
    out["adresse"] = [fake_address(v, seed) for v in out["adresse"]]

    # 3. overrides : le stage source -> les lignes qui le reçoivent
    real_ids = build_stage_id(raw.reset_index(drop=True))
    out_typed = out.replace("", pd.NA)
    new_ids = build_stage_id(out_typed[list(raw.columns)])
    stage_id_map: dict[str, list[str]] = {}
    for receiving, source in receiving_to_source.items():
        for s_row, d_row in zip(list(unit_rows[source]), list(unit_rows[receiving])):
            stage_id_map.setdefault(str(real_ids.iloc[s_row]), []).append(str(new_ids.iloc[d_row]))
    return SyntheticResult(out_typed[list(raw.columns)], stage_id_map, dict(mapper.mapping))


def remap_stage_overrides(overrides: pd.DataFrame, stage_id_map: dict[str, list[str]]) -> pd.DataFrame:
    """Recopie chaque override sur les lignes qui ont reçu le stage corrigé."""
    rows = []
    for _, row in overrides.iterrows():
        for new_id in sorted(set(stage_id_map.get(str(row["stage_id"]), []))):
            rows.append({**row.to_dict(), "stage_id": new_id})
    return pd.DataFrame(rows, columns=overrides.columns).drop_duplicates()


def remap_identity_overrides(overrides: pd.DataFrame, result: SyntheticResult) -> pd.DataFrame:
    """Overrides d'identité (clé = chaîne d'identité) traduits avec les mêmes mots fictifs."""
    roles: dict[str, str] = {}
    mapper = TokenMapper([], [], random.Random(0))
    mapper.mapping = dict(result.token_map)
    out = overrides.copy()
    for col in ("source_identity", "corrected_identity"):
        out[col] = [fake_identity(str(v), mapper, roles) if pd.notna(v) else v for v in out[col]]
    return out


def leaked_values(real: pd.DataFrame, fake: pd.DataFrame) -> dict[str, int]:
    """Nombre de noms complets et de parties locales d'email réels retrouvés dans le jeu fictif."""
    real_names = {norm_token(v) for v in real["etudiant"].dropna() if norm_token(v)}
    real_locals = {str(v).split("@")[0].lower() for v in real["email"].dropna() if "@" in str(v)}
    fake_names = {norm_token(v) for v in fake["etudiant"].dropna()}
    fake_locals = {str(v).split("@")[0].lower() for v in fake["email"].dropna() if "@" in str(v)}
    return {"names": len(real_names & fake_names), "email_locals": len(real_locals & fake_locals)}
