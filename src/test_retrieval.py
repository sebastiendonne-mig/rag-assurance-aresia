"""
Test de retrieval pur (sans LLM) sur le golden set : rang de l'article attendu
dans le top-10, scores top-1 / top-3 / top-10, distances cosine du top-1.
Même format de mesure que la référence e5 du 03/10/2026
(tests/results/baseline_e5_retrieval_20261003.txt).

Encodage des questions : agent.embed_texts (API Mistral, sans préfixe), avec
un cache local des vecteurs dans tests/results/ (non versionné) : un nouveau
lancement n'appelle l'API que pour les questions absentes du cache.
Aucun appel Anthropic. Interroge la collection locale chroma_db/, qui doit
avoir été construite avec le même modèle (python src/index_chroma.py).

Usage : python src/test_retrieval.py
"""
import hashlib
import json
import statistics
import sys
from pathlib import Path

import chromadb

ROOT = Path(__file__).parent.parent
CHROMA_PATH = ROOT / "chroma_db"
COLLECTION_NAME = "assur_docs"
CACHE_PATH = ROOT / "tests" / "results" / "retrieval_query_cache.json"
K = 10

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


def _cle_cache(modele: str, question: str) -> str:
    return hashlib.sha256(f"{modele}\n{question}".encode("utf-8")).hexdigest()


def _vecteurs_questions(modele: str, questions: list[str]) -> list[list[float]]:
    """Vecteurs des questions, depuis le cache local ou, à défaut, via embed_texts (un seul appel groupé)."""
    from agent import embed_texts

    cache = json.loads(CACHE_PATH.read_text(encoding="utf-8")) if CACHE_PATH.exists() else {}
    manquantes = [q for q in questions if _cle_cache(modele, q) not in cache]
    if manquantes:
        print(f"Encodage de {len(manquantes)} question(s) via l'API ({modele})...")
        for q, v in zip(manquantes, embed_texts(manquantes)):
            cache[_cle_cache(modele, q)] = v
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
    else:
        print(f"Vecteurs des questions lus depuis le cache ({CACHE_PATH.name}), aucun appel API.")
    return [cache[_cle_cache(modele, q)] for q in questions]


def run_retrieval_tests(k: int = K) -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from agent import MODEL_NAME

    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    collection = client.get_collection(COLLECTION_NAME)
    modele_index = (collection.metadata or {}).get("model_name")
    print(f"Collection chargée : {collection.count()} chunks, modèle de l'index : {modele_index}")
    if modele_index != MODEL_NAME:
        # Comparer des vecteurs de deux modèles différents n'a aucun sens (même à dimension égale).
        sys.exit(
            f"ERREUR : l'index a été construit avec {modele_index!r}, les questions seraient encodées "
            f"avec {MODEL_NAME!r}. Reconstruisez l'index : python src/index_chroma.py"
        )

    vecteurs = _vecteurs_questions(MODEL_NAME, [t["question"] for t in TESTS])
    print()

    rangs: list[int | None] = []
    dist_top1: list[float] = []
    dist_q20 = None
    for test, vec in zip(TESTS, vecteurs):
        results = collection.query(query_embeddings=[vec], n_results=k, include=["metadatas", "distances"])
        metas, distances = results["metadatas"][0], results["distances"][0]

        if test["expected_article"] is None:
            dist_q20 = distances[0]
            print(f"{test['label']:<40} top1_dist={distances[0]:.4f} "
                  f"[{metas[0]['source_doc']} Art.{metas[0]['article_num']}]")
            continue

        rang = next(
            (i + 1 for i, m in enumerate(metas)
             if m["source_doc"] == test["expected_doc"] and m["article_num"] == test["expected_article"]),
            None,
        )
        rangs.append(rang)
        dist_top1.append(distances[0])
        cible = f" dist_cible={distances[rang - 1]:.4f}" if rang else ""
        print(f"{test['label']:<40} rang={rang if rang else f'>{k}'} top1_dist={distances[0]:.4f}{cible}")
        for r, (m, d) in enumerate(zip(metas[:3], distances[:3]), 1):
            flag = " ← CIBLE" if r == rang else ""
            print(f"     #{r} [{m['source_doc']}] Art.{m['article_num']}  dist={d:.4f}{flag}")

    n = len(rangs)
    print(f"\n{'=' * 50}")
    print(f"Modèle : {MODEL_NAME} — questions avec cible : {n}")
    for seuil in (1, 3, 5, 10):
        if seuil <= k:
            print(f"top-{seuil}: {sum(1 for r in rangs if r and r <= seuil)}/{n}")
    print(f"top-1 dist ({n} questions): min={min(dist_top1):.4f} "
          f"médiane={statistics.median(dist_top1):.4f} max={max(dist_top1):.4f}")
    if dist_q20 is not None:
        # Information seulement : aucun seuil de distance n'est calibré pour ce modèle
        # (avec e5, Q20 tombait dans la plage des questions valides).
        print(f"Q20 top-1 dist: {dist_q20:.4f}")


if __name__ == "__main__":
    run_retrieval_tests()
