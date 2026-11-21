"""Exécute l'intégralité du pipeline de nettoyage, dans l'ordre, notebook par notebook.

Usage (PowerShell ou bash) :

    python run_pipeline.py
    python run_pipeline.py --only 01_identity_cleaning 02_country_cleaning
    python run_pipeline.py --stop-on-error false
    python run_pipeline.py --dataset demo --offline   # jeu fictif versionné, sans réseau (CI)

Chaque notebook est exécuté avec son répertoire de travail réglé sur `notebooks/`, exactement
comme s'il était lancé depuis Jupyter, puis réécrit sur place (code + nouvelles sorties), afin que
`git diff` montre exactement ce que la dernière exécution a produit. Le script s'arrête à la
première erreur par défaut, pour ne jamais enchaîner une étape sur une entrée invalide.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

ROOT = Path(__file__).resolve().parent
NOTEBOOKS_DIR = ROOT / "notebooks"
KERNEL_NAME = "python3"

PIPELINE_ORDER = [
    "00_profiling_raw",
    "01_identity_cleaning",
    "02_country_cleaning",
    "03_postal_code_cleaning",
    "04_programme_enrichment",
    "05_normalisation_entreprises",
    "06_data_quality_report",
    "99_validation",
]


def ensure_kernel_registered(kernel_name: str = KERNEL_NAME) -> None:
    """(Ré)installe le kernel Jupyter `kernel_name` pour l'interpréteur courant (`sys.executable`).

    `pip install jupyter ipykernel` (voir requirements.txt) n'enregistre PAS forcément un
    kernelspec valide pour CET interpréteur précis : un kernelspec `python3` générique peut déjà
    exister ailleurs sur la machine (autre install Python, autre venv) et pointer vers une
    commande introuvable une fois lancée — cause typique de `[WinError 2] Le fichier spécifié
    est introuvable` sous Windows quand le kernelspec référence juste `python` sans chemin
    absolu et que `python` n'est pas sur le PATH utilisé par Jupyter.

    On réinstalle donc systématiquement (opération rapide et idempotente) plutôt que de se fier
    à un kernelspec déjà présent, pour que `python run_pipeline.py` marche du premier coup sur
    n'importe quelle machine.
    """
    import ipykernel.kernelspec

    ipykernel.kernelspec.install(user=True, kernel_name=kernel_name, display_name=f"Python 3 ({kernel_name})")


def strip_outputs(nb) -> None:
    """Retire les sorties de cellules avant réécriture (AUDIT_FIXES.md R-1).

    Les notebooks sont versionnés ; leurs sorties peuvent contenir des données nominatives
    (noms, emails d'étudiants) affichées via `display`/`print` pendant l'exécution. On les
    retire par défaut avant d'écrire le notebook sur disque, pour ne jamais faire fuiter ces
    données dans l'historique git.
    """
    for cell in nb.cells:
        if cell.get("cell_type") == "code":
            cell["outputs"] = []
            cell["execution_count"] = None
            # horodatages d'exécution : du bruit dans chaque diff git
            cell.get("metadata", {}).pop("execution", None)


def run_notebook(name: str, timeout: int = 1800, keep_outputs: bool = False) -> float:
    path = NOTEBOOKS_DIR / f"{name}.ipynb"
    if not path.exists():
        raise FileNotFoundError(f"Notebook introuvable : {path}")

    notebook = nbformat.read(path, as_version=4)
    client = NotebookClient(
        notebook,
        timeout=timeout,
        kernel_name=KERNEL_NAME,
        resources={"metadata": {"path": str(NOTEBOOKS_DIR)}},
    )
    started = time.monotonic()
    client.execute()
    elapsed = time.monotonic() - started
    if not keep_outputs:
        strip_outputs(notebook)
    nbformat.write(notebook, path)
    return elapsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="*", default=None, help="Sous-ensemble de notebooks à exécuter (noms sans .ipynb), dans l'ordre du pipeline.")
    parser.add_argument("--stop-on-error", type=lambda v: v.lower() != "false", default=True, help="Arrêter au premier échec (défaut : true).")
    parser.add_argument("--keep-outputs", action="store_true", help="Conserver les sorties des cellules dans les notebooks réécrits (débogage local uniquement ; ne jamais committer). Défaut : les sorties sont retirées avant écriture.")
    parser.add_argument("--dataset", choices=["auto", "real", "demo"], default=None, help="Jeu d'entrée : export réel local, démo versionnée, ou auto (réel s'il est présent). Défaut : variable STAGES_DATASET, sinon auto.")
    parser.add_argument("--offline", action="store_true", help="Désactive le géocodage réseau (STAGES_RUN_NETWORK=0) : seuls les caches sont utilisés.")
    args = parser.parse_args()

    # Les kernels des notebooks héritent de l'environnement du processus courant.
    if args.dataset:
        os.environ["STAGES_DATASET"] = args.dataset
    if args.offline:
        os.environ["STAGES_RUN_NETWORK"] = "0"

    unknown = [name for name in args.only if name not in PIPELINE_ORDER] if args.only else []
    if unknown:
        raise SystemExit(f"Notebooks inconnus dans --only : {unknown}. Attendus : {PIPELINE_ORDER}")

    selected = [n for n in PIPELINE_ORDER if args.only is None or n in args.only]
    if not selected:
        print("Aucun notebook sélectionné.", file=sys.stderr)
        return 1

    ensure_kernel_registered()

    print("Pipeline :", " → ".join(selected))
    failures: list[str] = []
    for name in selected:
        print(f"\n=== {name} ===")
        try:
            elapsed = run_notebook(name, keep_outputs=args.keep_outputs)
            print(f"✔ {name} exécuté en {elapsed:.1f}s")
        except CellExecutionError as exc:
            print(f"✘ {name} a échoué : {exc}", file=sys.stderr)
            failures.append(name)
            if args.stop_on_error:
                break
        except Exception as exc:  # noqa: BLE001 - on veut un rapport clair, pas une trace brute
            print(f"✘ {name} a échoué de manière inattendue : {exc}", file=sys.stderr)
            failures.append(name)
            if args.stop_on_error:
                break

    print("\n" + "=" * 60)
    if failures:
        print(f"Échec(s) : {', '.join(failures)}")
        return 1
    print(f"Pipeline complet exécuté avec succès ({len(selected)} notebook(s)).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
