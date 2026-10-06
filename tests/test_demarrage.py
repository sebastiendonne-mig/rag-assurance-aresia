"""
Tests de l'indicateur de démarrage (sous-lot 2.5, option 1). Aucun réseau, aucune clé.
Chaque test charge une COPIE neuve du module : l'état du vrai module (partagé
avec les tests d'interface) n'est jamais touché.
"""
import ast
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "src" / "demarrage.py"


def _module_neuf():
    spec = importlib.util.spec_from_file_location("demarrage_copie", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pas_pret_au_depart():
    assert _module_neuf().est_pret() is False


def test_pret_apres_marquage_et_idempotent():
    d = _module_neuf()
    d.marquer_pret()
    assert d.est_pret() is True
    d.marquer_pret()
    assert d.est_pret() is True


def test_le_module_n_importe_que_la_bibliotheque_standard():
    """Aucun import tiers : le module est chargé en tête de app.py, avant l'agent."""
    import sys

    arbre = ast.parse(SOURCE.read_text(encoding="utf-8"))
    modules = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            modules.update(a.name.split(".")[0] for a in noeud.names)
        elif isinstance(noeud, ast.ImportFrom) and noeud.module:
            modules.add(noeud.module.split(".")[0])
    assert modules <= set(sys.stdlib_module_names)
