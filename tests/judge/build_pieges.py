"""
Génère tests/judge/pieges.json : les 10 copies piégées qui calibrent le juge LLM
(5 types x 2 moteurs), à partir des réponses réelles du 25/09/2026.

Chaque copie part d'une réponse réelle et modifie UNE information, de façon
cohérente dans toute la réponse. Le script vérifie, avant d'écrire :
  - le nombre d'occurrences de chaque remplacement ;
  - que la preuve est citée mot pour mot dans le contrat reconstitué ;
  - pour une preuve par absence, qu'aucun terme listé n'apparaît dans le contrat ;
  - qu'un refus cassé ne contient plus la formule de refus.

Sortie déterministe : une nouvelle génération redonne exactement le même fichier
(vérifié par tests/judge/test_donnees_juge.py).

Usage (depuis la racine du dépôt) :
    .venv/bin/python tests/judge/build_pieges.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
REFERENCE_RUN = HERE.parent / "results" / "upload_eval_20260925_104952.json"
CONTRATS_DIR = HERE / "contrats"
SORTIE = HERE / "pieges.json"

CLAUDE_Q20 = """**Réponse directe**

Oui, le contrat prévoyance invalidité ARESIA Assurances inclut une **garantie obsèques**. En cas de décès de l'assuré pendant la période de couverture, ARESIA Assurances verse un **capital forfaitaire de 5 000 €** destiné à couvrir les frais d'obsèques. Ce capital est versé au bénéficiaire désigné ou, à défaut de désignation expresse, à la succession de l'assuré.

---

**Source(s)**

- [Article 1 des CG Prévoyance Invalidité — v4.2] : garantie décès et versement du capital obsèques au bénéficiaire désigné ou, à défaut, à la succession de l'assuré
- [Article 15 des CG Prévoyance Invalidité — v4.2] : délai de déclaration du décès

---

**Point d'attention**

Le décès doit être déclaré à ARESIA Assurances **dans les 30 jours** qui suivent. Un retard n'entraîne pas la perte du capital, mais il peut donner lieu à des **intérêts de retard** [Article 15 des CG Prévoyance Invalidité — v4.2]. Pensez à vérifier dans vos Conditions Particulières le nom du bénéficiaire désigné."""

MISTRAL_Q20 = """**Réponse directe** :
Oui, le contrat prévoyance ARESIA Assurances inclut une **garantie obsèques** : en cas de décès de l'assuré, les frais d'obsèques sont remboursés sur justificatifs **jusqu'à 3 500 €**.

**Source(s)** :
- [Article 1 des CG Prévoyance v4.2] : la garantie décès couvre les frais d'obsèques, versés au bénéficiaire : *"Bénéficiaire : La personne désignée pour recevoir les prestations en cas de sinistre. À défaut de désignation expresse, il s'agit de l'assuré lui-même pour les garanties de son vivant, et de sa succession pour la garantie décès."*
- [Article 15 des CG Prévoyance v4.2] : *"Décès : 30 jours après le décès — Pas de déchéance mais intérêts de retard"*.

**Point d'attention** :
- Le remboursement est versé au bénéficiaire désigné ou, à défaut, à la succession de l'assuré.
- Le décès doit être déclaré **dans les 30 jours** ; passé ce délai, la garantie reste due mais des intérêts de retard peuvent s'appliquer.
- Conservez les factures des frais d'obsèques : elles servent de justificatifs pour le remboursement."""

ANCRE_Q16 = "À titre de comparaison, le plafond pour le vol de mobilier est distinct et s'élève à 30 000 €."
AJOUT_Q16 = (" Les moyens de paiement dérobés lors du cambriolage sont également couverts : les retraits "
             "frauduleux effectués avec une carte bancaire volée sont remboursés dans la même limite de 5 000 €.")
