"""
Génère tests/judge/annotation_humaine.md : la fiche d'annotation humaine,
À L'AVEUGLE, des 40 réponses d'origine du 25/09/2026 (20 questions x Claude
et Mistral, chemin upload). Les copies piégées n'y figurent pas.

À l'aveugle : seuls la question et le texte de la réponse sont repris.
Aucune donnée automatique du run (analyse des citations, garde-fou, verdict
historique, latence, coût) n'est lue ni écrite.

Ordre mélangé de façon déterministe (graine fixe) : on ne voit pas toujours
Claude avant Mistral sur la même question, et une nouvelle génération donne
exactement le même fichier.

Usage (depuis la racine du dépôt) :
    .venv/bin/python tests/judge/build_annotation.py
"""
from __future__ import annotations

import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
REFERENCE_RUN = HERE.parent / "results" / "upload_eval_20260925_104952.json"
SORTIE = HERE / "annotation_humaine.md"
GRAINE = 20260925

MOTEURS = {"anthropic": "Claude", "mistral": "Mistral"}

EN_TETE = """# Annotation humaine — fidélité au contrat (à l'aveugle)

40 réponses réelles du 25/09/2026 (évaluation du sous-lot 3.2, chemin upload) :
20 questions × Claude et Mistral, dans un ordre mélangé (graine {graine}).
Aucun résultat automatique n'est affiché ici.

**Contrats de référence** (texte intégral, articles en titres) :
`tests/judge/contrats/` — {liens}

## Rappel de la grille (détail : `tests/judge/grille.md`)

Juger chaque réponse contre le **contrat entier** du document interrogé.
Écrire la justification (ligne Commentaire) **avant** de cocher.

- **C1 Fidélité** : chaque affirmation sur le contrat est appuyée par son texte.
  Une connaissance générale est tolérée si elle est présentée comme une
  hypothèse ou un conseil, sanctionnée si elle est présentée comme le contenu
  du contrat. Un chiffre faux reste un défaut C1 même sous la bonne citation.
  Pas de « sans objet » pour C1.
- **C2 Citations** : chaque article cité existe et traite de l'information
  attribuée (rattachement, pas exactitude). Un renvoi présent dans le texte
  même du document est accepté (cas connu : « 6.3 », renvoi de l'art. 6.1 du
  contrat prévoyance). « sans objet » si aucun article n'est cité.
- **C3 Refus** : si l'information n'est pas dans le contrat, la réponse le dit
  clairement sans rien inventer. « sans objet » si l'information est dans le
  contrat.

## Comment cocher (lu automatiquement par `tests/judge/compare_juge_humain.py`)

- Pour chaque critère, remplacer **☐ par ☒** devant l'option choisie, et
  devant **une seule**. Exemple : `- **C1 Fidélité** : ☒ oui ☐ non`
- Écrire la justification à la suite de `- **Commentaire** :` (une ou
  plusieurs lignes, jusqu'au trait `---`), avant de cocher.
- Ne rien modifier d'autre : titres, réponses, ordre des fiches, libellés des
  options.
- Une fiche sans case cochée pour un critère est signalée « incomplète » ; plus
  d'une case cochée, ou une case autre que ☐ / ☒, est signalée « ambiguë ».
  Rien n'est deviné : la comparaison s'arrête tant qu'il en reste.
"""


def charger_reponses() -> list[dict]:
    run = json.loads(REFERENCE_RUN.read_text(encoding="utf-8"))
    reponses = []
    for r in run["resultats"]:
        for moteur in MOTEURS:
            m = r["moteurs"].get(moteur)
            reponses.append({
                # Code seul ("Q20") : le libellé complet ("Hors base (garde-fou)")
                # annoncerait le verdict attendu.
                "code": r["label"].split()[0],
                "question": r["question"],
                "doc": r["doc"],
                "moteur": moteur,
                "reponse": (m or {}).get("reponse") or "(pas de réponse enregistrée)",
            })
    return reponses


def melanger(reponses: list[dict]) -> list[dict]:
    ordre = list(reponses)
    random.Random(GRAINE).shuffle(ordre)
    return ordre


def citation(texte: str) -> str:
    """Réponse en bloc de citation markdown (même rendu que eval_upload_engines.render_markdown)."""
    return "> " + texte.replace("\n", "\n> ")


def fiche(numero: int, rep: dict) -> str:
    return "\n".join([
        f"## A{numero:02d} — {MOTEURS[rep['moteur']]} · {rep['code']}",
        "",
        f"- **Moteur** : {MOTEURS[rep['moteur']]}",
        f"- **Document** : {rep['doc']} — [contrat](contrats/{rep['doc']}.md)",
        f"- **Question** : {rep['question']}",
        "",
        "**Réponse :**",
        "",
        citation(rep["reponse"]),
        "",
        "- **C1 Fidélité** : ☐ oui ☐ non",
        "- **C2 Citations** : ☐ oui ☐ non ☐ sans objet",
        "- **C3 Refus** : ☐ oui ☐ non ☐ sans objet",
        "- **Commentaire** :",
        "",
        "---",
        "",
    ])


def render(reponses: list[dict]) -> str:
    docs = sorted({r["doc"] for r in reponses})
    liens = " · ".join(f"[{d}](contrats/{d}.md)" for d in docs)
    morceaux = [EN_TETE.format(graine=GRAINE, liens=liens)]
    morceaux += [fiche(i, rep) for i, rep in enumerate(melanger(reponses), 1)]
    return "\n".join(morceaux)


def deja_remplie(texte: str) -> bool:
    """Une case cochée ou un commentaire écrit : la fiche a commencé à être remplie."""
    fiches = texte.split("\n## A01 ", 1)[-1]  # l'en-tête cite ☒ et « Commentaire » dans la consigne
    if "☒" in fiches:
        return True
    return any(l.startswith("- **Commentaire** :") and l.split(":", 1)[1].strip() for l in fiches.splitlines())


def main() -> int:
    if SORTIE.exists() and deja_remplie(SORTIE.read_text(encoding="utf-8")):
        print(f"Refus : {SORTIE.name} est déjà en partie remplie ; elle n'est pas écrasée.")
        return 1
    SORTIE.write_text(render(charger_reponses()), encoding="utf-8")
    print(f"Fiche écrite : {SORTIE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
