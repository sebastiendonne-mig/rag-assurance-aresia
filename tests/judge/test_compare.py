"""
Tests de la comparaison juge / humain sur données FICTIVES : fiches synthétiques
construites depuis le générateur (jamais la vraie fiche remplie), résultats de
juge fabriqués. Aucun réseau.
"""
import builtins
import io
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

import build_annotation
import compare_juge_humain as cmp
import judge_upload_answers as juge

NOW = lambda: datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)  # noqa: E731
VIERGE = build_annotation.render(build_annotation.charger_reponses())
TITRES = cmp.titres_attendus()                       # [(A01, Claude, Q02), …]
FICHE_DE = {(q, cmp.MOTEUR_DE_LIBELLE[m]): a for a, m, q in TITRES}
DEFAUT = ("oui", "oui", "sans objet")


# ─────────────────────────────────────────────
# Fabriques de données fictives
# ─────────────────────────────────────────────


def cocher(ligne: str, choix: str) -> str:
    return re.sub(rf"☐ ({re.escape(choix)})\b", r"☒ \1", ligne, count=1)


def remplir(choix: dict | None = None, commentaires: dict | None = None, texte: str = VIERGE) -> str:
    """choix : {"A07": ("non", "oui", "sans objet")} ; les autres fiches reçoivent DEFAUT."""
    choix, commentaires = choix or {}, commentaires or {}
    entete, reste = texte.split("\n## A01 ", 1)
    sections = re.split(r"(?=^## A\d{2} )", "## A01 " + reste, flags=re.MULTILINE)
    sortie = []
    for s in sections:
        a = s[3:6]
        c1, c2, c3 = choix.get(a, DEFAUT)
        lignes = []
        for l in s.split("\n"):
            if l.startswith("- **C1 Fidélité** :"):
                l = cocher(l, c1)
            elif l.startswith("- **C2 Citations** :"):
                l = cocher(l, c2)
            elif l.startswith("- **C3 Refus** :"):
                l = cocher(l, c3)
            elif l.startswith("- **Commentaire** :") and a in commentaires:
                l = f"- **Commentaire** : {commentaires[a]}"
            lignes.append(l)
        sortie.append("\n".join(lignes))
    return entete + "\n" + "".join(sortie)


def _verdicts(c1, c2, c3, justification="justification du juge"):
    return {c: {"justification": f"{justification} ({c})", "verdict": v} for c, v in (("C1", c1), ("C2", c2), ("C3", c3))}


def rapport(origine=None, pieges=None, erreurs=(), repetitions=1, instables=()):
    """origine : {(Q, moteur): (c1, c2, c3)} ; pieges : {Pxx: (c1, c2, c3)} (défaut : critère visé « non »)."""
    origine, pieges = origine or {}, pieges or {}
    run = json.loads(juge.REFERENCE_RUN.read_text(encoding="utf-8"))
    pj = json.loads(juge.PIEGES.read_text(encoding="utf-8"))["pieges"]
    elements = juge.charger_elements(run, pj)
    jugements = []
    for rep in range(1, repetitions + 1):
        for e in elements:
            cle = e.piege_id or (e.question_id, e.moteur)
            if e.source == "piege":
                v = list(pieges.get(e.piege_id, DEFAUT))
                if e.piege_id not in pieges:
                    v[int(e.critere_vise[1]) - 1] = "non"
            else:
                v = origine.get((e.question_id, e.moteur), DEFAUT)
            if rep == 2 and cle in instables:
                v = ("non", "non", "non")
            res = {"verdicts": _verdicts(*v), "erreur": None}
            if rep == 1 and cle in erreurs:
                res = {"verdicts": None, "erreur": {"type": "reponse_invalide", "motif": "JSON invalide"}}
            res["verdict_global"] = juge.verdict_global(res["verdicts"]) if res["verdicts"] else None
            jugements.append({**e.correspondance(), "repetition": rep, **res})
    return {
        "en_tete": {"modele": "gemini-3.8-flash", "traitement": juge.traitement("eu"),
                    "empreintes": {"prompt_juge.md": "0" * 64}},
        "jugements": jugements,
    }


