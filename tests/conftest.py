"""
Garde-fou commun à TOUTE la suite : aucun vrai client google-genai ne peut être
créé pendant les tests.

Pourquoi : ce poste a des Application Default Credentials Google actives. Un
client google-genai en mode Vertex pourrait appeler l'API (payante) sans aucune
clé. Les tests du juge injectent un faux client ; si un test créait le vrai par
erreur, il échouerait ici au lieu d'appeler Google.
"""
import sys
import types

import pytest


class ClientGoogleReelInterdit(RuntimeError):
    pass


def _refus(*args, **kwargs):
    raise ClientGoogleReelInterdit("création d'un vrai client google-genai interdite pendant les tests")


@pytest.fixture(autouse=True)
def interdire_client_google(monkeypatch):
    monkeypatch.delenv("JUDGE_ALLOW_REAL", raising=False)
    try:
        from google import genai  # installé seulement via requirements-eval.txt
    except ImportError:
        genai = None
    if genai is not None and hasattr(genai, "Client"):
        monkeypatch.setattr(genai, "Client", _refus)
        if hasattr(genai, "client"):
            monkeypatch.setattr(genai.client, "Client", _refus, raising=False)
        return
    # SDK absent : un module factice prend sa place, dont le Client refuse aussi.
    factice = types.ModuleType("google.genai")
    factice.Client = _refus
    google = sys.modules.get("google")
    if google is None:
        google = types.ModuleType("google")
        google.__path__ = []
        monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", factice)
    monkeypatch.setattr(google, "genai", factice, raising=False)
