"""
Reconstitue le CONTRAT ENTIER de chacun des 4 PDF du corpus, tel que le chemin
upload le découpe, pour le juge LLM hors ligne (lot B).

Pourquoi le contrat entier : les extraits réellement récupérés le 25/09/2026
(évaluation du sous-lot 3.2) n'ont pas été sauvegardés. Le juge compare donc
chaque réponse à tous les extraits du document interrogé.

Même découpage que le chemin upload : upload_session.extract_and_chunk_pdf()
puis apply_length_guard(). AUCUN appel API : ni embedding, ni Chroma, ni LLM.
load_dotenv est neutralisé avant l'import d'agent (importé par upload_session).

Sorties (déterministes : même entrée -> mêmes fichiers, aucun horodatage) :
    tests/judge/contrats/<doc>.json   extraits (id, article, texte) + contrôle
    tests/judge/contrats/<doc>.md     version lisible pour l'annotation humaine

Contrôle de cohérence : nombre d'extraits, articles « chapitre », articles
définis et extraits tronqués comparés au JSON du 25/09. Un écart est signalé
(code de sortie 1), jamais corrigé.

Usage (depuis la racine du dépôt) :
    .venv/bin/python tests/judge/build_contrats.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TESTS = HERE.parent
ROOT = TESTS.parent
SRC = ROOT / "src"
CONTRATS_DIR = HERE / "contrats"
REFERENCE_RUN = TESTS / "results" / "upload_eval_20260925_104952.json"

EXIT_OK = 0
EXIT_ECART = 1

for chemin in (str(SRC), str(TESTS)):
    if chemin not in sys.path:
        sys.path.insert(0, chemin)

from eval_upload_engines import build_references, neutralize_dotenv  # noqa: E402


def extrait_id(index: int, article: str) -> str:
    """Même schéma d'id que l'indexation du chemin upload (upload_session.embed_and_index)."""
    return f"upload_{index}_{article or 'na'}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def controle(doc_ref: dict, chunks: list[dict], definitions: frozenset[str], n_tronques: int) -> dict:
    """Compare le découpage obtenu à celui enregistré le 25/09. Ne corrige rien."""
    chapitres = sorted({c["metadata"]["article_num"] for c in chunks if c["metadata"].get("article_num")})
    # La clé a été renommée après le run (512 tokens e5 -> 2000 caractères, commit 81028e4).
    tronques_ref = doc_ref.get("chunks_tronques_512_tokens", doc_ref.get("chunks_tronques"))
    ecarts = []
    if len(chunks) != doc_ref["chunks"]:
        ecarts.append(f"extraits : {len(chunks)} obtenus, {doc_ref['chunks']} le 25/09")
    if chapitres != doc_ref["articles_chapitre"]:
        ecarts.append(f"articles chapitre : {chapitres} obtenus, {doc_ref['articles_chapitre']} le 25/09")
    if sorted(definitions) != doc_ref["articles_definis"]:
        ecarts.append(f"articles définis : {sorted(definitions)} obtenus, {doc_ref['articles_definis']} le 25/09")
    if n_tronques != tronques_ref:
        ecarts.append(f"extraits tronqués : {n_tronques} obtenus, {tronques_ref} le 25/09")
    return {
        "reference": REFERENCE_RUN.name,
        "extraits": {"obtenus": len(chunks), "25_09": doc_ref["chunks"]},
        "extraits_tronques": {"obtenus": n_tronques, "25_09": tronques_ref},
        "articles_chapitre_identiques": chapitres == doc_ref["articles_chapitre"],
        "articles_definis_identiques": sorted(definitions) == doc_ref["articles_definis"],
        "ecarts": ecarts,
    }


def render_markdown(contrat: dict) -> str:
    lignes = [
        f"# {contrat['titre']} — v{contrat['version']} ({contrat['doc']})",
        "",
        f"Contrat entier reconstitué depuis `{contrat['pdf']}`, découpé comme sur le chemin upload "
        f"({len(contrat['extraits'])} extraits). Texte brut issu du PDF : les tableaux sont aplatis "
        "ligne à ligne, et le « n » en début de ligne est la puce des sous-clauses "
        "(ex. « n Article 4.1 — … »).",
        "",
    ]
    for e in contrat["extraits"]:
        titre = f"Article {e['article']}" if e["article"] else "Préambule (sans numéro d'article)"
        lignes += [f"## {titre}", "", f"`{e['id']}`" + (" — **tronqué**" if e["tronque"] else ""), "", "```text", e["texte"], "```", ""]
    return "\n".join(lignes)


def main() -> int:
    neutralize_dotenv()
    import extract_chunks  # noqa: E402
    import upload_session  # noqa: E402

    reference = json.loads(REFERENCE_RUN.read_text(encoding="utf-8"))["documents"]
    CONTRATS_DIR.mkdir(parents=True, exist_ok=True)
    code = EXIT_OK
    for doc in extract_chunks.DOCS:
        doc_id = doc["source_doc"]
        chunks = upload_session.extract_and_chunk_pdf(doc["path"], source_doc_id=doc_id)
        chunks, avertissements = upload_session.apply_length_guard(chunks)
        lignes_pdf = extract_chunks.extract_text_from_pdf(doc["path"])
        refs = build_references(lignes_pdf, chunks)
        contrat = {
            "doc": doc_id,
            "pdf": doc["path"].name,
            "pdf_sha256": sha256(doc["path"]),
            "titre": doc["titre_humain"],
            "version": doc["version"],
            "methode": "upload_session.extract_and_chunk_pdf + apply_length_guard (aucun appel API)",
            "extraits": [
                {
                    "id": extrait_id(i, c["metadata"].get("article_num", "")),
                    "article": c["metadata"].get("article_num", ""),
                    "chapitre_titre": c["metadata"].get("chapitre_titre", ""),
                    "texte": c["text"],
                    "tronque": bool(c["metadata"].get("tronque", False)),
                }
                for i, c in enumerate(chunks)
            ],
            "controle": controle(reference[doc_id], chunks, refs.definitions, len(avertissements)),
        }
        (CONTRATS_DIR / f"{doc_id}.json").write_text(
            json.dumps(contrat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (CONTRATS_DIR / f"{doc_id}.md").write_text(render_markdown(contrat), encoding="utf-8")
        ecarts = contrat["controle"]["ecarts"]
        print(f"[{doc_id}] {len(chunks)} extraits, {len(avertissements)} tronqué(s) — "
              + ("conforme au 25/09" if not ecarts else "ÉCARTS : " + " ; ".join(ecarts)))
        if ecarts:
            code = EXIT_ECART
    return code


if __name__ == "__main__":
    sys.exit(main())