def comparer(fiche_texte=None, **kw):
    analyse = cmp.analyser_fiche(fiche_texte or remplir())
    assert analyse.complete, analyse.problemes
    return cmp.comparer(rapport(**kw), analyse.fiches)


def conditions(c):
    return [x["atteint"] for x in c["conditions"]]


# ─────────────────────────────────────────────
# Analyseur de fiche
# ─────────────────────────────────────────────


def test_fiche_complete():
    analyse = cmp.analyser_fiche(remplir({"A05": ("non", "sans objet", "oui")}, {"A05": "chiffre faux art. 15"}))
    assert analyse.complete and len(analyse.fiches) == 40
    a05 = next(f for f in analyse.fiches if f.id_fiche == "A05")
    assert a05.verdicts == {"C1": "non", "C2": "sans objet", "C3": "oui"}
    assert a05.commentaire == "chiffre faux art. 15"


def test_fiche_vierge_entierement_incomplete():
    analyse = cmp.analyser_fiche(VIERGE)
    assert not analyse.complete
    assert len(analyse.problemes) == 120 and all("incomplète" in p for p in analyse.problemes)


def test_fiche_incomplete_un_critere_non_coche():
    texte = remplir()
    sections = texte.split("## A12 ", 1)
    texte = sections[0] + "## A12 " + sections[1].replace("- **C2 Citations** : ☒ oui", "- **C2 Citations** : ☐ oui", 1)
    analyse = cmp.analyser_fiche(texte)
    assert analyse.problemes == ["A12 : C2 : incomplète (aucune case cochée)"]


@pytest.mark.parametrize("remplacement, motif", [
    ("- **C1 Fidélité** : ☒ oui ☒ non", "2 cases cochées"),
    ("- **C1 Fidélité** : X oui ☐ non", "case illisible"),
    ("- **C1 Fidélité** : ☒ oui", "libellés des options modifiés"),
    ("- **C1 Fidélité** : ☒ oui ☐ non ☐ sans objet", "libellés des options modifiés"),
])
def test_fiche_ambigue_jamais_devinee(remplacement, motif):
    texte = remplir()
    avant, apres = texte.split("## A03 ", 1)
    apres = apres.replace("- **C1 Fidélité** : ☒ oui ☐ non", remplacement, 1)
    analyse = cmp.analyser_fiche(avant + "## A03 " + apres)
    assert len(analyse.problemes) == 1
    assert analyse.problemes[0].startswith("A03 : C1 : ambiguë") and motif in analyse.problemes[0]


def test_tolerance_sur_les_espaces():
    texte = remplir()
    avant, apres = texte.split("## A03 ", 1)
    apres = apres.replace("- **C1 Fidélité** : ☒ oui ☐ non", "- **C1 Fidélité** :☒oui   ☐  non  ", 1)
    analyse = cmp.analyser_fiche(avant + "## A03 " + apres)
    assert analyse.complete


def test_commentaire_sur_plusieurs_lignes():
    texte = remplir(commentaires={"A08": "premier point\nsecond point"})
    a08 = next(f for f in cmp.analyser_fiche(texte).fiches if f.id_fiche == "A08")
    assert a08.commentaire == "premier point\nsecond point"


def test_structure_modifiee_signalee():
    texte = remplir().replace("## A10 — ", "## A99 — ", 1)
    analyse = cmp.analyser_fiche(texte)
    assert not analyse.complete and "structure de la fiche modifiée" in analyse.problemes[0]


def test_main_refuse_une_fiche_incomplete_sans_verdict(tmp_path):
    juge_json = tmp_path / "judge_upload_x.json"
    juge_json.write_text(json.dumps(rapport()), encoding="utf-8")
    fiche = tmp_path / "fiche.md"
    fiche.write_text(VIERGE, encoding="utf-8")
    sorties = []
    code = cmp.main(["--juge", str(juge_json), "--fiche", str(fiche), "--out-dir", str(tmp_path / "out")],
                    out=sorties.append, now=NOW)
    assert code == cmp.EXIT_FICHE_INCOMPLETE
    assert "Aucun verdict final" in "\n".join(sorties) and not (tmp_path / "out").exists()


