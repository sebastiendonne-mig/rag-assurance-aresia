"""
Tests des données du juge LLM (lot B) : copies piégées, contrats reconstitués,
fiche d'annotation humaine. Lecture de fichiers seulement : aucun réseau,
aucun import d'agent, aucun appel API.
"""
import json
import re
from collections import Counter
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
RUN = json.loads((HERE.parent / "results" / "upload_eval_20260925_104952.json").read_text(encoding="utf-8"))
PIEGES = json.loads((HERE / "pieges.json").read_text(encoding="utf-8"))["pieges"]
FICHE = (HERE / "annotation_humaine.md").read_text(encoding="utf-8")

TYPES = {
    "chiffre_modifie": "C1",
    "garantie_inventee": "C1",
    "condition_supprimee": "C1",
    "citation_deplacee": "C2",
    "refus_casse": "C3",
}
MOTEURS = ("anthropic", "mistral")
DOCS = ("CG-PREV-INV-2024", "CG-AV-MULTI-2024", "BAR-IARD-2024-V2", "ACPR-REC-2024-12")
VERDICTS = {"oui", "non", "sans objet", "inchangé"}
CHAMPS = (
    "id", "type", "critere_vise", "moteur", "question_id", "question", "doc", "difficulte",
    "difficulte_justification", "reponse_origine", "reponse_piegee", "modification",
    "preuve_contrat", "verdict_attendu",
)
NON_TROUVE = "Je ne trouve pas cette information"


def normaliser(texte: str) -> str:
    return re.sub(r"\s+", " ", texte).strip()


def reponse_du_run(question_id: str, moteur: str) -> str:
    for r in RUN["resultats"]:
        if r["label"].split()[0] == question_id:
            return r["moteurs"][moteur]["reponse"]
    raise KeyError(question_id)


def contrat(doc: str) -> dict:
    return json.loads((HERE / "contrats" / f"{doc}.json").read_text(encoding="utf-8"))


# ─────────────────────────────────────────────
# Copies piégées
# ─────────────────────────────────────────────


def test_dix_pieges_cinq_types_deux_moteurs():
    assert len(PIEGES) == 10
    assert len({p["id"] for p in PIEGES}) == 10
    assert Counter((p["type"], p["moteur"]) for p in PIEGES) == {(t, m): 1 for t in TYPES for m in MOTEURS}


@pytest.mark.parametrize("piege", PIEGES, ids=lambda p: p["id"])
def test_champs_presents_et_coherents(piege):
    for champ in CHAMPS:
        assert piege.get(champ), f"champ vide ou absent : {champ}"
    assert piege["critere_vise"] == TYPES[piege["type"]]
    assert piege["doc"] in DOCS
    assert piege["difficulte"] in ("facile", "subtil")
    assert piege["modification"]["description"]
    verdicts = piege["verdict_attendu"]
    assert set(verdicts) == {"C1", "C2", "C3"}
    assert set(verdicts.values()) <= VERDICTS
    assert verdicts[piege["critere_vise"]] == "non"


@pytest.mark.parametrize("piege", PIEGES, ids=lambda p: p["id"])
def test_reponse_origine_est_la_reponse_du_25_09(piege):
    assert piege["reponse_origine"] == reponse_du_run(piege["question_id"], piege["moteur"])


@pytest.mark.parametrize("piege", PIEGES, ids=lambda p: p["id"])
def test_remplacements_redonnent_exactement_la_copie_piegee(piege):
    """Une seule information modifiée : les remplacements, appliqués dans l'ordre,
    transforment la réponse d'origine en copie piégée, sans rien d'autre."""
    remplacements = piege["modification"]["remplacements"]
    assert remplacements
    texte = piege["reponse_origine"]
    for r in remplacements:
        assert r["avant"] != r["apres"]
        assert texte.count(r["avant"]) == r["occurrences"] >= 1
        texte = texte.replace(r["avant"], r["apres"])
    assert texte == piege["reponse_piegee"]
    entiere = [r for r in remplacements if r["avant"] == piege["reponse_origine"]]
    if piege["type"] == "refus_casse":
        assert len(remplacements) == 1 and entiere, "refus cassé : un seul remplacement de la réponse entière"
    else:
        assert not entiere, "seul le refus cassé peut réécrire la réponse entière"


