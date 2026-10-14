# Juge LLM — fidélité au contrat (fumée)

- Date (UTC) : 2026-10-14T15:53:05+00:00
- Modèle du juge : `gemini-3.8-flash`
- Région : `eu` — traité dans l'UE (multi-région eu, pays non précisé)
- Endpoint : `https://aiplatform.eu.rep.googleapis.com/`
- Tarif utilisé : 0.825 $ / 4.125 $ par million de tokens (entrée / sortie + raisonnement) — tarif promotionnel jusqu'au 31/12/2026 (1,65 $ / 8,25 $ à partir du 01/01/2027) ; aucune date de retrait publiée pour ce modèle (page modèle consultée le 13/10/2026). Source : https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing (consultée le 13/10/2026).
- Température : 0.0 — demandée à 0, probablement sans effet : la documentation Gemini 3 indique que temperature n'est plus recommandé et qu'il est ignoré par le modèle
- Raisonnement : thinking_level=MEDIUM, max_output_tokens=8192
- Prompt : `prompt_juge.md` sha256 `ca37389fe9f00e5970c98ad1e153056b013f58b464bc1964d215cd858630b96e`
- Commit : `a1deda7951f0dac5229e42e29de19e3eb4e6dbe9` (arbre modifié)
- Répétitions : 1 · graine : 20261013 · plafond : 2 appels

## Synthèse

- Jugements : 1 · valides : 1 · **ERREURS : 0**
- Appels effectués : 1
- Tokens : 4206 en entrée, 265 en sortie, 1098 de raisonnement
- Coût mesuré : 0,01 $ (estimation avant run, borne haute : 0,04 $)

Ce rapport ne compare pas au jugement humain : voir `tests/judge/compare_juge_humain.py`.

## Verdicts

| Id | Rép. | Source | Question | Moteur | C1 | C2 | C3 | Verdict global |
|---|---|---|---|---|---|---|---|---|
| J33 | 1 | P03 | Q16 | anthropic | non | oui | sans objet | rejetée |

## Erreurs du juge (ni accord ni désaccord)

- Aucune.

## Justifications

### J33 (rép. 1) — P03 · Q16 · anthropic

- **C1 : non** — La réponse affirme que « Les moyens de paiement dérobés lors du cambriolage sont également couverts : les retraits frauduleux effectués avec une carte bancaire volée sont remboursés dans la même limite de 5 000 € ». Or, le contrat (Article 1.1) mentionne uniquement « 5 000 € (espèces) » pour la garantie Vol et actes de vandalisme, sans jamais mentionner les moyens de paiement ni la couverture des retraits frauduleux par carte bancaire.
- **C2 : oui** — Les articles cités (Article 1.1 et Article 4.1) existent tous deux dans le document et traitent bien des sujets auxquels ils sont rattachés (plafond/franchise pour le vol et modalités/délais de déclaration de sinistre).
- **C3 : sans objet** — L'information demandée figure dans le contrat à l'article 1.1.

Détail complet : `judge_upload_20261014_155305_smoke.json`