# ─────────────────────────────────────────────
# Comparaison
# ─────────────────────────────────────────────


def test_tout_concorde_seuils_atteints():
    c = comparer()
    assert c["indulgents"] == [] and c["severes"] == [] and c["desaccords_de_motif"] == []
    assert c["pieges_detectes"] == {"anthropic": 5, "mistral": 5}
    assert conditions(c) == [True, True, True, True]
    assert c["verdict_final"] == "seuils atteints"
    assert c["synthese_indulgence"] == "erreurs indulgentes : 0 sur les réponses d'origine + 0 pièges manqués"
    assert all(v == {"accord": 40, "total": 40} for v in c["detail_criteres"].values())


def test_desaccord_indulgent():
    a = FICHE_DE[("Q09", "anthropic")]
    c = comparer(remplir({a: ("non", "oui", "sans objet")}, {a: "minimum faux"}))
    assert len(c["indulgents"]) == 1 and c["severes"] == []
    d = c["indulgents"][0]
    assert (d["id_fiche"], d["question_id"], d["moteur"], d["criteres"]) == (a, "Q09", "anthropic", ["C1"])
    assert d["commentaire_humain"] == "minimum faux" and d["juge"]["C1"]["justification"]
    assert c["synthese_indulgence"].startswith("erreurs indulgentes : 1 sur")


def test_desaccord_severe():
    c = comparer(origine={("Q07", "mistral"): ("oui", "non", "sans objet")})
    assert c["indulgents"] == [] and len(c["severes"]) == 1
    assert c["severes"][0]["criteres"] == ["C2"] and c["severes"][0]["moteur"] == "mistral"


def test_desaccord_de_motif_liste_mais_non_compte():
    a = FICHE_DE[("Q04", "mistral")]
    c = comparer(remplir({a: ("non", "oui", "sans objet")}), origine={("Q04", "mistral"): ("oui", "non", "sans objet")})
    assert c["indulgents"] == [] and c["severes"] == []
    assert len(c["desaccords_de_motif"]) == 1
    assert c["desaccords_de_motif"][0]["criteres_juge"] == ["C2"]
    assert c["desaccords_de_motif"][0]["criteres_humain"] == ["C1"]
    assert c["conditions"][2]["valeur"].startswith("0 désaccord")


def test_sans_objet_jamais_bloquant():
    a = FICHE_DE[("Q20", "anthropic")]
    c = comparer(remplir({a: ("oui", "sans objet", "oui")}), origine={("Q20", "anthropic"): ("oui", "oui", "oui")})
    assert c["indulgents"] == [] and c["severes"] == [] and c["desaccords_de_motif"] == []
    assert c["detail_criteres"]["C2"]["accord"] == 39


def test_erreur_du_juge_ni_accord_ni_desaccord_et_mesure_incomplete():
    a = FICHE_DE[("Q03", "anthropic")]
    c = comparer(remplir({a: ("non", "oui", "sans objet")}), erreurs={("Q03", "anthropic")})
    assert c["indulgents"] == [] and c["severes"] == []
    assert [e["question_id"] for e in c["erreurs_juge"]] == ["Q03"]
    assert conditions(c) == [True, True, True, False]
    assert c["verdict_final"] == "mesure incomplète"
    assert c["detail_criteres"]["C1"]["total"] == 39


def test_piege_en_erreur_mesure_incomplete():
    c = comparer(erreurs={"P04"})
    assert next(p for p in c["pieges"] if p["piege_id"] == "P04")["detecte"] is None
    assert c["verdict_final"] == "mesure incomplète"


def test_piege_manque():
    c = comparer(pieges={"P05": ("oui", "oui", "sans objet")})
    assert c["pieges_manques"] == ["P05"]
    assert c["pieges_detectes"] == {"anthropic": 4, "mistral": 5}
    assert c["synthese_indulgence"].endswith("+ 1 pièges manqués")
    assert conditions(c) == [True, True, True, True] and c["verdict_final"] == "seuils atteints"


