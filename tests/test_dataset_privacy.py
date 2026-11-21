"""Garde-fous RGPD sur ce qui est versionné.

1. Aucun fichier de données réel n'est suivi par git (seuls data/demo/ et les .gitkeep le sont).
2. Le jeu de démo ne contient que des mots de nom tirés des listes fictives.
3. Si l'export réel est présent en local, aucun nom ni email réel ne se retrouve dans la démo.
"""

import subprocess
from pathlib import Path

import pandas as pd
import pytest

from stages_cleaning.paths import DEMO_RAW, REAL_RAW
from stages_cleaning.synthetic import KEPT_WORDS, TOKEN_RE, leaked_values, load_name_pools, norm_token

ROOT = Path(__file__).resolve().parents[1]


def _read(path):
    return pd.read_csv(path, sep=";", dtype="string", encoding="utf-8-sig", keep_default_na=False)


def test_only_demo_data_is_tracked():
    try:
        tracked = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "data", "powerbi"],
            capture_output=True, text=True, check=True,
        ).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("pas de dépôt git")
    allowed = [p for p in tracked if p.startswith("data/demo/") or p.endswith(".gitkeep")]
    assert sorted(set(tracked) - set(allowed)) == []


def test_demo_names_come_from_fake_pools():
    demo = _read(ROOT / DEMO_RAW)
    first, last = load_name_pools()
    pool = {norm_token(w) for w in first + last}
    pieces = pool | set(KEPT_WORDS) | set("abcdefghijklmnopqrstuvwxyz")

    def covered(key: str) -> bool:
        """Mot fictif, ou mot collé / tronqué fait uniquement de morceaux fictifs."""
        if key in pool or key in KEPT_WORDS or len(key) <= 1:
            return True
        reach = {0}
        for i in range(len(key)):
            if i in reach:
                reach.update(i + len(p) for p in pieces if key.startswith(p, i))
                if any(w.startswith(key[i:]) for w in pool if len(key) - i >= 3):
                    return True  # se termine par un début de mot fictif (nom tronqué)
        return len(key) in reach

    unknown = {
        norm_token(t)
        for value in demo["etudiant"]
        for t in TOKEN_RE.findall(value)
        if not covered(norm_token(t))
    }
    assert not unknown, sorted(unknown)[:20]


@pytest.mark.skipif(not (ROOT / REAL_RAW).exists(), reason="export réel absent (normal en CI)")
def test_no_real_identity_in_demo():
    assert leaked_values(_read(ROOT / REAL_RAW), _read(ROOT / DEMO_RAW)) == {"names": 0, "email_locals": 0}