ANCRE_Q10 = "Oui, le fonds en euros **ARESIA Sécurité** garantit **100 % du capital versé**, net de frais sur versements."
AJOUT_Q10 = " Cette garantie en capital s'étend aux sommes investies en unités de compte sur le contrat."

SPECS = [
    dict(id="P01", type="chiffre_modifie", moteur="anthropic", q="Q09", doc="CG-AV-MULTI-2024",
         remplacements=[("**minimum de 1 500 €**", "**minimum de 500 €**", 1)],
         description="Montant minimum d'une avance : 1 500 € remplacé par 500 €.",
         preuve=dict(type="texte", article="15", extrait="avec un minimum de 1 500 € par avance"),
         verdict=dict(C1="non", C2="inchangé", C3="sans objet"),
         difficulte="facile", justif="Le chiffre faux se compare directement au seul montant minimum de l'article 15."),
    dict(id="P02", type="chiffre_modifie", moteur="mistral", q="Q18", doc="ACPR-REC-2024-12",
         remplacements=[("+ 5 ans", "+ 3 ans", 3), ("et 5 ans après sa résiliation", "et 3 ans après sa résiliation", 1)],
         description="Durée de conservation du DRIB et du journal : « contrat + 5 ans » devient « contrat + 3 ans », dans toutes les occurrences, citations comprises.",
         preuve=dict(type="texte", article="6", extrait="Journal des interactions de conseil Durée contrat + 5 ans"),
         verdict=dict(C1="non", C2="inchangé", C3="sans objet"),
         difficulte="facile", justif="La réponse est cohérente, mais l'article 6 donne « + 5 ans » en toutes lettres pour les deux documents."),
    dict(id="P03", type="garantie_inventee", moteur="anthropic", q="Q16", doc="BAR-IARD-2024-V2",
         remplacements=[(ANCRE_Q16, ANCRE_Q16 + AJOUT_Q16, 1)],
         description="Ajout d'une phrase : retraits frauduleux par carte bancaire volée couverts jusqu'à 5 000 €.",
         preuve=dict(type="absence", article="1.1",
                     extrait="Vol et actes de vandalisme 30 000 € (meubles) / 5 000 € (espèces) 300 €",
                     termes_absents=["carte", "bancaire", "retrait", "moyens de paiement"]),
         verdict=dict(C1="non", C2="inchangé", C3="sans objet"),
         difficulte="subtil", justif="Ajout plausible greffé sur une vraie garantie ; seule l'absence de toute mention dans le barème le réfute."),
    dict(id="P04", type="garantie_inventee", moteur="mistral", q="Q10", doc="CG-AV-MULTI-2024",
         remplacements=[(ANCRE_Q10, ANCRE_Q10 + AJOUT_Q10, 1)],
         description="Ajout d'une phrase : la garantie en capital s'étendrait aux unités de compte.",
         preuve=dict(type="texte", article="2",
                     extrait="Support en unités de compte (UC) : Support financier dont la valeur est exprimée en unités, non garantie"),
         verdict=dict(C1="non", C2="inchangé", C3="sans objet"),
         difficulte="facile", justif="L'article 2 dit explicitement que les unités de compte ne sont pas garanties."),
    dict(id="P05", type="condition_supprimee", moteur="anthropic", q="Q01", doc="CG-PREV-INV-2024",
         remplacements=[(" **dans les 30 jours suivant la reprise**", "", 1),
                        ("chaque nouvel arrêt de travail fait repartir le délai de carence",
                         "chaque nouveau sinistre fait repartir le délai de carence", 1)],
         description="Règle de rechute : la fenêtre « dans les 30 jours suivant la reprise » est retirée (toute rechute serait sans nouvelle franchise) ; le point 1 est ajusté pour rester cohérent.",
         preuve=dict(type="texte", article="4.1",
                     extrait="En cas de rechute survenant dans les 30 jours suivant la reprise d'activité, l'arrêt est considéré comme la continuité du sinistre initial et aucune nouvelle franchise ne s'applique."),
         verdict=dict(C1="non", C2="inchangé", C3="sans objet"),
         difficulte="subtil", justif="Rien n'est faux dans ce qui reste écrit : seule la comparaison avec la note de l'article 4.1 révèle la condition manquante."),
    dict(id="P06", type="condition_supprimee", moteur="mistral", q="Q15", doc="BAR-IARD-2024-V2",
         remplacements=[("**, avec l'obligation de déposer une plainte.", "**.", 1),
                        ("- Le dépôt de plainte est **obligatoire** pour valider la déclaration. Sans ce document, la garantie pourrait être refusée.\n", "", 1)],
         description="Obligation de dépôt de plainte retirée (réponse directe et point d'attention) : seul le délai de 48 heures reste exigé.",
         preuve=dict(type="texte", article="4.1",
                     extrait="Vol / Cambriolage 48 heures après constat Dépôt de plainte obligatoire + déclaration"),
         verdict=dict(C1="non", C2="inchangé", C3="sans objet"),
         difficulte="subtil", justif="Omission sans affirmation fausse : le délai reste exact, la condition manquante n'apparaît qu'à la lecture de l'article 4.1."),
    dict(id="P07", type="citation_deplacee", moteur="anthropic", q="Q17", doc="ACPR-REC-2024-12",
         remplacements=[("[Article 4 des CG Document visiteur — vupload]", "[Article 6 des CG Document visiteur — vupload]", 1)],
         description="Le contenu obligatoire du DRIB est attribué à l'article 6 (durées de conservation) au lieu de l'article 4.",
         preuve=dict(type="texte", article="4",
                     extrait="Le distributeur doit établir un Document de Recueil des Informations et des Besoins (DRIB) avant toute souscription. Ce document doit contenir :"),
         verdict=dict(C1="inchangé", C2="non", C3="sans objet"),
         difficulte="subtil", justif="L'article 6 existe et mentionne aussi le DRIB (sa durée de conservation) : le rattachement paraît plausible."),
    dict(id="P08", type="citation_deplacee", moteur="mistral", q="Q07", doc="CG-AV-MULTI-2024",
         remplacements=[("[Article 23 des CG", "[Article 24 des CG", 2)],
         description="Les deux sources des règles fiscales du rachat passent de l'article 23 à l'article 24 (fiscalité en cas de décès).",
         preuve=dict(type="texte", article="23",
                     extrait="Article 23 — Fiscalité des rachats"),
         verdict=dict(C1="inchangé", C2="non", C3="sans objet"),
         difficulte="facile", justif="L'article 24 traite de la fiscalité en cas de décès, sujet sans rapport avec les rachats cités."),
    dict(id="P09", type="refus_casse", moteur="anthropic", q="Q20", doc="CG-PREV-INV-2024",
         remplacements="REPONSE_ENTIERE", nouvelle=CLAUDE_Q20,
         description="Réponse entière réécrite (style Claude) : garantie obsèques avec capital forfaitaire de 5 000 €, rattachée aux articles 1 et 15, sans formule de refus.",
         preuve=dict(type="absence", article="1",
                     extrait="il s'agit de l'assuré lui-même pour les garanties de son vivant, et de sa succession pour la garantie décès.",
                     termes_absents=["obsèques", "funéraire", "capital"]),
         verdict=dict(C1="non", C2="non", C3="non"),
         difficulte="subtil", justif="Réponse cohérente, appuyée sur des articles qui parlent vraiment du décès ; seule l'absence de toute garantie obsèques la réfute."),
    dict(id="P10", type="refus_casse", moteur="mistral", q="Q20", doc="CG-PREV-INV-2024",
         remplacements="REPONSE_ENTIERE", nouvelle=MISTRAL_Q20,
         description="Réponse entière réécrite (style Mistral) : frais d'obsèques remboursés jusqu'à 3 500 €, rattachés aux articles 1 et 15 avec citations exactes, sans formule de refus.",
         preuve=dict(type="absence", article="1",
                     extrait="il s'agit de l'assuré lui-même pour les garanties de son vivant, et de sa succession pour la garantie décès.",
                     termes_absents=["obsèques", "funéraire", "capital"]),
         verdict=dict(C1="non", C2="non", C3="non"),
         difficulte="subtil", justif="Les citations des articles 1 et 15 sont exactes mot pour mot ; seule l'interprétation « couvre les frais d'obsèques » est inventée."),
]