@pytest.mark.parametrize("piege", PIEGES, ids=lambda p: p["id"])
def test_preuve_presente_dans_le_contrat(piege):
    preuve = piege["preuve_contrat"]
    extraits = contrat(piege["doc"])["extraits"]
    textes = {e["article"]: normaliser(e["texte"]) for e in extraits}
    assert normaliser(preuve["extrait"]) in textes[preuve["article"]]
    if preuve["type"] == "absence":
        assert preuve["termes_absents"]
        for terme in preuve["termes_absents"]:
            assert not any(terme.lower() in t.lower() for t in textes.values()), terme


def test_refus_casse_sans_formule_de_refus():
    for p in PIEGES:
        if p["type"] == "refus_casse":
            assert NON_TROUVE not in p["reponse_piegee"]
            assert "obsèques" in p["reponse_piegee"]


def test_pieges_varies():
    assert len({p["question_id"] for p in PIEGES if p["type"] != "refus_casse"}) == 8
    assert {p["doc"] for p in PIEGES} == set(DOCS)


# ─────────────────────────────────────────────
# Contrats reconstitués
# ─────────────────────────────────────────────


@pytest.mark.parametrize("doc", DOCS)
def test_contrat_conforme_au_25_09(doc):
    c = contrat(doc)
    ref = RUN["documents"][doc]
    assert c["controle"]["ecarts"] == []
    assert len(c["extraits"]) == ref["chunks"]
    assert sorted({e["article"] for e in c["extraits"] if e["article"]}) == ref["articles_chapitre"]
    assert len({e["id"] for e in c["extraits"]}) == len(c["extraits"])
    assert (HERE / "contrats" / f"{doc}.md").is_file()


# ─────────────────────────────────────────────
# Fiche d'annotation humaine
# ─────────────────────────────────────────────

_FICHE_RE = re.compile(r"^## A(\d{2}) — (Claude|Mistral) · (Q\d{2})$", re.MULTILINE)


def test_fiche_quarante_reponses_une_par_question_et_moteur():
    fiches = _FICHE_RE.findall(FICHE)
    assert [int(n) for n, _, _ in fiches] == list(range(1, 41))
    assert Counter((q, m) for _, m, q in fiches) == {
        (r["label"].split()[0], m): 1 for r in RUN["resultats"] for m in ("Claude", "Mistral")
    }


def test_fiche_ordre_melange():
    """Claude ne précède pas toujours Mistral sur la même question."""
    position = {(q, m): int(n) for n, m, q in _FICHE_RE.findall(FICHE)}
    questions = {q for q, _ in position}
    assert any(position[(q, "Mistral")] < position[(q, "Claude")] for q in questions)
    assert any(position[(q, "Claude")] < position[(q, "Mistral")] for q in questions)


def test_fiche_a_l_aveugle():
    """Aucun verdict pré-rempli, aucun résultat automatique, aucun piège."""
    assert "☒" not in FICHE and "[x]" not in FICHE.lower()
    for marqueur in ("verdict_historique", "garde-fou", "confirmé automatiquement", "À RELIRE", "latence"):
        assert marqueur not in FICHE
    for p in PIEGES:
        # La fiche cite les réponses d'origine, jamais les copies piégées.
        assert citation(p["reponse_origine"]) in FICHE
        assert citation(p["reponse_piegee"]) not in FICHE
    assert FICHE.count("- **C1 Fidélité** : ☐ oui ☐ non\n") == 40


def citation(texte: str) -> str:
    """Même rendu que build_annotation.citation()."""
    return "> " + texte.replace("\n", "\n> ")
