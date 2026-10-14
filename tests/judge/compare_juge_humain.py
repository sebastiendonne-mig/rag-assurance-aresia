"""
Compare les verdicts du juge LLM (tests/results/judge_upload_*.json) à
l'annotation humaine (tests/judge/annotation_humaine.md, une fois remplie), et
applique les seuils pré-enregistrés de tests/judge/seuils.md.

AUCUN réseau, aucun appel : lecture de fichiers seulement.

Fiche humaine : format de coche documenté en tête de fiche (☐ remplacé par ☒,
une seule case par critère). L'analyse est tolérante sur les espaces, jamais
sur le sens : une fiche incomplète (aucune case cochée) ou ambiguë (plusieurs
cases cochées, case illisible, libellé modifié) est signalée, jamais devinée,
et la comparaison s'arrête (code de sortie 1) tant qu'il en reste.

Calculs (seuils sur la répétition 1 ; la 2e ne sert qu'à mesurer la stabilité) :
  (a) désaccords INDULGENTS : le juge valide une réponse que l'humain rejette ;
  (b) désaccords SÉVÈRES : le juge rejette une réponse que l'humain valide ;
  désaccords de motif (rejet des deux côtés, critères différents) : listés, non comptés ;
  pièges détectés / manqués par moteur ; erreurs du juge ; détail par critère ;
  les 4 conditions de seuils.md et le verdict final.

Mode --pieges-seuls (amendement du 14/10/2026 de seuils.md) : la fiche humaine
n'est JAMAIS lue. Seuils sur les pièges seuls (au moins 8 détectés sur 10, au
plus 1 d'écart entre Claude et Mistral), détail piège par piège, puis liste des
réponses d'origine jugées « non » pour la relecture humaine qualitative (sans
seuil). Code de sortie : 0 si les deux seuils sont atteints, 1 sinon, 2 si les
résultats sont illisibles ou la mesure incomplète (jugement manquant ou en
ERREUR) : rien n'est deviné.

Usage (depuis la racine du dépôt) :
    .venv/bin/python tests/judge/compare_juge_humain.py --juge tests/results/judge_upload_<horodatage>.json
    .venv/bin/python tests/judge/compare_juge_humain.py --juge tests/results/judge_upload_<horodatage>.json --pieges-seuls
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
TESTS = HERE.parent
RESULTS_DIR = TESTS / "results"
FICHE = HERE / "annotation_humaine.md"

for chemin in (str(HERE), str(TESTS)):
    if chemin not in sys.path:
        sys.path.insert(0, chemin)

import build_annotation  # noqa: E402
from eval_upload_engines import ResultsWriter  # noqa: E402
from judge_upload_answers import PIEGES, REFERENCE_RUN, VERDICTS, charger_elements, verdict_global  # noqa: E402

EXIT_OK = 0
EXIT_FICHE_INCOMPLETE = 1
EXIT_SEUILS_NON_ATTEINTS = 1
EXIT_ENTREE_INVALIDE = 2

SEUIL_PIEGES_DETECTES = 8
SEUIL_ECART_MOTEURS = 1
SEUIL_DESACCORDS = 4

MOTEURS = {"anthropic": "Claude", "mistral": "Mistral"}
MOTEUR_DE_LIBELLE = {v: k for k, v in MOTEURS.items()}
CASE_VIDE = "☐"
CASE_COCHEE = "☒"
LIGNES_CRITERES = {
    "C1": "- **C1 Fidélité** :",
    "C2": "- **C2 Citations** :",
    "C3": "- **C3 Refus** :",
}
LIGNE_COMMENTAIRE = "- **Commentaire** :"
_TITRE_RE = re.compile(r"^## (A\d{2}) — (Claude|Mistral) · (Q\d{2})[ \t]*$", re.MULTILINE)
_CASE_RE = re.compile(r"(\S)\s*(sans objet|oui|non)\b")


# ─────────────────────────────────────────────
# Fiche humaine
# ─────────────────────────────────────────────


@dataclass
class FicheHumaine:
    id_fiche: str
    moteur: str
    question_id: str
    verdicts: dict[str, str] = field(default_factory=dict)
    commentaire: str = ""
    problemes: list[str] = field(default_factory=list)


@dataclass
class AnalyseFiche:
    fiches: list[FicheHumaine]
    problemes_globaux: list[str]

    @property
    def problemes(self) -> list[str]:
        return self.problemes_globaux + [f"{f.id_fiche} : {p}" for f in self.fiches for p in f.problemes]

    @property
    def complete(self) -> bool:
        return not self.problemes


def lire_cases(reste: str, options: tuple[str, ...]) -> tuple[str | None, str | None]:
    """(option cochée, problème). Exactement une case ☒ parmi les options attendues, sinon un problème."""
    trouvees = _CASE_RE.findall(reste)
    if [opt for _, opt in trouvees] != list(options):
        return None, "ambiguë (libellés des options modifiés)"
    illisibles = [opt for case, opt in trouvees if case not in (CASE_VIDE, CASE_COCHEE)]
    if illisibles:
        return None, f"ambiguë (case illisible devant « {illisibles[0]} »)"
    cochees = [opt for case, opt in trouvees if case == CASE_COCHEE]
    if not cochees:
        return None, "incomplète (aucune case cochée)"
    if len(cochees) > 1:
        return None, f"ambiguë ({len(cochees)} cases cochées)"
    return cochees[0], None


def _commentaire(lignes: list[str]) -> str:
    morceaux, dedans = [], False
    for ligne in lignes:
        if ligne.startswith(LIGNE_COMMENTAIRE):
            dedans = True
            morceaux.append(ligne[len(LIGNE_COMMENTAIRE):])
            continue
        if dedans:
            if ligne.strip() == "---":
                break
            morceaux.append(ligne)
    return "\n".join(m.strip() for m in morceaux).strip()


def analyser_section(id_fiche: str, moteur: str, question_id: str, texte: str) -> FicheHumaine:
    fiche = FicheHumaine(id_fiche, moteur, question_id)
    lignes = texte.splitlines()
    for c, libelle in LIGNES_CRITERES.items():
        candidates = [l for l in lignes if l.startswith(libelle)]
        if len(candidates) != 1:
            fiche.problemes.append(f"{c} : ligne absente ou répétée ({len(candidates)})")
            continue
        option, probleme = lire_cases(candidates[0][len(libelle):], VERDICTS[c])
        if probleme:
            fiche.problemes.append(f"{c} : {probleme}")
        else:
            fiche.verdicts[c] = option
    if sum(1 for l in lignes if l.startswith(LIGNE_COMMENTAIRE)) != 1:
        fiche.problemes.append("ligne Commentaire absente ou répétée")
    fiche.commentaire = _commentaire(lignes)
    return fiche


def titres_attendus() -> list[tuple[str, str, str]]:
    """(Axx, Claude|Mistral, Qxx) dans l'ordre exact généré par build_annotation (même graine)."""
    reponses = build_annotation.melanger(build_annotation.charger_reponses())
    return [(f"A{i:02d}", MOTEURS[r["moteur"]], r["code"]) for i, r in enumerate(reponses, 1)]