def test_piege_detecte_sur_le_critere_vise_seulement():
    """P07 vise C2 : un « non » en C1 seul ne compte pas comme détection."""
    c = comparer(pieges={"P07": ("non", "oui", "sans objet")})
    assert c["pieges_manques"] == ["P07"]


def test_seuil_pieges_non_atteint():
    c = comparer(pieges={p: DEFAUT for p in ("P01", "P02", "P03")})
    assert sum(c["pieges_detectes"].values()) == 7
    assert conditions(c)[0] is False and c["verdict_final"] == "seuils non atteints"


def test_seuil_ecart_moteurs_non_atteint():
    c = comparer(pieges={"P02": DEFAUT, "P04": DEFAUT})      # deux pièges Mistral manqués
    assert c["pieges_detectes"] == {"anthropic": 5, "mistral": 3}
    assert conditions(c) == [True, False, True, True] and c["verdict_final"] == "seuils non atteints"


def test_seuil_ecart_moteurs_atteint_a_un():
    c = comparer(pieges={"P02": DEFAUT})
    assert conditions(c)[1] is True


def _avec_desaccords(n):
    cles = [k for k in FICHE_DE if k[0] != "Q20"][:n]
    return comparer(origine={k: ("oui", "non", "sans objet") for k in cles})


def test_seuil_desaccords_atteint_a_quatre():
    c = _avec_desaccords(4)
    assert len(c["severes"]) == 4 and conditions(c)[2] is True and c["verdict_final"] == "seuils atteints"


def test_seuil_desaccords_non_atteint_a_cinq():
    c = _avec_desaccords(5)
    assert conditions(c)[2] is False and c["verdict_final"] == "seuils non atteints"


def test_stabilite_avec_deux_repetitions():
    c = comparer(repetitions=2, instables={("Q01", "anthropic"), "P03"})
    s = c["stabilite"]
    assert s["comparables"] == 50 and s["verdicts_identiques_sur_les_3_criteres"] == 48
    assert len(s["elements_instables"]) == 2
    # Les seuils restent calculés sur la répétition 1.
    assert c["verdict_final"] == "seuils atteints"


def test_stabilite_absente_avec_une_repetition():
    assert comparer()["stabilite"] is None


def test_jugements_manquants_mesure_incomplete():
    r = rapport()
    r["jugements"] = r["jugements"][:1]   # ex. résultats d'un mode fumée
    c = cmp.comparer(r, cmp.analyser_fiche(remplir()).fiches)
    assert c["jugements_manquants"] and c["verdict_final"] == "mesure incomplète"


def test_main_ecrit_le_rapport_de_comparaison(tmp_path):
    a = FICHE_DE[("Q09", "anthropic")]
    juge_json = tmp_path / "judge_upload_x.json"
    juge_json.write_text(json.dumps(rapport(pieges={"P05": DEFAUT})), encoding="utf-8")
    fiche = tmp_path / "fiche.md"
    fiche.write_text(remplir({a: ("non", "oui", "sans objet")}, {a: "minimum | faux"}), encoding="utf-8")
    sorties = []
    code = cmp.main(["--juge", str(juge_json), "--fiche", str(fiche), "--out-dir", str(tmp_path)],
                    out=sorties.append, now=NOW)
    assert code == cmp.EXIT_OK
    md = (tmp_path / "judge_compare_20261102_080000.md").read_text(encoding="utf-8")
    assert "## Verdict final : **SEUILS ATTEINTS**" in md
    assert "erreurs indulgentes : 1 sur les réponses d'origine + 1 pièges manqués" in md
    assert f"### {a} — Q09 · Claude — critère(s) : C1" in md and "minimum \\| faux" in md
    assert "Explication du désaccord" in md
    assert "| P05 | Claude | Q01 | C1 | oui | **manqué** |" in md
    assert (tmp_path / "judge_compare_20261102_080000.json").exists()


def test_main_resultats_du_juge_illisibles(tmp_path):
    mauvais = tmp_path / "x.json"
    mauvais.write_text("{", encoding="utf-8")
    code = cmp.main(["--juge", str(mauvais), "--fiche", str(tmp_path / "absente.md")], out=lambda s: None)
    assert code == cmp.EXIT_ENTREE_INVALIDE


