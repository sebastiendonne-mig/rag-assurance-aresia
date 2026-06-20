"""
Test de retrieval pur (sans LLM) sur un sous-ensemble du golden set.
Valide que le bon article est en top-3 pour chaque question.
Convention e5 : requêtes préfixées "query: "
"""
from pathlib import Path
import chromadb
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).parent.parent
CHROMA_PATH = ROOT / "chroma_db"
COLLECTION_NAME = "assur_docs"
MODEL_NAME = "intfloat/multilingual-e5-large"

TESTS = [
    {
        "question": "Quelles sont les options de franchise disponibles sur le contrat prévoyance invalidité ?",
        "expected_article": "4.1",
        "expected_doc": "CG-PREV-INV-2024",
        "label": "Q01 — Franchise ITT",
    },
    {
        "question": "Quel est le montant maximum d'indemnité journalière pour quelqu'un qui gagne 80 000 € par an ?",
        "expected_article": "4.2",
        "expected_doc": "CG-PREV-INV-2024",
        "label": "Q02 — Montant IJ",
    },
    {
        "question": "Combien de temps peut-on être indemnisé en arrêt de travail avant de basculer en invalidité ?",
        "expected_article": "4.3",
        "expected_doc": "CG-PREV-INV-2024",
        "label": "Q03 — Durée ITT",
    },
    {
        "question": "À partir de quel taux d'invalidité est-on reconnu en Invalidité Permanente Totale ?",
        "expected_article": "6",
        "expected_doc": "CG-PREV-INV-2024",
        "label": "Q04 — Conditions IPT",
    },
    {
        "question": "Le burn-out est-il couvert par le contrat prévoyance invalidité ?",
        "expected_article": "13",
        "expected_doc": "CG-PREV-INV-2024",
        "label": "Q05 — Exclusions burn-out",
    },
    {
        "question": "Si un assuré reprend le travail pendant 3 semaines puis retombe en arrêt, doit-il resubir une franchise ?",
        "expected_article": "4.1",
        "expected_doc": "CG-PREV-INV-2024",
        "label": "Q06 — Rechute ITT",
    },
    {
        "question": "Quelle est la fiscalité d'un rachat partiel sur une assurance vie ouverte il y a 10 ans ?",
        "expected_article": "23",
        "expected_doc": "CG-AV-MULTI-2024",
        "label": "Q07 — Fiscalité rachat AV",
    },
    {
        "question": "Quel est le montant minimum pour un versement complémentaire sur ARESIA Patrimoine+ ?",
        "expected_article": "8",
        "expected_doc": "CG-AV-MULTI-2024",
        "label": "Q08 — Versement minimum",
    },
    {
        "question": "Peut-on faire une avance sur son contrat d'assurance vie et jusqu'à quel montant ?",
        "expected_article": "15",
        "expected_doc": "CG-AV-MULTI-2024",
        "label": "Q09 — Avance contrat AV",
    },
    {
        "question": "Le fonds en euros ARESIA Sécurité garantit-il le capital investi ?",
        "expected_article": "10",
        "expected_doc": "CG-AV-MULTI-2024",
        "label": "Q10 — Garantie fonds euros",
    },
    {
        "question": "Un conjoint bénéficiaire d'une assurance vie est-il exonéré de droits de succession ?",
        "expected_article": "24",
        "expected_doc": "CG-AV-MULTI-2024",
        "label": "Q11 — Fiscalité décès conjoint",
    },
    {
        "question": "Combien coûte un arbitrage entre supports sur ARESIA Patrimoine+ ?",
        "expected_article": "9",
        "expected_doc": "CG-AV-MULTI-2024",
        "label": "Q12 — Frais arbitrage",
    },
    {
        "question": "Quelle est la franchise en cas de bris de pare-brise avec un réparateur agréé ?",
        "expected_article": "2.3",
        "expected_doc": "BAR-IARD-2024-V2",
        "label": "Q13 — Franchise bris de glace",
    },
    {
        "question": "Quel est le plafond de RC Professionnelle pour un conseiller en gestion de patrimoine ?",
        "expected_article": "3.1",
        "expected_doc": "BAR-IARD-2024-V2",
        "label": "Q14 — RC Pro CGP",
    },
    {
        "question": "Dans quel délai doit-on déclarer un cambriolage à son assureur ?",
        "expected_article": "4.1",
        "expected_doc": "BAR-IARD-2024-V2",
        "label": "Q15 — Délai déclaration vol",
    },
    {
        "question": "La multirisque habitation couvre-t-elle le vol d'espèces au domicile et jusqu'à quel montant ?",
        "expected_article": "1.1",
        "expected_doc": "BAR-IARD-2024-V2",
        "label": "Q16 — MRH vol espèces",
    },
    {
        "question": "Quels éléments doit obligatoirement contenir le Document de Recueil des Informations et des Besoins ?",
        "expected_article": "4",
        "expected_doc": "ACPR-REC-2024-12",
        "label": "Q17 — Contenu DRIB",
    },
    {
        "question": "Pendant combien de temps dois-je conserver le DRIB et le journal des interactions de conseil ?",
        "expected_article": "6",
        "expected_doc": "ACPR-REC-2024-12",
        "label": "Q18 — Conservation documents",
    },
    {
        "question": "Combien d'heures de formation continue un conseiller doit-il suivre par an au titre de la DDA ?",
        "expected_article": "7",
        "expected_doc": "ACPR-REC-2024-12",
        "label": "Q19 — Formation DDA",
    },
    {
        "question": "Quelle est la garantie obsèques incluse dans le contrat prévoyance ?",
        "expected_article": None,  # N'existe pas — doit ne rien trouver de pertinent
        "expected_doc": None,
        "label": "Q20 — Hors base (garde-fou)",
    },
]