def analyser_fiche(texte: str) -> AnalyseFiche:
    titres = list(_TITRE_RE.finditer(texte))
    trouves = [m.groups() for m in titres]
    attendus = titres_attendus()
    globaux = []
    if trouves != attendus:
        manquants = [t[0] for t in attendus if t not in trouves]
        inattendus = [t[0] for t in trouves if t not in attendus]
        globaux.append(
            "structure de la fiche modifiée (titres « ## Axx — Moteur · Qxx » différents de ceux générés)"
            + (f" ; manquants : {', '.join(manquants)}" if manquants else "")
            + (f" ; inattendus : {', '.join(inattendus)}" if inattendus else "")
        )
    fiches = []
    for i, m in enumerate(titres):
        fin = titres[i + 1].start() if i + 1 < len(titres) else len(texte)
        id_fiche, moteur, q = m.groups()
        fiches.append(analyser_section(id_fiche, MOTEUR_DE_LIBELLE[moteur], q, texte[m.end():fin]))
    return AnalyseFiche(fiches, globaux)


# ─────────────────────────────────────────────
# Comparaison
# ─────────────────────────────────────────────


def criteres_non(verdicts: dict) -> set[str]:
    return {c for c, v in verdicts.items() if (v["verdict"] if isinstance(v, dict) else v) == "non"}


def _verdicts_humains(fiche: FicheHumaine) -> dict:
    return {c: {"verdict": v} for c, v in fiche.verdicts.items()}


