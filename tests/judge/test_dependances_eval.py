"""
Le SDK Google (google-genai) est une dépendance d'ÉVALUATION seulement : il ne
doit jamais entrer dans les dépendances de prod ni dans l'image Docker (temps
de démarrage à froid). Lecture de fichiers seulement.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROD = ("requirements.txt", "pyproject.toml", "uv.lock", "Dockerfile")


def test_google_genai_absent_de_la_prod():
    for nom in PROD:
        texte = (ROOT / nom).read_text(encoding="utf-8").lower()
        assert "google-genai" not in texte and "google_genai" not in texte, nom
        assert "requirements-eval" not in texte, nom


def test_requirements_eval_versions_figees():
    lignes = [
        l.strip() for l in (ROOT / "requirements-eval.txt").read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.lstrip().startswith("#")
    ]
    assert "google-genai==2.25.0" in lignes
    for ligne in lignes:
        assert re.fullmatch(r"[A-Za-z0-9_.-]+==[0-9][0-9A-Za-z.]*", ligne), f"version non figée : {ligne}"


def test_dockerfile_n_installe_que_requirements_txt():
    installs = re.findall(r"pip install[^\n]*", (ROOT / "Dockerfile").read_text(encoding="utf-8"))
    assert installs and all("-r requirements.txt" in l for l in installs)