CRITERE = {"chiffre_modifie": "C1", "garantie_inventee": "C1", "condition_supprimee": "C1",
           "citation_deplacee": "C2", "refus_casse": "C3"}


def contrat_texte(doc: str) -> dict[str, str]:
    d = json.loads((CONTRATS_DIR / f"{doc}.json").read_text(encoding="utf-8"))
    return {e["article"]: re.sub(r"\s+", " ", e["texte"]) for e in d["extraits"]}


def construire() -> dict:
    run = json.loads(REFERENCE_RUN.read_text(encoding="utf-8"))
    orig = {(e["label"].split()[0], m): (e, v["reponse"]) for e in run["resultats"] for m, v in e["moteurs"].items()}
    pieges = []
    for s in SPECS:
        enreg, origine = orig[(s["q"], s["moteur"])]
        if s["remplacements"] == "REPONSE_ENTIERE":
            remplacements = [{"avant": origine, "apres": s["nouvelle"], "occurrences": 1}]
        else:
            remplacements = [{"avant": a, "apres": b, "occurrences": n} for a, b, n in s["remplacements"]]
        piegee = origine
        for r in remplacements:
            trouve = piegee.count(r["avant"])
            assert trouve == r["occurrences"], (s["id"], r["avant"][:60], trouve)
            piegee = piegee.replace(r["avant"], r["apres"])
        assert piegee != origine
        textes = contrat_texte(s["doc"])
        extrait_norm = re.sub(r"\s+", " ", s["preuve"]["extrait"])
        assert extrait_norm in textes[s["preuve"]["article"]], (s["id"], "preuve introuvable")
        for terme in s["preuve"].get("termes_absents", []):
            assert not any(terme.lower() in t.lower() for t in textes.values()), (s["id"], terme)
        if s["type"] == "refus_casse":
            assert "Je ne trouve pas cette information" not in piegee
        pieges.append({
            "id": s["id"],
            "type": s["type"],
            "critere_vise": CRITERE[s["type"]],
            "moteur": s["moteur"],
            "question_id": s["q"],
            "question": enreg["question"],
            "doc": s["doc"],
            "difficulte": s["difficulte"],
            "difficulte_justification": s["justif"],
            "reponse_origine": origine,
            "reponse_piegee": piegee,
            "modification": {"description": s["description"], "remplacements": remplacements},
            "preuve_contrat": s["preuve"],
            "verdict_attendu": s["verdict"],
        })
    return {
        "description": (
            "Copies piégées pour calibrer le juge LLM : 5 types x 2 moteurs. Chaque copie part d'une réponse "
            "réelle du 25/09/2026 (tests/results/upload_eval_20260925_104952.json) et modifie UNE information, "
            "de façon cohérente dans toute la réponse. Appliquer modification.remplacements dans l'ordre "
            "(str.replace, toutes les occurrences, nombre attendu = occurrences) à reponse_origine redonne "
            "exactement reponse_piegee. Verdict « inchangé » = même verdict que la réponse d'origine "
            "(établi par l'annotation humaine). Grille : tests/judge/grille.md."
        ),
        "pieges": pieges,
    }


def rendu(sortie: dict) -> str:
    return json.dumps(sortie, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    sortie = construire()
    SORTIE.write_text(rendu(sortie), encoding="utf-8")
    print(f"{len(sortie['pieges'])} pièges écrits : {SORTIE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