def erreurs_du_juge(rep1: list[dict]) -> list[dict]:
    return [
        {"id_interne": j["id_interne"], "source": j["piege_id"] or "origine", "question_id": j["question_id"],
         "moteur": j["moteur"], "type": j["erreur"]["type"], "motif": j["erreur"].get("motif", "")}
        for j in rep1 if j["erreur"]
    ]


def tableau_des_pieges(pieges: list[dict]) -> list[dict]:
    """Piège détecté = « non » du juge sur le critère visé (seuils.md) ; None si le juge est en ERREUR."""
    tableau = []
    for j in pieges:
        detecte = None if j["erreur"] else j["verdicts"][j["critere_vise"]]["verdict"] == "non"
        tableau.append({
            "piege_id": j["piege_id"], "moteur": j["moteur"], "question_id": j["question_id"],
            "critere_vise": j["critere_vise"], "detecte": detecte,
            "verdict_juge": None if j["erreur"] else j["verdicts"][j["critere_vise"]]["verdict"],
        })
    return tableau


def conditions_pieges(detectes: dict[str, int]) -> list[dict]:
    """Les deux seuils sur les pièges, communs au texte d'origine et à l'amendement du 14/10/2026."""
    return [
        {"condition": f"Au moins {SEUIL_PIEGES_DETECTES} pièges détectés sur 10",
         "valeur": f"{sum(detectes.values())} / 10",
         "atteint": sum(detectes.values()) >= SEUIL_PIEGES_DETECTES},
        {"condition": f"Au plus {SEUIL_ECART_MOTEURS} piège d'écart entre Claude et Mistral",
         "valeur": f"Claude {detectes['anthropic']} / Mistral {detectes['mistral']} (écart {abs(detectes['anthropic'] - detectes['mistral'])})",
         "atteint": abs(detectes["anthropic"] - detectes["mistral"]) <= SEUIL_ECART_MOTEURS},
    ]


def comparer(rapport_juge: dict, fiches: list[FicheHumaine]) -> dict:
    jugements = rapport_juge["jugements"]
    rep1 = [j for j in jugements if j["repetition"] == 1]
    origine = {(j["question_id"], j["moteur"]): j for j in rep1 if j["source"] == "origine"}
    pieges = sorted((j for j in rep1 if j["source"] == "piege"), key=lambda j: j["piege_id"])

    attendus_origine = {(f.question_id, f.moteur) for f in fiches}
    manquants = sorted(f"{q} · {MOTEURS[m]}" for q, m in attendus_origine - set(origine))
    if len(pieges) != 10:
        manquants.append(f"pièges : {len(pieges)} jugés sur 10")

    erreurs = erreurs_du_juge(rep1)

    indulgents, severes, motifs = [], [], []
    accord_criteres = {c: {"accord": 0, "total": 0} for c in VERDICTS}
    for f in fiches:
        j = origine.get((f.question_id, f.moteur))
        if j is None or j["erreur"]:
            continue
        humain = _verdicts_humains(f)
        for c in VERDICTS:
            accord_criteres[c]["total"] += 1
            accord_criteres[c]["accord"] += j["verdicts"][c]["verdict"] == f.verdicts[c]
        g_juge, g_humain = j["verdict_global"], verdict_global(humain)
        non_juge, non_humain = criteres_non(j["verdicts"]), criteres_non(humain)
        ligne = {
            "id_fiche": f.id_fiche, "question_id": f.question_id, "moteur": f.moteur,
            "id_interne": j["id_interne"],
            "juge": {c: j["verdicts"][c] for c in VERDICTS},
            "humain": dict(f.verdicts), "commentaire_humain": f.commentaire,
        }
        if g_juge == "validée" and g_humain == "rejetée":
            indulgents.append({**ligne, "criteres": sorted(non_humain - non_juge)})
        elif g_juge == "rejetée" and g_humain == "validée":
            severes.append({**ligne, "criteres": sorted(non_juge - non_humain)})
        elif g_juge == g_humain == "rejetée" and non_juge != non_humain:
            motifs.append({**ligne, "criteres_juge": sorted(non_juge), "criteres_humain": sorted(non_humain)})

    tableau_pieges = tableau_des_pieges(pieges)
    detectes = {m: sum(1 for p in tableau_pieges if p["moteur"] == m and p["detecte"]) for m in MOTEURS}
    manques = [p for p in tableau_pieges if p["detecte"] is False]

    n_desaccords = len(indulgents) + len(severes)
    conditions = conditions_pieges(detectes) + [
        {"condition": f"Au plus {SEUIL_DESACCORDS} désaccords juge/humain sur les 40 réponses, chacun expliqué",
         "valeur": f"{n_desaccords} désaccord(s) — explications à rédiger ci-dessous",
         "atteint": n_desaccords <= SEUIL_DESACCORDS},
        {"condition": "Aucune réponse du juge en ERREUR au moment de la conclusion",
         "valeur": f"{len(erreurs)} erreur(s)" + (f", {len(manquants)} jugement(s) manquant(s)" if manquants else ""),
         "atteint": not erreurs and not manquants},
    ]
    if erreurs or manquants:
        verdict_final = "mesure incomplète"
    elif all(c["atteint"] for c in conditions):
        verdict_final = "seuils atteints"
    else:
        verdict_final = "seuils non atteints"

    return {
        "indulgents": indulgents,
        "severes": severes,
        "desaccords_de_motif": motifs,
        "pieges": tableau_pieges,
        "pieges_detectes": detectes,
        "pieges_manques": [p["piege_id"] for p in manques],
        "synthese_indulgence": f"erreurs indulgentes : {len(indulgents)} sur les réponses d'origine + {len(manques)} pièges manqués",
        "erreurs_juge": erreurs,
        "jugements_manquants": manquants,
        "detail_criteres": accord_criteres,
        "conditions": conditions,
        "verdict_final": verdict_final,
        "stabilite": stabilite(jugements),
    }