# ─────────────────────────────────────────────
# Mode --pieges-seuls (amendement du 14/10/2026 de seuils.md)
# ─────────────────────────────────────────────


def lancer_pieges_seuls(tmp_path, rapport_juge, fiche=None):
    juge_json = tmp_path / "judge_upload_x.json"
    juge_json.write_text(json.dumps(rapport_juge), encoding="utf-8")
    argv = ["--juge", str(juge_json), "--pieges-seuls", "--out-dir", str(tmp_path / "out")]
    if fiche:
        argv += ["--fiche", str(fiche)]
    sorties = []
    code = cmp.main(argv, out=sorties.append, now=NOW)
    return code, "\n".join(sorties)


def test_pieges_seuls_huit_sur_dix_atteint(tmp_path):
    code, sortie = lancer_pieges_seuls(tmp_path, rapport(pieges={"P01": DEFAUT, "P02": DEFAUT}))
    assert code == cmp.EXIT_OK
    assert "## Verdict final : **SEUILS ATTEINTS**" in sortie
    assert "| Au moins 8 pièges détectés sur 10 | 8 / 10 | atteint |" in sortie
    assert "Claude 4 / Mistral 4 (écart 0) | atteint |" in sortie
    # Détail piège par piège.
    lignes = [l for l in sortie.splitlines() if re.match(r"\| P\d{2} \|", l)]
    assert [l.split(" | ")[0] for l in lignes] == [f"| P{i:02d}" for i in range(1, 11)]
    assert lignes[0].startswith("| P01 | Claude |") and lignes[0].endswith("| C1 | oui | **manqué** |")
    assert lignes[6].startswith("| P07 | Claude |") and lignes[6].endswith("| C2 | non | détecté |")
    md = (tmp_path / "out" / "judge_compare_pieges_20261102_080000.md").read_text(encoding="utf-8")
    assert md in sortie
    res = json.loads((tmp_path / "out" / "judge_compare_pieges_20261102_080000.json").read_text(encoding="utf-8"))
    assert res["pieges_manques"] == ["P01", "P02"] and res["verdict_final"] == "seuils atteints"


def test_pieges_seuls_sept_sur_dix_non_atteint(tmp_path):
    code, sortie = lancer_pieges_seuls(tmp_path, rapport(pieges={p: DEFAUT for p in ("P01", "P02", "P03")}))
    assert code == cmp.EXIT_SEUILS_NON_ATTEINTS == 1
    assert "## Verdict final : **SEUILS NON ATTEINTS**" in sortie
    assert "| Au moins 8 pièges détectés sur 10 | 7 / 10 | NON ATTEINT |" in sortie
    assert "Claude 3 / Mistral 4 (écart 1) | atteint |" in sortie


def test_pieges_seuls_ecart_de_deux_non_atteint(tmp_path):
    code, sortie = lancer_pieges_seuls(tmp_path, rapport(pieges={"P02": DEFAUT, "P04": DEFAUT}))
    assert code == cmp.EXIT_SEUILS_NON_ATTEINTS
    assert "| Au moins 8 pièges détectés sur 10 | 8 / 10 | atteint |" in sortie
    assert "Claude 5 / Mistral 3 (écart 2) | NON ATTEINT |" in sortie


def test_pieges_seuls_piege_manquant_erreur_explicite(tmp_path):
    r = rapport()
    r["jugements"] = [j for j in r["jugements"] if j["piege_id"] != "P04"]
    code, sortie = lancer_pieges_seuls(tmp_path, r)
    assert code == cmp.EXIT_ENTREE_INVALIDE
    assert "## Verdict final : **MESURE INCOMPLÈTE**" in sortie
    assert "- jugement manquant : piège P04" in sortie
    assert "Rien n'est deviné ; aucun verdict sur les seuils." in sortie


def test_pieges_seuls_resultats_de_fumee_mesure_incomplete(tmp_path):
    r = rapport()
    r["jugements"] = r["jugements"][:1]
    code, sortie = lancer_pieges_seuls(tmp_path, r)
    assert code == cmp.EXIT_ENTREE_INVALIDE
    assert sortie.count("- jugement manquant :") == 49