def run_retrieval_tests(k: int = 5):
    print(f"Chargement modèle {MODEL_NAME}...")
    model = SentenceTransformer(MODEL_NAME)

    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    collection = client.get_collection(COLLECTION_NAME)
    print(f"Collection chargée : {collection.count()} chunks\n")

    passed = 0
    total_non_q20 = len([t for t in TESTS if t["expected_article"] is not None])

    for test in TESTS:
        query_text = "query: " + test["question"]
        embedding = model.encode([query_text], normalize_embeddings=True).tolist()

        results = collection.query(
            query_embeddings=embedding,
            n_results=k,
            include=["metadatas", "distances", "documents"],
        )

        metas = results["metadatas"][0]
        distances = results["distances"][0]

        if test["expected_article"] is None:
            # Q20 : vérifier que le score du top-1 est bas (> 0.3 = peu similaire en cosine)
            top_dist = distances[0]
            # distance cosine : 0 = identique, 2 = opposé — on veut > 0.5 pour "non trouvé"
            ok = top_dist > 0.35
            marker = "✅" if ok else "⚠️ "
            print(f"{marker} {test['label']}")
            print(f"     Top-1 distance={top_dist:.3f} [{metas[0]['source_doc']} Art.{metas[0]['article_num']}]")
            print(f"     {'→ Aucun doc pertinent (bon)' if ok else '→ ATTENTION: un doc proche trouvé'}")
        else:
            # Chercher si l'article attendu est dans le top-k
            top_k_found = [
                (m["source_doc"], m["article_num"], d)
                for m, d in zip(metas, distances)
            ]
            hit = next(
                (i + 1 for i, (src, art, _) in enumerate(top_k_found)
                 if src == test["expected_doc"] and art == test["expected_article"]),
                None,
            )
            ok = hit is not None
            if ok:
                passed += 1
            marker = "✅" if ok else "❌"
            rank_str = f"rank {hit}" if ok else "non trouvé dans top-5"
            print(f"{marker} {test['label']}")
            for rank, (src, art, dist) in enumerate(top_k_found[:3], 1):
                flag = " ← CIBLE" if (src == test["expected_doc"] and art == test["expected_article"]) else ""
                print(f"     #{rank} [{src}] Art.{art}  dist={dist:.3f}{flag}")

        print()

    print(f"{'='*50}")
    print(f"Score retrieval : {passed}/{total_non_q20} articles cibles en top-{k}")


if __name__ == "__main__":
    run_retrieval_tests(k=5)