def stabilite(jugements: list[dict]) -> dict | None:
    """Répétition 1 contre répétition 2, à titre descriptif (None si une seule répétition)."""
    par_rep: dict[int, dict[str, dict]] = {}
    for j in jugements:
        par_rep.setdefault(j["repetition"], {})[j["id_interne"]] = j
    if 2 not in par_rep:
        return None
    communs = [i for i in par_rep[1] if i in par_rep[2] and par_rep[1][i]["verdicts"] and par_rep[2][i]["verdicts"]]
    differents = [
        i for i in communs
        if any(par_rep[1][i]["verdicts"][c]["verdict"] != par_rep[2][i]["verdicts"][c]["verdict"] for c in VERDICTS)
    ]
    global_diff = [i for i in communs if par_rep[1][i]["verdict_global"] != par_rep[2][i]["verdict_global"]]
    return {
        "comparables": len(communs),
        "verdicts_identiques_sur_les_3_criteres": len(communs) - len(differents),
        "verdict_global_identique": len(communs) - len(global_diff),
        "elements_instables": sorted(differents),
    }


# ─────────────────────────────────────────────
# Mode --pieges-seuls (amendement du 14/10/2026 de seuils.md)
# ─────────────────────────────────────────────


def elements_attendus() -> tuple[list[str], list[tuple[str, str]]]:
    """(ids des 10 pièges, (question, moteur) des 40 réponses d'origine) d'un run complet."""
    run = json.loads(REFERENCE_RUN.read_text(encoding="utf-8"))
    pieges = json.loads(PIEGES.read_text(encoding="utf-8"))["pieges"]
    elements = charger_elements(run, pieges)
    return (
        sorted(e.piege_id for e in elements if e.source == "piege"),
        sorted((e.question_id, e.moteur) for e in elements if e.source == "origine"),
    )