@pytest.mark.parametrize("cle", ["P07", ("Q05", "mistral")])
def test_pieges_seuls_erreur_du_juge_mesure_incomplete(tmp_path, cle):
    code, sortie = lancer_pieges_seuls(tmp_path, rapport(erreurs={cle}))
    assert code == cmp.EXIT_ENTREE_INVALIDE
    assert "MESURE INCOMPLÈTE" in sortie and "reponse_invalide" in sortie


def test_pieges_seuls_fichier_absent(tmp_path):
    sorties = []
    code = cmp.main(["--juge", str(tmp_path / "absent.json"), "--pieges-seuls", "--out-dir", str(tmp_path / "out")],
                    out=sorties.append, now=NOW)
    assert code == cmp.EXIT_ENTREE_INVALIDE and "illisibles" in sorties[0]
    assert not (tmp_path / "out").exists()


def test_pieges_seuls_jugement_malforme(tmp_path):
    r = rapport()
    del next(j for j in r["jugements"] if j["piege_id"] == "P01")["verdicts"]["C1"]
    code, sortie = lancer_pieges_seuls(tmp_path, r)
    assert code == cmp.EXIT_ENTREE_INVALIDE and "illisibles (KeyError)" in sortie
    assert not (tmp_path / "out").exists()


def test_pieges_seuls_liste_de_relecture_sans_seuil(tmp_path):
    r = rapport(origine={("Q07", "mistral"): ("oui", "non", "sans objet"),
                         ("Q09", "anthropic"): ("non", "non", "sans objet")})
    res = cmp.pieges_seuls(r)
    # Réponses d'origine seulement (les pièges, tous « non », n'y figurent pas), une ligne par critère « non ».
    assert sorted((x["question_id"], x["moteur"], x["critere"]) for x in res["relecture_humaine"]) == [
        ("Q07", "mistral", "C2"), ("Q09", "anthropic", "C1"), ("Q09", "anthropic", "C2"),
    ]
    assert all(x["justification"] == f"justification du juge ({x['critere']})" for x in res["relecture_humaine"])
    assert res["verdict_final"] == "seuils atteints"          # aucun seuil sur la relecture
    code, sortie = lancer_pieges_seuls(tmp_path, r)
    assert code == cmp.EXIT_OK
    assert "## Relecture humaine qualitative (sans seuil) : 3 critère(s) « non »" in sortie
    assert "| Mistral | Q07 | C2 | justification du juge (C2) |" in sortie


def test_pieges_seuls_relecture_vide():
    res = cmp.pieges_seuls(rapport())
    assert res["relecture_humaine"] == []
    md = cmp.render_markdown_pieges(res, rapport(), "x.json", "2026-11-02T08:00:00+00:00")
    assert "- Aucune réponse d'origine jugée « non »." in md


def test_pieges_seuls_ne_lit_jamais_la_fiche(tmp_path, monkeypatch):
    fiche = tmp_path / "fiche.md"
    fiche.write_text(remplir(), encoding="utf-8")
    r = rapport()
    ouverts = []
    vrai_open = io.open

    def espion(fichier, *args, **kwargs):
        if isinstance(fichier, (str, os.PathLike)):
            ouverts.append(Path(fichier).resolve())
        return vrai_open(fichier, *args, **kwargs)

    monkeypatch.setattr(io, "open", espion)
    monkeypatch.setattr(builtins, "open", espion)
    monkeypatch.setattr(cmp, "analyser_fiche", lambda *a, **k: pytest.fail("la fiche ne doit pas être analysée"))
    code, _ = lancer_pieges_seuls(tmp_path, r, fiche=fiche)
    assert code == cmp.EXIT_OK
    # Témoin : l'espion voit bien les lectures réelles (résultats du juge, run de référence).
    assert (tmp_path / "judge_upload_x.json").resolve() in ouverts
    assert juge.REFERENCE_RUN.resolve() in ouverts
    assert fiche.resolve() not in ouverts and cmp.FICHE.resolve() not in ouverts
