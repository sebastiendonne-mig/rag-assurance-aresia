# Grille du juge — fidélité au contrat (chemin upload)

Cette grille sert au juge LLM hors ligne (lot C) **et** à l'annotation humaine
(`annotation_humaine.md`). Les deux appliquent exactement les mêmes règles.

## Ce qui est jugé

Une réponse produite le 25/09/2026 (évaluation du sous-lot 3.2) par Claude ou
Mistral, à une question posée sur **un** document. Elle est jugée contre le
**contrat entier** de ce document, c'est-à-dire tous ses extraits :
`tests/judge/contrats/<doc>.json` (version lisible : `<doc>.md`).

Le contrat entier est plus large que ce que le modèle a réellement vu (les 10
extraits récupérés ce jour-là, non sauvegardés). Une réponse peut donc
s'appuyer sur un passage que le modèle n'avait pas sous les yeux. Peu importe :
on juge la fidélité au contrat, pas au contexte reçu.

## Règles générales

1. Trois critères indépendants : C1, C2, C3. Un verdict par critère.
2. **La justification est écrite AVANT le verdict.** Elle cite le passage de
   la réponse en cause et, s'il existe, le passage du contrat (article et mots
   exacts). Un verdict sans justification n'est pas valide.
3. Verdicts possibles : `oui` (le critère est respecté), `non` (il ne l'est
   pas), `sans objet` (seulement pour C2 et C3, dans les cas prévus plus bas).
4. Un seul manquement suffit pour un `non`.
5. On ne juge ni le style, ni la longueur, ni le format en 3 blocs.

## C1 — Fidélité

**Question :** chaque affirmation sur le contenu du contrat est-elle appuyée
par le texte du contrat ?

- `non` si la réponse attribue au contrat un chiffre, une durée, un montant,
  une garantie, une exclusion ou une condition qui n'y figure pas, ou qui
  diffère du texte. Cela inclut une condition **omise** qui élargit la portée
  réelle d'une garantie, par exemple une restriction « sous réserve de… »
  présente dans le contrat et absente de la réponse, si bien que la garantie
  paraît plus large qu'elle ne l'est.
- **Connaissance générale tolérée** si elle est clairement présentée comme une
  hypothèse, un conseil ou une information extérieure au contrat. Exemple
  accepté (Q20, Claude) : « Il est possible que la garantie obsèques […] ne soit
  pas incluse dans ce contrat prévoyance (elle fait souvent l'objet d'un
  contrat dédié séparé) ». Elle est **sanctionnée** si elle est
  présentée comme le contenu du contrat.
- Une reformulation fidèle, un calcul exact à partir du contrat (ex. 1 095
  jours = 3 ans) ou une simplification qui ne change pas la portée sont
  acceptés.
- **C1 porte sur l'exactitude du contenu.** Un chiffre faux reste un défaut C1
  même s'il est placé sous la bonne citation (voir C2).

## C2 — Citations

**Question :** chaque article cité existe-t-il dans le document, et traite-t-il
de l'information qu'on lui attribue ?

- `non` si un article cité n'existe pas dans le document, ou s'il existe mais
  porte sur autre chose que ce qui lui est attribué (ex. la liste du DRIB
  attribuée à l'article des durées de conservation).
- **C2 juge le rattachement, pas l'exactitude.** Si le bon article est cité
  mais que le chiffre rapporté est faux : C2 `oui`, C1 `non`.
- **Renvoi interne accepté :** un numéro d'article qui n'existe pas comme
  article mais qui figure dans le texte même du document comme renvoi est
  accepté. Cas connu : « Article 6.3 », renvoi mort de l'article 6.1 (étape 5)
  du contrat prévoyance (CG-PREV-INV-2024), relayé par Mistral en Q04 et Q05.
- Une plage citée (« articles 1 à 21 ») est acceptée si elle décrit
  correctement le document consulté.
- Un renvoi légal extérieur, présenté comme tel (ex. « Article 990-I du Code
  général des impôts »), n'est pas une citation du document et ne compte pas.
- `sans objet` si la réponse ne cite aucun article. L'absence de citation
  relève du format, pas de la fidélité.

## C3 — Refus

**Question :** si l'information demandée n'est pas dans le contrat, la
réponse le dit-elle clairement, sans rien inventer ?

- `sans objet` si l'information demandée **est** dans le contrat. C'est le cas
  de toutes les questions sauf Q20.
- `oui` si la réponse dit clairement que le contrat ne contient pas
  l'information, sans affirmer de contenu à la place. Des hypothèses
  présentées comme telles et un renvoi vers l'assureur sont acceptés.
- `non` si la réponse affirme l'existence de l'information (ex. une garantie
  obsèques chiffrée), ou si le refus est si ambigu qu'un lecteur pourrait
  croire l'information présente.
- Un refus alors que l'information **est** dans le contrat (faux négatif) se
  juge en C1 (`non` : la réponse affirme une absence qui contredit le texte).
  C3 reste alors `sans objet`.

## Format de sortie attendu (lot C)

```json
{
  "C1": {"justification": "…", "verdict": "oui | non"},
  "C2": {"justification": "…", "verdict": "oui | non | sans objet"},
  "C3": {"justification": "…", "verdict": "oui | non | sans objet"}
}
```

Dans chaque objet, la clé `justification` précède `verdict` : le modèle
l'écrit d'abord.

## Calibration : copies piégées

`tests/judge/pieges.json` contient 10 réponses réelles modifiées sur **une
seule information** (5 types × 2 moteurs). Chaque copie précise le critère visé
et le verdict attendu. Pour les critères non visés, `"inchangé"` signifie : même
verdict que la réponse d'origine, tel que l'annotation humaine l'aura établi.