def pieges_seuls(rapport_juge: dict) -> dict:
    """Seuils sur les pièges seuls ; la fiche humaine n'intervient pas.

    Les réponses d'origine n'entrent dans aucun seuil : celles que le juge juge
    « non » sur au moins un critère forment la liste de relecture humaine
    qualitative. Un jugement manquant ou en ERREUR (pièges comme réponses
    d'origine) donne « mesure incomplète » : il n'est jamais compté comme
    détecté ni comme manqué.
    """
    rep1 = [j for j in rapport_juge["jugements"] if j["repetition"] == 1]
    ids_pieges, cles_origine = elements_attendus()
    pieges = {j["piege_id"]: j for j in rep1 if j["source"] == "piege"}
    origine = {(j["question_id"], j["moteur"]): j for j in rep1 if j["source"] == "origine"}

    manquants = [f"piège {p}" for p in ids_pieges if p not in pieges]
    manquants += [f"{q} · {MOTEURS[m]}" for q, m in cles_origine if (q, m) not in origine]
    erreurs = erreurs_du_juge(rep1)

    tableau_pieges = tableau_des_pieges([pieges[p] for p in ids_pieges if p in pieges])
    detectes = {m: sum(1 for p in tableau_pieges if p["moteur"] == m and p["detecte"]) for m in MOTEURS}
    conditions = conditions_pieges(detectes)
    if erreurs or manquants:
        verdict_final = "mesure incomplète"
    elif all(c["atteint"] for c in conditions):
        verdict_final = "seuils atteints"
    else:
        verdict_final = "seuils non atteints"

    relecture = [
        {"id_interne": j["id_interne"], "moteur": j["moteur"], "question_id": j["question_id"],
         "critere": c, "justification": j["verdicts"][c]["justification"]}
        for j in sorted(origine.values(), key=lambda j: j["id_interne"]) if not j["erreur"]
        for c in VERDICTS if j["verdicts"][c]["verdict"] == "non"
    ]
    return {
        "mode": "pièges seuls (amendement du 14/10/2026)",
        "pieges": tableau_pieges,
        "pieges_detectes": detectes,
        "pieges_manques": [p["piege_id"] for p in tableau_pieges if p["detecte"] is False],
        "erreurs_juge": erreurs,
        "jugements_manquants": manquants,
        "conditions": conditions,
        "verdict_final": verdict_final,
        "relecture_humaine": relecture,
    }


# ─────────────────────────────────────────────
# Rendu
# ─────────────────────────────────────────────


def _cellule(texte: str) -> str:
    return (texte or "").replace("|", "\\|").replace("\n", "<br>")


def _bloc_desaccord(d: dict, criteres: list[str]) -> list[str]:
    lignes = [
        f"### {d['id_fiche']} — {d['question_id']} · {MOTEURS[d['moteur']]} — critère(s) : {', '.join(criteres) or '—'}",
        "",
        "| Critère | Juge | Humain |",
        "|---|---|---|",
    ]
    for c in VERDICTS:
        juge = d["juge"][c]
        lignes.append(f"| {c} | **{juge['verdict']}** — {_cellule(juge['justification'])} | **{d['humain'][c]}** |")
    lignes += [
        f"| Commentaire humain | | {_cellule(d['commentaire_humain']) or '(vide)'} |",
        "",
        "Explication du désaccord : ",
        "",
    ]
    return lignes


def _lignes_pieges(c: dict) -> list[str]:
    lignes = [
        "## Pièges",
        "",
        "| Piège | Moteur | Question | Critère visé | Verdict du juge | Résultat |",
        "|---|---|---|---|---|---|",
    ]
    for p in c["pieges"]:
        resultat = "ERREUR du juge" if p["detecte"] is None else ("détecté" if p["detecte"] else "**manqué**")
        lignes.append(
            f"| {p['piege_id']} | {MOTEURS[p['moteur']]} | {p['question_id']} | {p['critere_vise']} | "
            f"{p['verdict_juge'] or '—'} | {resultat} |"
        )
    d = c["pieges_detectes"]
    return lignes + [
        "",
        f"Détectés : Claude {d['anthropic']} / 5 · Mistral {d['mistral']} / 5 · "
        f"écart {abs(d['anthropic'] - d['mistral'])}",
        "",
    ]


def _lignes_erreurs(c: dict) -> list[str]:
    lignes = []
    if not c["erreurs_juge"] and not c["jugements_manquants"]:
        lignes.append("- Aucune.")
    for e in c["erreurs_juge"]:
        lignes.append(f"- {e['id_interne']} ({e['source']}, {e['question_id']} · {MOTEURS[e['moteur']]}) : {e['type']} — {e['motif']}")
    for m in c["jugements_manquants"]:
        lignes.append(f"- jugement manquant : {m}")
    return lignes


