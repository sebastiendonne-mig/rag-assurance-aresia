# Brief technique — RAG agentique assurance (démo entretien)

## Contexte en une phrase

Démo technique pour un entretien : agent RAG qui répond à des questions sur des
contrats d'assurance (CG, barèmes, circulaire réglementaire) en démontrant les
patterns **Plan-and-Execute** et **ReAct**, avec traçabilité complète du
raisonnement — pas un RAG simple à une passe.

## Stack imposée

- Python
- LangGraph (orchestration en graphe d'état)
- API Anthropic (Claude) pour le raisonnement et la génération
- Chroma (vector store local)
- `multilingual-e5-large` via sentence-transformers (embeddings)
- pypdf ou pdfplumber (extraction PDF)
- Streamlit (interface de démo)

Aucun lien avec un projet précédent (Azure/Power Platform/Copilot Studio) — stack
entièrement nouvelle, seul le corpus documentaire est réemployé.

## Corpus disponible (4 PDF, à uploader dans l'environnement de travail)

1. **CG Prévoyance Invalidité** — `CG-PREV-INV-2024`, v4.2, ~10 pages utiles
   (Titres I à X, articles numérotés 1-23, alinéas marqués `■`)
2. **CG Assurance Vie Multisupport** — `CG-AV-MULTI-2024` (ARESIA Patrimoine+),
   v3.1, ~7 pages utiles (Chapitres 1-10, articles 1-24)
3. **Barème Garanties IARD 2024** — `BAR-IARD-2024-V2`, v2.0, ~5 pages
   (Sections 1-4, articles 1.1-4.1)
4. **Circulaire ACPR devoir de conseil** — `ACPR-REC-2024-12` (fictive), ~5 pages
   (Sections I-IV, articles 1-8)

Tous les documents sont fictifs (créés pour un projet pédagogique antérieur,
"AssurConseil 365"). Structure homogène : `Article N` ou `N.N` comme repère
principal, alinéas d'attention marqués `■`, nombreux tableaux de barèmes/montants.

## Golden set de validation

20 questions de test disponibles, réparties en 5 blocs :
- Bloc 1 (Q01-Q06) : Prévoyance Invalidité
- Bloc 2 (Q07-Q12) : Assurance Vie
- Bloc 3 (Q13-Q16) : IARD
- Bloc 4 (Q17-Q19) : ACPR
- Bloc 5 (Q20) : hors base documentaire — doit déclencher la réponse "non trouvé",
  jamais une invention

**Q20 est un garde-fou critique** : une garantie obsèques qui n'existe dans aucun
document. Si l'agent invente une réponse à Q20, c'est un échec bloquant.

Deux questions cibles pour démontrer Plan-and-Execute (multi-sous-questions) :
- *"Quelle indemnisation pour une invalidité partielle suite à un accident, avec
  une rente complémentaire ?"* → décomposition en (a) définition IPP, (b) barème
  applicable, (c) clause rente complémentaire
- Toute question combinant explicitement deux garanties ou deux documents

## Architecture finalisée

### 1. Pipeline d'indexation (one-shot, avant le graphe)

```
PDF (pypdf/pdfplumber)
  → extraction texte par page
  → détection des marqueurs "Article N" / "N.N" / alinéas "■" / tableaux
  → découpage en chunks = 1 article (ou 1 alinéa ■) avec tableau atomique
    RÈGLE CRITIQUE : un tableau ne doit JAMAIS être coupé entre deux chunks.
    Si un article contient un tableau, l'article + son tableau = un seul chunk,
    même si cela dépasse la taille "idéale" d'un chunk classique.
  → métadonnées par chunk :
    {
      "source_doc": "CG-PREV-INV-2024",
      "version": "4.2",
      "titre_humain": "CG Prévoyance Invalidité",
      "chapitre_titre": "Garanties Incapacité Temporaire de Travail",
      "article_num": "4.1"
    }
  → embedding (multilingual-e5-large, sentence-transformers)
  → upsert dans Chroma (collection unique, filtrable par métadonnée source_doc)
```

Décisions à respecter :
- **Chunking par article, jamais plus fin.** L'article est l'unité de citation
  exigée par le prompt système (`[Article X.Y des CG ... — vZ]`), donc chunk et
  citation doivent être alignés 1:1.
- **Pas de chunk "à cheval" sur deux articles.** Si un article est très court,
  ne pas le fusionner avec le suivant — garder la granularité de citation propre.
- **Encodage e5 : préfixer les passages avec `"passage: "` et les requêtes avec
  `"query: "`** (convention du modèle e5, sinon perte de perf significative).

### 2. État partagé LangGraph

```python
class AgentState(TypedDict):
    question_originale: str
    produit_filtre: str | None          # filtre document optionnel, donné en input
    sous_questions: list[dict]          # [{texte, doc_cible_probable}]
    resultats: list[dict]               # [{sous_question, chunks, suffisant, tentatives, methode_reformulation}]
    reponse_finale: str
    trace_log: list[dict]               # append-only, format JSON, voir plus bas
```

### 3. Nœuds du graphe

1. **`router`** — décide Plan-and-Execute vs ReAct simple.
   Heuristique de départ : détection LLM légère ("cette question a-t-elle
   plusieurs composantes distinctes nécessitant des sources différentes ?").
   Ne pas sur-ingénierer cette étape — un simple appel LLM avec sortie
   structurée `{multi_composantes: bool}` suffit.

2. **`planner`** (si multi-composantes) — décompose en sous-questions explicites.
   Sortie structurée : `list[{texte: str, doc_cible_probable: str | None}]`.

3. **`retrieve`** — recherche Chroma top-k (k=4 ou 5) pour chaque sous-question
   (ou la question simple si pas de planning). Applique le filtre document si
   `produit_filtre` est connu ou si `doc_cible_probable` a été déduit.

4. **`evaluate`** (cœur du ReAct) — le LLM juge si les chunks suffisent.
   Sortie structurée : `{suffisant: bool, raison: str}`.
   - suffisant → vers `synthesize` pour cette sous-question
   - insuffisant ET tentatives < 2 → `reformulate`
   - insuffisant après 2 tentatives → marquer "non trouvé", ne jamais inventer

5. **`reformulate`** — deux niveaux, dans cet ordre :
   - **Niveau 1 (par défaut)** : reformulation lexicale (synonymes, termes
     proches — ex. "burn-out" → "affection psychiatrique"). Reste sur le même
     filtre document.
   - **Niveau 2 (fallback, après échec niveau 1)** : élargissement du filtre —
     retire le filtre document s'il y en avait un, recherche sur tout le corpus.
   Logguer explicitement quel niveau a été utilisé (`methode_reformulation`)
   pour que ce soit visible dans la trace Streamlit.

6. **`synthesize`** — combine les résultats de toutes les sous-questions en une
   réponse finale, format imposé strict (voir prompt système ci-dessous).
   Signale explicitement toute sous-question "non trouvée" plutôt que de la
   passer sous silence ou de combler avec une inférence.

7. **`log`** — à chaque transition de nœud, append dans `trace_log` :
   ```json
   {
     "etape": "evaluate",
     "sous_question": "...",
     "chunks_recus": 4,
     "decision": "insuffisant",
     "raison": "Les chunks récupérés concernent l'IPT (Art. 6-7), pas l'IPP (Art. 8)",
     "action_suivante": "reformulate_niveau_1"
   }
   ```
   Ce log alimente directement l'affichage Streamlit (colonne traçabilité).

### 4. Prompt système (reprendre presque tel quel du projet précédent)

Règles non négociables, déjà validées sur le golden set v1 :
1. Grounding strict — jamais de connaissances générales sur garanties/montants/délais
2. Citation obligatoire — format exact `[Article X.Y des CG {Produit} — v{version}]`
3. Honnêteté sur les limites — phrase exacte si info absente :
   *"Je ne trouve pas cette information dans les documents disponibles. Je vous
   recommande de contacter votre référent produit ou le service technique."*
4. Langage accessible, jargon expliqué en une phrase si indispensable
5. Format de réponse en 3 blocs : **Réponse directe** / **Source(s)** / **Point d'attention**
6. Questions fiscales/successorales complexes → recommander un expert, jamais
   d'interprétation personnelle

### 5. Interface Streamlit

Deux colonnes :
- **Gauche** : chat question/réponse classique
- **Droite** : déroulé du `trace_log` en accordéon, une entrée par étape du
  graphe, avec décision et raison affichées clairement

## Ordre d'implémentation recommandé

1. Setup projet (`requirements.txt`, structure de dossiers, `.env` pour clé API)
2. Script d'extraction PDF → chunks structurés (valider manuellement le
   chunking sur les 4 PDF avant de passer à l'embedding — vérifier en particulier
   qu'aucun tableau n'est coupé)
3. Script d'indexation Chroma (embeddings e5, upsert avec métadonnées)
4. Test de retrieval pur (sans LLM) sur quelques questions du golden set —
   valider que le bon article remonte en top-3 avant de construire le graphe
5. Graphe LangGraph nœud par nœud, en commençant par le chemin simple
   (`retrieve` → `evaluate` → `synthesize`, sans Plan-and-Execute ni reformulation)
6. Ajout de `reformulate` et de la boucle ReAct
7. Ajout de `router` + `planner` pour Plan-and-Execute
8. Logging structuré sur tous les nœuds
9. Test complet sur les 20 questions du golden set — **Q20 doit impérativement
   déclencher "non trouvé", pas d'invention**
10. Interface Streamlit (chat + trace)

## Points d'attention transverses

- **Ne jamais halluciner un chiffre.** C'est le risque n°1 sur ce corpus
  (tableaux de montants/franchises/plafonds partout). Le chunking atomique des
  tableaux + le prompt système + le golden set Q20 sont les trois garde-fous.
- **Tracer le raisonnement, pas seulement le résultat.** L'intérêt de la démo
  est de montrer *pourquoi* l'agent a reformulé ou décomposé — pas juste qu'il a
  fini par trouver la bonne réponse.
- **Garder le code lisible pour une démo live en entretien.** Préférer des
  fonctions courtes et nommées explicitement (`evaluate_sufficiency`,
  `reformulate_query_level1`) à de l'abstraction excessive.
