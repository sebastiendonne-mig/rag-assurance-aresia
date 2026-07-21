"""
Évaluation END-TO-END du golden set : les 20 questions passent par l'agent complet
(run_agent), pas seulement par le retrieval.

Placement : tests/test_golden_set.py (à côté de test_retrieval.py)
Usage :
    uv run python tests/test_golden_set.py              # les 20 questions
    uv run python tests/test_golden_set.py --only Q20   # une seule question
    uv run python tests/test_golden_set.py --limit 3    # les 3 premières

Sortie :
    - Résumé console par question (verdict, chemin router, reformulations, durée)
    - JSON complet : tests/results/golden_set_results_<timestamp>.json
      (réponse finale + trace_log intégral par question → matière pour la Session 4)

Coût : ~5-8 appels claude-sonnet-4-6 par question. Vérifier le coût réel
sur console.anthropic.com après le premier run complet.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

import agent  # noqa: E402  (src/agent.py)
from agent import run_agent  # noqa: E402
from test_retrieval import TESTS  # noqa: E402  (réutilise le golden set existant)

# Phrase exacte exigée par la règle 3 du prompt système
NON_TROUVE = "Je ne trouve pas cette information"

# Blocs exigés par la règle 5 du prompt système
BLOCS = ["Réponse directe", "Source(s)", "Point d'attention"]


def analyse_trace(trace: list[dict]) -> dict:
    """Extrait les décisions clés du trace_log pour le résumé."""
    router_entry = next((e for e in trace if e["etape"] == "router"), None)
    reformulations = [e for e in trace if e["etape"] == "reformulate"]
    evaluations = [e for e in trace if e["etape"] == "evaluate"]
    planner_entry = next((e for e in trace if e["etape"] == "planner"), None)
    return {
        "chemin_router": router_entry["decision"] if router_entry else "?",
        "raison_router": router_entry.get("raison", "") if router_entry else "",
        "nb_sous_questions": (
            int(planner_entry["decision"].split()[0]) if planner_entry else 1
        ),
        "nb_reformulations": len(reformulations),
        "methodes_reformulation": [r["decision"] for r in reformulations],
        "decisions_evaluate": [e["decision"] for e in evaluations],
    }


def verdict(test: dict, reponse: str) -> tuple[bool, str]:
    """
    Verdict automatique (volontairement simple — la revue humaine reste nécessaire) :
    - Q20 (hors base) : la phrase exacte "non trouvé" doit apparaître.
    - Questions normales : l'article attendu doit être cité dans la réponse.
    """
    if test["expected_article"] is None:
        ok = NON_TROUVE in reponse
        detail = "phrase 'non trouvé' présente" if ok else "ÉCHEC BLOQUANT : pas de refus, risque d'invention"
        return ok, detail

    cible = f"Article {test['expected_article']}"
    cite = cible in reponse
    refus = NON_TROUVE in reponse
    if cite:
        return True, f"'{cible}' cité"
    if refus:
        return False, f"'{cible}' non cité — l'agent a répondu 'non trouvé' (faux négatif)"
    return False, f"'{cible}' non cité — vérifier quelle source a été utilisée"


def check_format(reponse: str) -> list[str]:
    """Vérifie la présence des 3 blocs obligatoires."""
    return [b for b in BLOCS if b not in reponse]


def run(tests: list[dict]) -> None:
    results = []
    t_global = time.time()

    for i, test in enumerate(tests, 1):
        label = test["label"]
        question = test["question"]
        print(f"\n{'=' * 70}\n[{i}/{len(tests)}] {label}\n  Q : {question}")

        entry = {
            "label": label,
            "question": question,
            "expected_doc": test["expected_doc"],
            "expected_article": test["expected_article"],
        }

        t0 = time.time()
        try:
            state = run_agent(question)
            duree = time.time() - t0
            reponse = state["reponse_finale"]
            trace = state["trace_log"]

            ok, detail = verdict(test, reponse)
            blocs_manquants = check_format(reponse)
            resume_trace = analyse_trace(trace)

            entry.update({
                "ok": ok,
                "detail": detail,
                "blocs_manquants": blocs_manquants,
                "duree_s": round(duree, 1),
                "nb_appels_llm": agent._turn_llm_seq,
                "trace_resume": resume_trace,
                "reponse_finale": reponse,
                "trace_log": trace,
            })

            marker = "✅" if ok else "❌"
            print(f"  {marker} {detail}")
            print(
                f"     router={resume_trace['chemin_router']}"
                f" | sous-questions={resume_trace['nb_sous_questions']}"
                f" | reformulations={resume_trace['nb_reformulations']}"
                f" {resume_trace['methodes_reformulation'] or ''}"
            )
            if blocs_manquants:
                print(f"     ⚠️  Blocs manquants dans la réponse : {blocs_manquants}")
            print(f"     {duree:.1f}s | {agent._turn_llm_seq} appels LLM")

        except Exception as exc:
            duree = time.time() - t0
            entry.update({
                "ok": False,
                "detail": f"EXCEPTION : {exc}",
                "duree_s": round(duree, 1),
                "traceback": traceback.format_exc(),
            })
            print(f"  💥 EXCEPTION après {duree:.1f}s : {exc}")

        results.append(entry)

    # ── Résumé global ────────────────────────────────────────────────
    duree_totale = time.time() - t_global
    notes = [r for r in results if r["expected_article"] is not None]
    passed = sum(1 for r in notes if r.get("ok"))
    q20 = next((r for r in results if r["expected_article"] is None), None)

    print(f"\n{'=' * 70}")
    print(f"SCORE END-TO-END : {passed}/{len(notes)} questions avec l'article attendu cité")
    if q20 is not None:
        statut_q20 = "✅ refus correct" if q20.get("ok") else "❌ ÉCHEC BLOQUANT"
        print(f"Q20 (garde-fou anti-hallucination) : {statut_q20}")
    format_ko = [r["label"] for r in results if r.get("blocs_manquants")]
    if format_ko:
        print(f"⚠️  Format 3 blocs incomplet sur : {format_ko}")
    print(f"Durée totale : {duree_totale:.0f}s")

    # ── Sauvegarde JSON ──────────────────────────────────────────────
    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"golden_set_results_{stamp}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "date": stamp,
                "modele": agent.CLAUDE_MODEL,
                "retrieval_k": agent.RETRIEVAL_K,
                "score": f"{passed}/{len(notes)}",
                "q20_ok": bool(q20 and q20.get("ok")),
                "duree_totale_s": round(duree_totale, 1),
                "resultats": results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\nRésultats complets : {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Golden set end-to-end via l'agent")
    parser.add_argument("--limit", type=int, default=None, help="ne lancer que les N premières questions")
    parser.add_argument("--only", type=str, default=None, help="ne lancer qu'une question, ex: --only Q20")
    args = parser.parse_args()

    tests = TESTS
    if args.only:
        tests = [t for t in TESTS if t["label"].startswith(args.only)]
        if not tests:
            sys.exit(f"Aucune question ne correspond à '{args.only}'")
    if args.limit:
        tests = tests[: args.limit]

    print(f"=== Golden set end-to-end — {len(tests)} question(s), modèle {agent.CLAUDE_MODEL} ===")
    run(tests)