def render_markdown_pieges(res: dict, rapport_juge: dict, chemin_juge: str, date_utc: str) -> str:
    h = rapport_juge["en_tete"]
    lignes = [
        "# Validation du juge LLM par les pièges seuls",
        "",
        f"- Date (UTC) : {date_utc}",
        f"- Résultats du juge : `{Path(chemin_juge).name}` — modèle `{h['modele']}`, {h['traitement']}",
        f"- Prompt du juge : sha256 `{h['empreintes']['prompt_juge.md']}`",
        "- Seuils : `tests/judge/seuils.md`, amendement du 14/10/2026 (pièges seuls) ; calculés sur la répétition 1.",
        "- La fiche d'annotation humaine n'est pas lue.",
        "",
        f"## Verdict final : **{res['verdict_final'].upper()}**",
        "",
        "| Condition (seuils.md, amendement du 14/10/2026) | Valeur | Résultat |",
        "|---|---|---|",
    ]
    for cond in res["conditions"]:
        lignes.append(f"| {cond['condition']} | {cond['valeur']} | {'atteint' if cond['atteint'] else 'NON ATTEINT'} |")
    lignes.append("")
    lignes += _lignes_pieges(res)
    lignes += ["## Erreurs du juge et jugements manquants", ""]
    lignes += _lignes_erreurs(res)
    lignes += [
        "",
        f"## Relecture humaine qualitative (sans seuil) : {len(res['relecture_humaine'])} critère(s) « non »",
        "",
        "Réponses d'origine (pas les pièges) jugées « non » sur au moins un critère.",
        "",
    ]
    if not res["relecture_humaine"]:
        lignes.append("- Aucune réponse d'origine jugée « non ».")
    else:
        lignes += ["| Id | Moteur | Question | Critère | Justification du juge |", "|---|---|---|---|---|"]
        for r in res["relecture_humaine"]:
            lignes.append(
                f"| {r['id_interne']} | {MOTEURS[r['moteur']]} | {r['question_id']} | {r['critere']} | "
                f"{_cellule(r['justification'])} |"
            )
    lignes.append("")
    return "\n".join(lignes)


def render_markdown(comparaison: dict, rapport_juge: dict, chemin_juge: str, date_utc: str) -> str:
    h = rapport_juge["en_tete"]
    c = comparaison
    lignes = [
        "# Comparaison juge LLM / annotation humaine",
        "",
        f"- Date (UTC) : {date_utc}",
        f"- Résultats du juge : `{Path(chemin_juge).name}` — modèle `{h['modele']}`, {h['traitement']}",
        f"- Prompt du juge : sha256 `{h['empreintes']['prompt_juge.md']}`",
        "- Seuils : `tests/judge/seuils.md` (pré-enregistrés) ; calculés sur la répétition 1.",
        "",
        f"## Verdict final : **{c['verdict_final'].upper()}**",
        "",
        "| Condition (seuils.md) | Valeur | Résultat |",
        "|---|---|---|",
    ]
    for cond in c["conditions"]:
        lignes.append(f"| {cond['condition']} | {cond['valeur']} | {'atteint' if cond['atteint'] else 'NON ATTEINT'} |")
    lignes += ["", f"**{c['synthese_indulgence']}**", ""]

    lignes += [f"## (a) Désaccords INDULGENTS — le juge valide, l'humain rejette : {len(c['indulgents'])}", ""]
    if not c["indulgents"]:
        lignes += ["- Aucun.", ""]
    for d in c["indulgents"]:
        lignes += _bloc_desaccord(d, d["criteres"])
    lignes += [f"## (b) Désaccords SÉVÈRES — le juge rejette, l'humain valide : {len(c['severes'])}", ""]
    if not c["severes"]:
        lignes += ["- Aucun.", ""]
    for d in c["severes"]:
        lignes += _bloc_desaccord(d, d["criteres"])

    lignes += [
        f"## Désaccords de motif (rejet des deux côtés, critères différents) — non comptés : {len(c['desaccords_de_motif'])}",
        "",
    ]
    if not c["desaccords_de_motif"]:
        lignes += ["- Aucun.", ""]
    for d in c["desaccords_de_motif"]:
        lignes.append(
            f"- {d['id_fiche']} — {d['question_id']} · {MOTEURS[d['moteur']]} : juge {', '.join(d['criteres_juge'])}"
            f" / humain {', '.join(d['criteres_humain'])}"
        )
    lignes.append("")

    lignes += _lignes_pieges(c)
    lignes += ["## Erreurs du juge (ni accord ni désaccord)", ""]
    lignes += _lignes_erreurs(c)
    lignes += [
        "",
        "## Détail par critère (information, sur les 40 réponses d'origine)",
        "",
        "| Critère | Accord juge / humain |",
        "|---|---|",
    ]
    for crit, v in c["detail_criteres"].items():
        lignes.append(f"| {crit} | {v['accord']} / {v['total']} |")
    if c["stabilite"]:
        s = c["stabilite"]
        lignes += [
            "",
            "## Stabilité du juge (répétition 1 / répétition 2, descriptif)",
            "",
            f"- Éléments comparables : {s['comparables']}",
            f"- Verdicts identiques sur les 3 critères : {s['verdicts_identiques_sur_les_3_criteres']}",
            f"- Verdict global identique : {s['verdict_global_identique']}",
            f"- Éléments instables : {', '.join(s['elements_instables']) or 'aucun'}",
        ]
    lignes.append("")
    return "\n".join(lignes)


