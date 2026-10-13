# Seuils du juge LLM — pré-enregistrement

Texte validé le 12/10/2026, précisé le 13/10/2026 avant tout run du juge.
Ce fichier est committé seul, avant tout autre commit du lot C : le commit fait
foi. Il ne sera pas modifié après le premier run.

- Unité : la réponse. Verdict global d'une réponse = « rejetée » si au moins un
  critère applicable est « non », « validée » sinon (« sans objet » n'est jamais
  bloquant). Désaccord = verdicts globaux différents entre le juge et l'humain.
- Piège détecté = verdict « non » du juge sur le critère visé par le piège (C3
  pour P09 et P10).
- Au moins 8 pièges détectés sur 10.
- Au plus 1 piège d'écart entre les pièges Claude et les pièges Mistral.
- Au plus 4 désaccords juge/humain sur les 40 réponses d'origine, chacun
  expliqué.
- Réponse du juge en ERREUR (JSON invalide, verdict manquant) : ni accord ni
  désaccord ; listée à part ; s'il en reste au moment de la conclusion, le
  verdict final est « mesure incomplète ».
- En cas d'échec d'un seuil : une seule correction du prompt du juge, puis
  nouvelle mesure complète ; résultats publiés même mauvais.
- Les catégories (a)/(b) et le désaccord de motif (point 4) sont descriptifs :
  ils n'ajoutent aucun seuil.
- Avec --repetitions 2, les seuils se calculent sur la première répétition ; la
  seconde ne sert qu'à mesurer la stabilité.
