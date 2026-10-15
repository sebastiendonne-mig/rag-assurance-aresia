# Validation du juge LLM par les pièges seuls

- Date (UTC) : 2026-10-15T09:21:55+00:00
- Résultats du juge : `judge_upload_20261014_155950.json` — modèle `gemini-3.8-flash`, traité dans l'UE (multi-région eu, pays non précisé)
- Prompt du juge : sha256 `ca37389fe9f00e5970c98ad1e153056b013f58b464bc1964d215cd858630b96e`
- Seuils : `tests/judge/seuils.md`, amendement du 14/10/2026 (pièges seuls) ; calculés sur la répétition 1.
- La fiche d'annotation humaine n'est pas lue.

## Verdict final : **SEUILS ATTEINTS**

| Condition (seuils.md, amendement du 14/10/2026) | Valeur | Résultat |
|---|---|---|
| Au moins 8 pièges détectés sur 10 | 9 / 10 | atteint |
| Au plus 1 piège d'écart entre Claude et Mistral | Claude 5 / Mistral 4 (écart 1) | atteint |

## Pièges

| Piège | Moteur | Question | Critère visé | Verdict du juge | Résultat |
|---|---|---|---|---|---|
| P01 | Claude | Q09 | C1 | non | détecté |
| P02 | Mistral | Q18 | C1 | non | détecté |
| P03 | Claude | Q16 | C1 | non | détecté |
| P04 | Mistral | Q10 | C1 | non | détecté |
| P05 | Claude | Q01 | C1 | non | détecté |
| P06 | Mistral | Q15 | C1 | oui | **manqué** |
| P07 | Claude | Q17 | C2 | non | détecté |
| P08 | Mistral | Q07 | C2 | non | détecté |
| P09 | Claude | Q20 | C3 | non | détecté |
| P10 | Mistral | Q20 | C3 | non | détecté |

Détectés : Claude 5 / 5 · Mistral 4 / 5 · écart 1

## Erreurs du juge et jugements manquants

- Aucune.

## Relecture humaine qualitative (sans seuil) : 9 critère(s) « non »

Réponses d'origine (pas les pièges) jugées « non » sur au moins un critère.

| Id | Moteur | Question | Critère | Justification du juge |
|---|---|---|---|---|
| J02 | Mistral | Q12 | C1 | La réponse affirme qu'« En gestion libre, 4 arbitrages par an sont gratuits », omettant la condition essentielle du tableau de l'Article 9 qui réserve cette gratuité au « Taux partenaire conseiller » par opposition au « Taux standard » (0,50 % avec min. 15 €). Cette omission élargit indûment la gratuité à tous les souscripteurs en gestion libre. |
| J02 | Mistral | Q12 | C2 | La réponse cite l'« Article 9.4 » pour les frais d'arbitrage, or le paragraphe 9.4 traite exclusivement des modalités de prélèvement des frais de gestion annuels sur le fonds euros et les UC. Les frais d'arbitrage figurent dans le tableau général de l'Article 9. |
| J10 | Mistral | Q05 | C1 | La réponse affirme que pour l'IPT, le burn-out est couvert « uniquement si l’assuré a souscrit l’option Premium » et indique « Option Premium requise pour l’IPT : Sans cette option, le burn-out peut être soumis à une surprime ou une exclusion spécifique ». Or, l'Article 5.1 (« Les affections psychiatriques (dépression, burn-out, troubles anxieux) sont couvertes sans limitation de durée spécifique pour les assurés ayant souscrit l'option Premium, sous réserve d'un suivi psychiatrique régulier attesté ») ne restreint pas son champ à l'IPT et ne subordonne pas l'accès à la garantie IPT à la souscription de l'option Premium (qui n'est par ailleurs qu'un niveau de barème de rente à l'Article 7). De plus, la surprime ou exclusion prévue à l'Article 5 repose sur le questionnaire médical de santé et non sur l'absence d'option Premium. |
| J14 | Mistral | Q08 | C1 | La réponse affirme qu'« Aucun frais n'est appliqué sur les versements complémentaires libres », or l'Article 9 indique des « Frais sur versements » de « 0% à 4,5% selon le réseau » (taux standard) et réserve le taux de 0% aux seuls « versements programmés » pour le taux partenaire conseiller. Le contrat n'indique pas que les versements complémentaires libres sont exonérés de frais. |
| J18 | Claude | Q06 | C1 | La réponse affirme en ouverture : « Dans le cas décrit — reprise du travail pendant 3 semaines (21 jours) puis nouvel arrêt — **une nouvelle franchise s'applique** », ce qui contredit directement l'Article 4.1 du contrat (« En cas de rechute survenant dans les 30 jours suivant la reprise d'activité, l'arrêt est considéré comme la continuité du sinistre initial et aucune nouvelle franchise ne s'applique »). Même si la suite du texte se contredit et affirme l'inverse, cette affirmation initiale erronée constitue un manquement. |
| J21 | Mistral | Q04 | C1 | La réponse affirme que « La reconnaissance de l’IPT est définitive après consolidation, sauf amélioration significative justifiant une réévaluation ([Article 6]) », or cette règle et cette modalité de réévaluation ne figurent nulle part dans l'Article 6 ni dans le contrat. De plus, la mention « Aucune prestation n’est versée pour un taux inférieur à 66% » contredit l'Article 6.2 qui prévoit le versement d'une rente pour l'IPP entre 33% et 65%. |
| J34 | Claude | Q07 | C1 | Dans son tableau pour les contrats de plus de 8 ans dépassant 150 000 €, la réponse inverse les colonnes du tableau de l'article 23. Elle attribue aux « Primes versées avant septembre 2017 » la formule « Au-delà de 150 000 € : 7,5% jusqu'au seuil + 12,8% au-delà + PS » et aux « Primes versées après septembre 2017 » la mention « Même règle — seuil de 150 000 € tous contrats confondus ». Or, dans le tableau de l'article 23, la colonne « Primes versées avant 09/2017 » indique « Même règle — seuil 150 k€ tous contrats » tandis que la colonne « Primes versées après 09/2017 (PFU) » porte la mention « 7,5% IR sur 150 k€ + 12,8% au-delà + PS ». |
| J47 | Claude | Q18 | C1 | La réponse indique pour le Journal des interactions de conseil : « base de données horodatée et immuable (archivage électronique NF Z42-013 recommandé) ». Or, dans le tableau de l'Article 6, la recommandation « Archivage électronique NF Z42-013 recommandé » est spécifiquement rattachée aux « Correspondances contractuelles », tandis que le support recommandé pour le « Journal des interactions de conseil » est uniquement « Base de données horodatée et immuable ». |
| J50 | Mistral | Q19 | C1 | La réponse indique que les 15 heures « sont réparties par domaines obligatoires » et évoque des « thèmes imposés », alors que le tableau de l'Article 7 mentionne explicitement une « Durée minimale recommandée » pour chaque domaine et non une répartition obligatoire. |