# ─────────────────────────────────────────────
# Point d'entrée
# ─────────────────────────────────────────────


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compare le juge LLM à l'annotation humaine (sans réseau).")
    p.add_argument("--juge", required=True, help="fichier tests/results/judge_upload_<horodatage>.json")
    p.add_argument("--fiche", default=str(FICHE), help="fiche d'annotation remplie (ignorée avec --pieges-seuls)")
    p.add_argument(
        "--pieges-seuls", action="store_true",
        help="amendement du 14/10/2026 de seuils.md : seuils sur les pièges seuls, la fiche n'est jamais lue",
    )
    p.add_argument("--out-dir", default=str(RESULTS_DIR), help=argparse.SUPPRESS)
    return p.parse_args(argv)


def main_pieges_seuls(args: argparse.Namespace, rapport_juge: dict, out: Callable[[str], None], horodatage: datetime) -> int:
    try:
        res = pieges_seuls(rapport_juge)
        md = render_markdown_pieges(res, rapport_juge, args.juge, horodatage.isoformat(timespec="seconds"))
    except (KeyError, TypeError, AttributeError) as exc:
        out(f"Résultats du juge illisibles ({type(exc).__name__}) : {args.juge}. Rien n'est deviné.")
        return EXIT_ENTREE_INVALIDE
    writer = ResultsWriter.reserve(
        Path(args.out_dir), horodatage.strftime("%Y%m%d_%H%M%S"), False, [], prefix="judge_compare_pieges",
    )
    writer.write_json({"juge": str(args.juge), **res})
    writer.write_markdown(md)
    out(md)
    out(f"Validation par les pièges : {writer.md_path}")
    if res["verdict_final"] == "mesure incomplète":
        n = len(res["erreurs_juge"]) + len(res["jugements_manquants"])
        out(f"Mesure incomplète : {n} jugement(s) manquant(s) ou en ERREUR. Rien n'est deviné ; aucun verdict sur les seuils.")
        return EXIT_ENTREE_INVALIDE
    return EXIT_OK if res["verdict_final"] == "seuils atteints" else EXIT_SEUILS_NON_ATTEINTS


def main(
    argv: list[str] | None = None,
    *,
    out: Callable[[str], None] = print,
    now: Callable[[], datetime] | None = None,
) -> int:
    args = parse_args(argv)
    try:
        rapport_juge = json.loads(Path(args.juge).read_text(encoding="utf-8"))
        rapport_juge["jugements"], rapport_juge["en_tete"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        out(f"Résultats du juge illisibles ({type(exc).__name__}) : {args.juge}")
        return EXIT_ENTREE_INVALIDE

    if args.pieges_seuls:
        return main_pieges_seuls(args, rapport_juge, out, (now or (lambda: datetime.now(timezone.utc)))())

    analyse = analyser_fiche(Path(args.fiche).read_text(encoding="utf-8"))
    if not analyse.complete:
        out(f"Fiche humaine incomplète ou ambiguë : {len(analyse.problemes)} problème(s). Rien n'est deviné ;")
        out("compléter la fiche puis relancer. Aucun verdict final.")
        for p in analyse.problemes:
            out(f"  - {p}")
        return EXIT_FICHE_INCOMPLETE

    comparaison = comparer(rapport_juge, analyse.fiches)
    horodatage = (now or (lambda: datetime.now(timezone.utc)))()
    writer = ResultsWriter.reserve(
        Path(args.out_dir), horodatage.strftime("%Y%m%d_%H%M%S"), False, [], prefix="judge_compare",
    )
    md = render_markdown(comparaison, rapport_juge, args.juge, horodatage.isoformat(timespec="seconds"))
    writer.write_json({"juge": str(args.juge), "fiche": str(args.fiche), **comparaison})
    writer.write_markdown(md)
    out(md)
    out(f"Comparaison : {writer.md_path}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
