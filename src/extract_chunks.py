"""
Extraction PDF → chunks structurés.
Règle critique : 1 article = 1 chunk, un tableau n'est jamais coupé.
"""
import json
import re
from pathlib import Path
import pdfplumber

ROOT = Path(__file__).parent.parent

DOCS = [
    {
        "path": ROOT / "CG-prevoyance-invalidite.pdf",
        "source_doc": "CG-PREV-INV-2024",
        "version": "4.2",
        "titre_humain": "CG Prévoyance Invalidité",
    },
    {
        "path": ROOT / "CG-assurance-vie.pdf",
        "source_doc": "CG-AV-MULTI-2024",
        "version": "3.1",
        "titre_humain": "CG Assurance Vie ARESIA Patrimoine+",
    },
    {
        "path": ROOT / "bareme-garanties-iard.pdf",
        "source_doc": "BAR-IARD-2024-V2",
        "version": "2.0",
        "titre_humain": "Barème Garanties IARD 2024",
    },
    {
        "path": ROOT / "circulaire-acpr-conseil.pdf",
        "source_doc": "ACPR-REC-2024-12",
        "version": "1.0",
        "titre_humain": "Circulaire ACPR Devoir de Conseil",
    },
]

# Détecte un marqueur d'article (début de chunk)
# Couvre : "Article 4", "Article 4.1", "Article 4.1.2",
# "ARTICLE 4", mais aussi "SECTION 1", "TITRE I", "CHAPITRE 3"
ARTICLE_PATTERN = re.compile(
    r"^(Article\s+\d+(?:\.\d+)*"
    r"|ARTICLE\s+\d+(?:\.\d+)*"
    r"|Section\s+\d+(?:\.\d+)*"
    r"|SECTION\s+\d+(?:\.\d+)*"
    r"|Titre\s+[IVXivx]+"
    r"|TITRE\s+[IVXivx]+"
    r"|Chapitre\s+\d+"
    r"|CHAPITRE\s+\d+"
    r")\b",
    re.IGNORECASE,
)


def _extract_article_num(line: str) -> str:
    """Extrait le numéro d'article depuis la première ligne d'un chunk."""
    m = re.match(
        r"(Article|ARTICLE|Section|SECTION|Titre|TITRE|Chapitre|CHAPITRE)\s+(\S+)",
        line,
        re.IGNORECASE,
    )
    if m:
        return m.group(2).rstrip("—–-").strip()
    return ""


def _extract_chapitre_titre(lines_before: list[str]) -> str:
    """Remonte dans les lignes précédentes pour trouver le titre du chapitre/titre courant."""
    for line in reversed(lines_before):
        line = line.strip()
        if re.match(r"(TITRE|CHAPITRE|SECTION)\s+", line, re.IGNORECASE) and len(line) < 120:
            return line
    return ""


def extract_text_from_pdf(path: Path) -> list[str]:
    """Retourne la liste des lignes texte du PDF (toutes pages)."""
    lines = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=2, y_tolerance=2)
            if text:
                for line in text.split("\n"):
                    lines.append(line)
    return lines


def split_into_chunks(lines: list[str], meta: dict) -> list[dict]:
    """
    Découpe les lignes en chunks délimités par les marqueurs d'article.
    Chaque chunk hérite des métadonnées + numéro d'article détecté.
    """
    chunks = []
    current_lines: list[str] = []
    current_article = ""
    all_lines_so_far: list[str] = []

    def flush(article_num: str, content_lines: list[str], context_lines: list[str]):
            text = "\n".join(content_lines).strip()
            # Filtre 1 : chunk trop court
            if not text or len(text) < 150:
                return
            # Filtre 2 : chunk dominé par des lignes "....... p.XX" (table des matières)
            toc_lines = [l for l in content_lines if re.search(r"\.{4,}\s*p\.\d+", l)]
            if len(toc_lines) > len(content_lines) * 0.4:
                return
            chapitre = _extract_chapitre_titre(context_lines)
            chunk = {
                "text": text,
                "metadata": {
                    "source_doc": meta["source_doc"],
                    "version": meta["version"],
                    "titre_humain": meta["titre_humain"],
                    "chapitre_titre": chapitre,
                    "article_num": article_num,
                },
            }
            chunks.append(chunk)

    for line in lines:
        stripped = line.strip()
        if ARTICLE_PATTERN.match(stripped):
            # Sauvegarder le chunk précédent
            if current_lines:
                flush(current_article, current_lines, all_lines_so_far[:])
            current_article = _extract_article_num(stripped)
            current_lines = [stripped]
        else:
            current_lines.append(line)
        all_lines_so_far.append(line)

    # Dernier chunk
    if current_lines:
        flush(current_article, current_lines, all_lines_so_far[:])

    return chunks


def extract_all_chunks() -> list[dict]:
    all_chunks = []
    for doc_meta in DOCS:
        path = doc_meta["path"]
        print(f"  Extraction : {path.name}")
        lines = extract_text_from_pdf(path)
        meta = {k: v for k, v in doc_meta.items() if k != "path"}
        chunks = split_into_chunks(lines, meta)
        print(f"    → {len(chunks)} chunks extraits")
        all_chunks.extend(chunks)
    return all_chunks


if __name__ == "__main__":
    print("=== Extraction PDF → chunks ===")
    chunks = extract_all_chunks()
    print(f"\nTotal : {len(chunks)} chunks")

    out_path = ROOT / "data" / "chunks" / "chunks.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    print(f"Sauvegardé : {out_path}")

    # Affichage de contrôle
    print("\n--- Aperçu des 3 premiers chunks ---")
    for c in chunks[:3]:
        m = c["metadata"]
        print(f"\n[{m['source_doc']}] Art.{m['article_num']} — {m['chapitre_titre'][:50]}")
        print(c["text"][:200])
        print("...")
