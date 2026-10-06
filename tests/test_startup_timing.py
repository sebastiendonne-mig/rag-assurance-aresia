"""
Tests des repères de démarrage (sous-lot 2.5). Aucun réseau, aucune clé.
Chaque test charge une COPIE neuve du module : son état (horloge, étapes déjà
émises) ne fuit ni vers les autres tests ni depuis l'import réel d'agent/app.
"""
import ast
import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

LIGNE = re.compile(r"^startup-timing (?P<etape>.+?) \+(?P<t>\d+\.\d{3})s( \(age_processus=(\d+\.\d{3}s|n/a)\))?$")


def _module_neuf():
    spec = importlib.util.spec_from_file_location("startup_timing_copie", ROOT / "src" / "startup_timing.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_format_prefixe_etape_et_temps(capsys):
    st = _module_neuf()
    st.mark("étape A")
    st.mark("étape B")
    lignes = capsys.readouterr().out.splitlines()
    assert len(lignes) == 2
    premiere, seconde = (LIGNE.match(l) for l in lignes)
    assert premiere and seconde
    assert premiere["etape"] == "étape A" and seconde["etape"] == "étape B"
    assert float(seconde["t"]) >= float(premiere["t"]) >= 0
    # L'âge du processus n'est ajouté qu'à la première ligne.
    assert "age_processus" in lignes[0]
    assert "age_processus" not in lignes[1]


def test_une_seule_emission_par_etape(capsys):
    st = _module_neuf()
    for _ in range(5):
        st.mark("démarrage")
    assert len(capsys.readouterr().out.splitlines()) == 1


def test_ne_leve_jamais(monkeypatch, capsys):
    st = _module_neuf()

    def _boom(*a, **k):
        raise RuntimeError("stdout cassé")

    monkeypatch.setattr("builtins.print", _boom)
    st.mark("étape")  # ne doit pas lever


def test_age_processus_indisponible_sans_psutil(monkeypatch, capsys):
    st = _module_neuf()
    monkeypatch.setitem(sys.modules, "psutil", None)  # import psutil -> ImportError
    st.mark("sans psutil")
    assert "(age_processus=n/a)" in capsys.readouterr().out


def test_le_module_n_importe_que_la_bibliotheque_standard():
    arbre = ast.parse((ROOT / "src" / "startup_timing.py").read_text(encoding="utf-8"))
    modules = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            modules.update(a.name.split(".")[0] for a in noeud.names)
        elif isinstance(noeud, ast.ImportFrom) and noeud.module:
            modules.add(noeud.module.split(".")[0])
    assert modules <= {"threading", "time", "os", "psutil"}  # psutil : import local, protégé par try/except


# 12 repères depuis l'option 1 du sous-lot 2.5 (ajout de « page : coquille émise »), soit
# exactement l'ancienne limite. Relevée à 14 pour laisser une petite marge, tout en gardant
# une instrumentation courte : au-delà, se demander si chaque repère sert encore une mesure.
MAX_REPERES = 14


def test_etapes_instrumentees_dans_app_et_agent():
    """Les repères demandés existent, et leur nombre reste borné (MAX_REPERES)."""
    etapes = []
    for fichier in ("app.py", "src/agent.py"):
        arbre = ast.parse((ROOT / fichier).read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            if (
                isinstance(noeud, ast.Call)
                and isinstance(noeud.func, ast.Attribute)
                and noeud.func.attr == "mark"
                and isinstance(noeud.func.value, ast.Name)
                and noeud.func.value.id == "startup_timing"
            ):
                etapes.append(noeud.args[0].value)
    assert len(etapes) == len(set(etapes)) <= MAX_REPERES
    for attendu in (
        "app.py début",
        "import streamlit",
        "page : coquille émise",
        "import agent (module complet)",
        "agent : import anthropic",
        "agent : import chromadb",
        "agent : import langgraph",
        "warm-up : get_chroma_col",
        "warm-up : get_anthropic",
        "warm-up : get_graph",
        "warm-up terminé",
    ):
        assert attendu in etapes


def test_app_py_importe_startup_timing_avant_toute_bibliotheque_tierce():
    arbre = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    ordre = []
    for noeud in arbre.body:
        if isinstance(noeud, ast.Import):
            ordre += [a.name.split(".")[0] for a in noeud.names]
        elif isinstance(noeud, ast.ImportFrom) and noeud.module:
            ordre.append(noeud.module.split(".")[0])
    assert ordre.index("startup_timing") < ordre.index("streamlit")
    assert set(ordre[: ordre.index("startup_timing")]) <= {"sys", "pathlib"}
