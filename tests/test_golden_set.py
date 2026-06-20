"""
Test complet des 20 questions du golden set.
Q20 est le garde-fou critique : ne doit JAMAIS inventer une réponse.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent import run_agent

GOLDEN_SET = [
    # Bloc 1 — Prévoyance Invalidité
    {
        "id": "Q01", "bloc": "Prévoyance",
        "question": "Quelles sont les options de franchise disponibles sur le contrat prévoyance invalidité ?",
        "source_attendue": "Article 4.1 — CG-PREV-INV-2024",
        "mots_cles": ["franchise", "15", "30", "60", "90"],
        "hallucination_type": "franchise fixe inventée",
    },
    {
        "id": "Q02", "bloc": "Prévoyance",
        "question": "Quel est le montant maximum d'indemnité journalière pour quelqu'un qui gagne 80 000 € par an ?",
        "source_attendue": "Article 4.2 — CG-PREV-INV-2024",
        "mots_cles": ["220", "295", "60 001", "100 000"],
        "hallucination_type": "montant hors tableau ou confusion Standard/Premium",
    },
    {
        "id": "Q03", "bloc": "Prévoyance",
        "question": "Combien de temps peut-on être indemnisé en arrêt de travail avant de basculer en invalidité ?",
        "source_attendue": "Article 4.3 — CG-PREV-INV-2024",
        "mots_cles": ["1 095", "3 ans"],
        "hallucination_type": "durée légale Sécu (3 ans ≠ 1 095 jours)",
    },
    {
        "id": "Q04", "bloc": "Prévoyance",
        "question": "À partir de quel taux d'invalidité est-on reconnu en Invalidité Permanente Totale ?",
        "source_attendue": "Article 6 — CG-PREV-INV-2024",
        "mots_cles": ["66%", "66"],
        "hallucination_type": "confusion IPT/IPP ou taux Sécu",
    },
    {
        "id": "Q05", "bloc": "Prévoyance",
        "question": "Le burn-out est-il couvert par le contrat prévoyance invalidité ?",
        "source_attendue": "Articles 13 et 13.5 — CG-PREV-INV-2024",
        "mots_cles": ["Premium", "psychiatrique"],
        "hallucination_type": "répondre non couvert sans distinction Standard/Premium",
    },
    {
        "id": "Q06", "bloc": "Prévoyance",
        "question": "Si un assuré reprend le travail pendant 3 semaines puis retombe en arrêt, doit-il resubir une franchise ?",
        "source_attendue": "Article 4.1 — CG-PREV-INV-2024",
        "mots_cles": ["30 jours", "continuité", "nouvelle franchise"],
        "hallucination_type": "dire 'oui, nouvelle franchise systématique'",
    },
    # Bloc 2 — Assurance Vie
    {
        "id": "Q07", "bloc": "Assurance Vie",
        "question": "Quelle est la fiscalité d'un rachat partiel sur une assurance vie ouverte il y a 10 ans ?",
        "source_attendue": "Article 23 — CG-AV-MULTI-2024",
        "mots_cles": ["7,5%", "8 ans", "abattement", "prélèvements sociaux"],
        "hallucination_type": "taux incorrect ou oublier les prélèvements sociaux",
    },
    {
        "id": "Q08", "bloc": "Assurance Vie",
        "question": "Quel est le montant minimum pour un versement complémentaire sur ARESIA Patrimoine+ ?",
        "source_attendue": "Article 8 — CG-AV-MULTI-2024",
        "mots_cles": ["300"],
        "hallucination_type": "donner 1 000 € (versement initial) au lieu de 300 €",
    },
    {
        "id": "Q09", "bloc": "Assurance Vie",
        "question": "Peut-on faire une avance sur son contrat d'assurance vie et jusqu'à quel montant ?",
        "source_attendue": "Article 15 — CG-AV-MULTI-2024",
        "mots_cles": ["80%", "60%", "1 500"],
        "hallucination_type": "confondre avance et rachat partiel",
    },
    {
        "id": "Q10", "bloc": "Assurance Vie",
        "question": "Le fonds en euros ARESIA Sécurité garantit-il le capital investi ?",
        "source_attendue": "Article 10 — CG-AV-MULTI-2024",
        "mots_cles": ["100%", "frais sur versements", "net"],
        "hallucination_type": "garantie absolue sans mentionner les frais sur versements",
    },
    {
        "id": "Q11", "bloc": "Assurance Vie",
        "question": "Un conjoint bénéficiaire d'une assurance vie est-il exonéré de droits de succession ?",
        "source_attendue": "Article 24.2 — CG-AV-MULTI-2024",
        "mots_cles": ["exonéré", "conjoint", "PACS"],
        "hallucination_type": "appliquer les règles du droit successoral ordinaire",
    },
    {
        "id": "Q12", "bloc": "Assurance Vie",
        "question": "Combien coûte un arbitrage entre supports sur ARESIA Patrimoine+ ?",
        "source_attendue": "Article 9 — CG-AV-MULTI-2024",
        "mots_cles": ["0,50%", "gratuit", "4"],
        "hallucination_type": "dire arbitrages gratuits sans mentionner la condition 4/an",
    },
    # Bloc 3 — IARD
    {
        "id": "Q13", "bloc": "IARD",
        "question": "Quelle est la franchise en cas de bris de pare-brise avec un réparateur agréé ?",
        "source_attendue": "Article 2.3 — BAR-IARD-2024-V2",
        "mots_cles": ["0", "agréé", "75"],
        "hallucination_type": "donner franchise sans distinguer agréé/non agréé",
    },
    {
        "id": "Q14", "bloc": "IARD",
        "question": "Quel est le plafond de RC Professionnelle pour un conseiller en gestion de patrimoine ?",
        "source_attendue": "Article 3.1 — BAR-IARD-2024-V2",
        "mots_cles": ["1 500 000", "3 000 000", "CGP"],
        "hallucination_type": "plafond d'une autre catégorie professionnelle",
    },
    {
        "id": "Q15", "bloc": "IARD",
        "question": "Dans quel délai doit-on déclarer un cambriolage à son assureur ?",
        "source_attendue": "Article 4.1 — BAR-IARD-2024-V2",
        "mots_cles": ["48 heures", "plainte"],
        "hallucination_type": "délai général 5 jours sans dépôt de plainte obligatoire",
    },
    {
        "id": "Q16", "bloc": "IARD",
        "question": "La multirisque habitation couvre-t-elle le vol d'espèces au domicile et jusqu'à quel montant ?",
        "source_attendue": "Article 1.1 — BAR-IARD-2024-V2",
        "mots_cles": ["5 000", "espèces"],
        "hallucination_type": "dire oui sans préciser le plafond de 5 000 €",
    },
    # Bloc 4 — ACPR
    {
        "id": "Q17", "bloc": "ACPR",
        "question": "Quels éléments doit obligatoirement contenir le Document de Recueil des Informations et des Besoins ?",
        "source_attendue": "Article 4 — ACPR-REC-2024-12",
        "mots_cles": ["identité", "besoins", "recommandation", "signature"],
        "hallucination_type": "liste incomplète ou exigences inventées",
    },
    {
        "id": "Q18", "bloc": "ACPR",
        "question": "Pendant combien de temps dois-je conserver le DRIB et le journal des interactions de conseil ?",
        "source_attendue": "Article 6 — ACPR-REC-2024-12",
        "mots_cles": ["5 ans", "durée contrat"],
        "hallucination_type": "durée légale 3 ans au lieu de durée contrat + 5 ans",
    },
    {
        "id": "Q19", "bloc": "ACPR",
        "question": "Combien d'heures de formation continue un conseiller doit-il suivre par an au titre de la DDA ?",
        "source_attendue": "Article 7 — ACPR-REC-2024-12",
        "mots_cles": ["15 heures", "15"],
        "hallucination_type": "nombre incorrect ou oublier les domaines obligatoires",
    },
    # Bloc 5 — Hors base documentaire (GARDE-FOU CRITIQUE)
    {
        "id": "Q20", "bloc": "Hors base",
        "question": "Quelle est la garantie obsèques incluse dans le contrat prévoyance ?",
        "source_attendue": "AUCUNE",
        "mots_cles": ["ne trouve pas", "recommande de contacter"],
        "hallucination_type": "INVENTER une garantie obsèques",
        "critique": True,
    },
]


def score_reponse(reponse: str, test: dict) -> dict:
    """Évalue la réponse sur 3 critères simples."""
    reponse_lower = reponse.lower()

    # Exactitude : mots-clés attendus présents
    mots_trouves = [m for m in test["mots_cles"] if m.lower() in reponse_lower]
    exactitude = len(mots_trouves) / len(test["mots_cles"]) if test["mots_cles"] else 0

    # Hallucination détectée
    if test.get("critique"):  # Q20
        # Doit contenir la phrase de non-trouvé
        pas_invente = "ne trouve pas" in reponse_lower or "recommande de contacter" in reponse_lower
        hallucination = not pas_invente
    else:
        hallucination = False  # on ne peut pas détecter automatiquement sans ground truth

    return {
        "mots_trouves": mots_trouves,
        "mots_attendus": test["mots_cles"],
        "exactitude": exactitude,
        "hallucination": hallucination,
    }


def run_all_tests(output_json: str | None = None):
    print("=" * 60)
    print("TEST GOLDEN SET — 20 QUESTIONS")
    print("=" * 60)

    resultats = []
    scores = []
    total_start = time.time()

    for i, test in enumerate(GOLDEN_SET):
        print(f"\n[{test['id']}] {test['bloc']} — {test['question'][:60]}...")
        start = time.time()

        try:
            state = run_agent(test["question"])
            reponse = state["reponse_finale"]
            trace = state["trace_log"]
            elapsed = time.time() - start

            eval_result = score_reponse(reponse, test)

            # Affichage console
            mots_ok = len(eval_result["mots_trouves"])
            mots_total = len(eval_result["mots_attendus"])
            exactitude_pct = int(eval_result["exactitude"] * 100)

            if test.get("critique"):
                if eval_result["hallucination"]:
                    status = "❌ HALLUCINATION (BLOQUANT)"
                else:
                    status = "✅ NON-TROUVÉ CORRECT"
            else:
                status = f"✅ {exactitude_pct}%" if exactitude_pct >= 50 else f"⚠️  {exactitude_pct}%"

            print(f"  {status}  ({elapsed:.1f}s)")
            print(f"  Mots-clés : {mots_ok}/{mots_total} {eval_result['mots_trouves']}")

            # Résumé de la trace
            etapes = [e["etape"] for e in trace]
            print(f"  Trace : {' → '.join(etapes)}")

            # Afficher un extrait de la réponse
            extrait = reponse[:150].replace("\n", " ")
            print(f"  Réponse : {extrait}...")

            resultats.append({
                "id": test["id"],
                "bloc": test["bloc"],
                "question": test["question"],
                "source_attendue": test["source_attendue"],
                "reponse": reponse,
                "trace_log": trace,
                "score": eval_result,
                "status": status,
                "elapsed_s": round(elapsed, 1),
            })
            scores.append(eval_result)

        except Exception as e:
            print(f"  ❌ ERREUR : {e}")
            resultats.append({
                "id": test["id"],
                "erreur": str(e),
                "score": {"exactitude": 0, "hallucination": True},
            })
            scores.append({"exactitude": 0, "hallucination": True})

        # Pause courte pour éviter le rate limiting
        if i < len(GOLDEN_SET) - 1:
            time.sleep(1)

    total_elapsed = time.time() - total_start

    # Résumé final
    print("\n" + "=" * 60)
    print("RÉSUMÉ")
    print("=" * 60)

    q20 = next(r for r in resultats if r["id"] == "Q20")
    q20_ok = not q20.get("score", {}).get("hallucination", True)

    print(f"\n🔴 Q20 (garde-fou critique) : {'✅ PASS — pas d\'invention' if q20_ok else '❌ FAIL — hallucination détectée'}")

    exactitudes = [s["exactitude"] for s in scores if "exactitude" in s]
    moy = sum(exactitudes) / len(exactitudes) if exactitudes else 0
    print(f"\n📊 Score moyen mots-clés : {moy:.0%}")
    print(f"⏱️  Durée totale : {total_elapsed:.0f}s ({total_elapsed/len(GOLDEN_SET):.1f}s/question)")

    print("\nDétail par question :")
    for r in resultats:
        sc = r.get("score", {})
        pct = int(sc.get("exactitude", 0) * 100)
        halluc = "🔥HALLUC" if sc.get("hallucination") else ""
        print(f"  {r['id']}  {pct:3d}%  {halluc}")

    if output_json:
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(resultats, f, ensure_ascii=False, indent=2)
        print(f"\nRésultats sauvegardés : {output_json}")

    return resultats


if __name__ == "__main__":
    out = Path(__file__).parent.parent / "data" / "test_results.json"
    run_all_tests(output_json=str(out))
