"""
Tests de la pause d'inactivité (lot « pause d'inactivité », P1) : configuration, bloc HTML/JS,
page statique. Aucun réseau, aucune clé. Chaque test charge une COPIE neuve du module (même
raison que tests/test_demarrage.py : l'ensemble des avertissements déjà émis est par processus).
"""
import importlib.util
import logging
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "src" / "pause.py"
PAGE = ROOT / "static" / "pause.html"

_VARIABLES = ("PAUSE_INACTIVITE_MIN", "PAUSE_ONGLET_MASQUE_MIN", "PAUSE_OCCUPE_MAX_MIN", "PAUSE_ACTIVE")


def _module_neuf():
    spec = importlib.util.spec_from_file_location("pause_copie", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _env_propre(monkeypatch):
    for nom in _VARIABLES:
        monkeypatch.delenv(nom, raising=False)


def _avertissements(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


# ── Durées ──

def test_durees_par_defaut_sans_avertissement(caplog):
    with caplog.at_level(logging.WARNING):
        assert _module_neuf().lire_config() == {"inactivite_min": 6, "masque_min": 3, "occupe_max_min": 20}
    assert _avertissements(caplog) == []


def test_durees_valides_lues(monkeypatch):
    monkeypatch.setenv("PAUSE_INACTIVITE_MIN", "1")
    monkeypatch.setenv("PAUSE_ONGLET_MASQUE_MIN", "60")
    monkeypatch.setenv("PAUSE_OCCUPE_MAX_MIN", "120")
    assert _module_neuf().lire_config() == {"inactivite_min": 1, "masque_min": 60, "occupe_max_min": 120}


@pytest.mark.parametrize("valeur", ["0", "61", "-3", "abc", "2.5", "6 min", "²"])
@pytest.mark.parametrize("nom, defaut", [("PAUSE_INACTIVITE_MIN", 6), ("PAUSE_ONGLET_MASQUE_MIN", 3)])
def test_duree_invalide_valeur_par_defaut_et_avertissement(monkeypatch, caplog, nom, defaut, valeur):
    monkeypatch.setenv(nom, valeur)
    with caplog.at_level(logging.WARNING):
        assert _module_neuf().lire_duree(nom, defaut) == defaut
    messages = _avertissements(caplog)
    assert len(messages) == 1 and nom in messages[0]


@pytest.mark.parametrize("valeur", ["0", "121", "abc"])
def test_plafond_occupation_invalide_valeur_par_defaut_et_avertissement(monkeypatch, caplog, valeur):
    monkeypatch.setenv("PAUSE_OCCUPE_MAX_MIN", valeur)
    with caplog.at_level(logging.WARNING):
        assert _module_neuf().lire_config()["occupe_max_min"] == 20
    messages = _avertissements(caplog)
    assert len(messages) == 1 and "PAUSE_OCCUPE_MAX_MIN" in messages[0]


def test_plafond_occupation_borne_haute_120_et_non_60(monkeypatch):
    monkeypatch.setenv("PAUSE_OCCUPE_MAX_MIN", "90")
    assert _module_neuf().lire_config()["occupe_max_min"] == 90


def test_avertissement_non_repete_a_chaque_rerun(monkeypatch, caplog):
    monkeypatch.setenv("PAUSE_INACTIVITE_MIN", "abc")
    module = _module_neuf()
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            module.lire_config()
    assert len(_avertissements(caplog)) == 1


def test_valeur_vide_valeur_par_defaut_sans_avertissement(monkeypatch, caplog):
    monkeypatch.setenv("PAUSE_INACTIVITE_MIN", "  ")
    with caplog.at_level(logging.WARNING):
        assert _module_neuf().lire_config()["inactivite_min"] == 6
    assert _avertissements(caplog) == []


# ── Interrupteur ──

@pytest.mark.parametrize("valeur, attendu", [
    (None, True), ("true", True), ("TRUE", True), ("1", True),
    ("false", False), ("False", False), ("0", False), ("off", False),
])
def test_pause_active(monkeypatch, valeur, attendu):
    if valeur is not None:
        monkeypatch.setenv("PAUSE_ACTIVE", valeur)
    assert _module_neuf().pause_active() is attendu


def test_pause_active_invalide_reste_active_avec_avertissement(monkeypatch, caplog):
    monkeypatch.setenv("PAUSE_ACTIVE", "peut-etre")
    with caplog.at_level(logging.WARNING):
        assert _module_neuf().pause_active() is True
    assert len(_avertissements(caplog)) == 1


# ── Bloc HTML/JS ──

def _bloc(occupe=False, inactivite=6, masque=3, plafond=20):
    return _module_neuf().bloc_html(occupe, inactivite, masque, plafond)


def test_bloc_etat_occupe_dans_l_attribut():
    assert '<div id="tk-pause" data-busy="1" hidden></div>' in _bloc(occupe=True)
    assert '<div id="tk-pause" data-busy="0" hidden></div>' in _bloc(occupe=False)


def test_bloc_durees_en_millisecondes_dont_le_plafond():
    bloc = _bloc(inactivite=6, masque=3, plafond=20)
    assert "var INACTIVITE_MS = 360000;" in bloc
    assert "var MASQUE_MS = 180000;" in bloc
    assert "var OCCUPE_MAX_MS = 1200000;" in bloc
    assert "setInterval(verifier, 15000);" in bloc


def test_bloc_aucun_jeton_restant_et_cible_statique():
    bloc = _bloc()
    assert not re.search(r"__[A-Z_]+__", bloc)
    assert 'var CIBLE = "/app/static/pause.html";' in bloc
    assert "window.location.replace(CIBLE)" in bloc


def test_bloc_verrou_un_seul_jeu_d_ecouteurs():
    bloc = _bloc()
    assert "if (window.__tkPause) { return; }" in bloc
    assert bloc.index("window.__tkPause = true;") < bloc.index("addEventListener")


def test_bloc_relit_data_busy_dans_le_dom_a_chaque_verification():
    bloc = _bloc()
    # occupe() lit le DOM et verifier() l'appelle : aucune valeur capturée à l'installation.
    occupe = bloc[bloc.index("function occupe()"):bloc.index("function verifier()")]
    assert 'document.getElementById("tk-pause")' in occupe
    assert 'getAttribute("data-busy")' in occupe
    verifier = bloc[bloc.index("function verifier()"):]
    assert "if (occupe())" in verifier
    # Le gabarit n'utilise la valeur rendue qu'à un seul endroit : l'attribut du div.
    assert bloc.count('data-busy="') == 1


def test_bloc_plafond_d_occupation_et_remise_a_zero_apres_calcul():
    verifier = _bloc()[_bloc().index("function verifier()"):]
    assert "maintenant - occupeDepuis < OCCUPE_MAX_MS" in verifier
    assert "occupeDepuis = null;" in verifier
    assert "derniere = maintenant;" in verifier


def test_bloc_evenements_d_activite_et_date_now():
    bloc = _bloc()
    for evenement in ("mousemove", "pointerdown", "keydown", "wheel", "scroll", "touchstart"):
        assert f'"{evenement}"' in bloc
    assert '"visibilitychange"' in bloc
    assert "Date.now()" in bloc
    assert "performance.now" not in bloc


def test_bloc_entiers_forces():
    # Même avec des valeurs inattendues, seul un entier peut entrer dans le JavaScript.
    with pytest.raises((TypeError, ValueError)):
        _module_neuf().bloc_html(False, "6; alert(1)", 3, 20)


# ── Page statique ──

def test_page_de_pause_existe_dans_static():
    assert PAGE.is_file()


def test_page_de_pause_textes_fr_puis_en():
    html = PAGE.read_text(encoding="utf-8")
    fr = [
        "Démo en pause",
        "La démo a été mise en pause après quelques minutes d'inactivité, pour ne pas consommer "
        "de ressources inutilement. La conversation et le document éventuellement envoyé ne sont "
        "pas conservés.",
        "Reprendre la démo",
    ]
    en = [
        "Demo paused",
        "The demo was paused after a few minutes of inactivity, to avoid using resources "
        "needlessly. The conversation and any uploaded document are not kept.",
        "Resume the demo",
    ]
    for texte in fr + en:
        assert texte in html, texte
    corps = html[html.index("<body>"):]  # le <title> contient déjà les deux langues
    assert corps.index("Reprendre la démo") < corps.index("Demo paused")
    assert '<section lang="fr">' in corps and '<section lang="en">' in corps


def test_page_de_pause_autonome_sans_script_ni_url_externe():
    html = PAGE.read_text(encoding="utf-8")
    assert "<script" not in html.lower()
    assert "http:" not in html and "https:" not in html
    assert "//" not in html
    assert "@import" not in html and "url(" not in html
    # Seules références : les liens « Reprendre » vers la racine, et l'icône vide en data:.
    assert re.findall(r'(?:href|src)="([^"]*)"', html) == ["data:,", "/", "/"]
