# Questions de test RAG — AssurConseil 365

**Fichier :** `/tests/questions-test-rag.md`  
**Projet :** AssurConseil 365 — ARESIA Assurances (fictif)  
**Auteur :** Sébastien Donné | tkoidra.com  
**Date :** Juin 2026  
**Usage :** Phase 1.3 (validation indexation) + Phase 2.4 (validation agent Copilot Studio)

---

## Instructions d'utilisation

Pour chaque question :
1. Poser la question à l'agent (ou directement à l'API en Phase 1.3)
2. Vérifier que la réponse cite la bonne source (colonne "Source attendue")
3. Vérifier l'absence d'hallucination (colonne "Réponse incorrecte type")
4. Cocher la case et noter le score de pertinence (1-3) dans la colonne résultat

**Score de pertinence :**
- ✅ 3/3 — Réponse correcte, source citée, format respecté
- ⚠️ 2/3 — Réponse correcte mais source manquante ou format non respecté
- ❌ 1/3 — Réponse incorrecte ou hallucination détectée

**Seuil de passage Phase 1.3 :** 18/20 questions à 3/3  
**Seuil de passage Phase 2.4 :** 20/20 questions à 3/3

---

## Bloc 1 — Prévoyance Invalidité (6 questions)

### Q01 — Franchise ITT
**Question :** "Quelles sont les options de franchise disponibles sur le contrat prévoyance invalidité ?"  
**Source attendue :** Article 4.1 — CG Prévoyance Invalidité v4.2  
**Réponse incorrecte type :** Inventer une franchise fixe (ex: "30 jours obligatoires")  
**Résultat Phase 1.3 :** ☐  
**Résultat Phase 2.4 :** ☐  

---

### Q02 — Montant indemnité journalière
**Question :** "Quel est le montant maximum d'indemnité journalière pour quelqu'un qui gagne 80 000 € par an ?"  
**Source attendue :** Article 4.2 — CG Prévoyance Invalidité v4.2 (tableau IJ par tranche)  
**Réponse incorrecte type :** Donner un montant hors tableau ou confondre option Standard et Premium  
**Résultat Phase 1.3 :** ☐  
**Résultat Phase 2.4 :** ☐  

---

### Q03 — Durée maximale ITT
**Question :** "Combien de temps peut-on être indemnisé en arrêt de travail avant de basculer en invalidité ?"  
**Source attendue :** Article 4.3 — CG Prévoyance Invalidité v4.2  
**Réponse incorrecte type :** Confondre avec une durée légale Sécu (ex: 3 ans en Sécu ≠ 1 095 jours contrat)  
**Résultat Phase 1.3 :** ☐  
**Résultat Phase 2.4 :** ☐  

---

### Q04 — Conditions reconnaissance IPT
**Question :** "À partir de quel taux d'invalidité est-on reconnu en Invalidité Permanente Totale ?"  
**Source attendue :** Article 6 — CG Prévoyance Invalidité v4.2  
**Réponse incorrecte type :** Confondre IPT (66%) et IPP (33%-65%) ou donner le taux Sécu (inapplicable ici)  
**Résultat Phase 1.3 :** ☐  
**Résultat Phase 2.4 :** ☐  

---

### Q05 — Exclusions ITT
**Question :** "Le burn-out est-il couvert par le contrat prévoyance invalidité ?"  
**Source attendue :** Articles 13 et 13.5 — CG Prévoyance Invalidité v4.2  
**Réponse incorrecte type :** Répondre "non couvert" sans mentionner la distinction Standard/Premium  
**Résultat Phase 1.3 :** ☐  
**Résultat Phase 2.4 :** ☐  

---

### Q06 — Rechute ITT
**Question :** "Si un assuré reprend le travail pendant 3 semaines puis retombe en arrêt, doit-il resubir une franchise ?"  
**Source attendue :** Article 4.1 (note) — CG Prévoyance Invalidité v4.2  
**Réponse incorrecte type :** Dire "oui, une nouvelle franchise s'applique systématiquement"  
**Résultat Phase 1.3 :** ☐  
**Résultat Phase 2.4 :** ☐  

---

## Bloc 2 — Assurance Vie (6 questions)

### Q07 — Fiscalité rachat après 8 ans
**Question :** "Quelle est la fiscalité d'un rachat partiel sur une assurance vie ouverte il y a 10 ans ?"  
**Source attendue :** Article 23 — CG Assurance Vie ARESIA Patrimoine+ v3.1  
**Réponse incorrecte type :** Donner un taux incorrect ou oublier les prélèvements sociaux  
**Résultat Phase 1.3 :** ☐  
**Résultat Phase 2.4 :** ☐  

---

### Q08 — Versement minimum
**Question :** "Quel est le montant minimum pour un versement complémentaire sur ARESIA Patrimoine+ ?"  
**Source attendue :** Article 8 — CG Assurance Vie ARESIA Patrimoine+ v3.1  
**Réponse incorrecte type :** Donner le montant du versement initial (1 000 €) au lieu du versement complémentaire (300 €)  
**Résultat Phase 1.3 :** ☐  
**Résultat Phase 2.4 :** ☐  

---

### Q09 — Avance sur contrat
**Question :** "Peut-on faire une avance sur son contrat d'assurance vie et jusqu'à quel montant ?"  
**Source attendue :** Article 15 — CG Assurance Vie ARESIA Patrimoine+ v3.1  
**Réponse incorrecte type :** Confondre avance et rachat partiel, ou donner un pourcentage incorrect  
**Résultat Phase 1.3 :** ☐  
**Résultat Phase 2.4 :** ☐  

---

### Q10 — Garantie fonds euros
**Question :** "Le fonds en euros ARESIA Sécurité garantit-il le capital investi ?"  
**Source attendue :** Article 10 — CG Assurance Vie ARESIA Patrimoine+ v3.1  
**Réponse incorrecte type :** Confirmer une garantie absolue sans mentionner les frais sur versements  
**Résultat Phase 1.3 :** ☐  
**Résultat Phase 2.4 :** ☐  

---

### Q11 — Fiscalité décès conjoint
**Question :** "Un conjoint bénéficiaire d'une assurance vie est-il exonéré de droits de succession ?"  
**Source attendue :** Article 24.2 — CG Assurance Vie ARESIA Patrimoine+ v3.1  
**Réponse incorrecte type :** Appliquer les règles du droit successoral ordinaire  
**Résultat Phase 1.3 :** ☐  
**Résultat Phase 2.4 :** ☐  

---

### Q12 — Frais d'arbitrage
**Question :** "Combien coûte un arbitrage entre supports sur ARESIA Patrimoine+ ?"  
**Source attendue :** Article 9 — CG Assurance Vie ARESIA Patrimoine+ v3.1  
**Réponse incorrecte type :** Dire que les arbitrages sont gratuits sans mentionner la condition (4/an en gestion libre)  
**Résultat Phase 1.3 :** ☐  
**Résultat Phase 2.4 :** ☐  

---

## Bloc 3 — IARD (4 questions)

### Q13 — Franchise bris de glace auto
**Question :** "Quelle est la franchise en cas de bris de pare-brise avec un réparateur agréé ?"  
**Source attendue :** Article 2.3 — Barème Garanties IARD 2024 v2.0  
**Réponse incorrecte type :** Donner la franchise sans distinguer réparateur agréé / non agréé  
**Résultat Phase 1.3 :** ☐  
**Résultat Phase 2.4 :** ☐  

---

### Q14 — RC Pro CGP
**Question :** "Quel est le plafond de RC Professionnelle pour un conseiller en gestion de patrimoine ?"  
**Source attendue :** Article 3.1 et note 3.1.5 — Barème Garanties IARD 2024 v2.0  
**Réponse incorrecte type :** Donner un plafond d'une autre catégorie professionnelle  
**Résultat Phase 1.3 :** ☐  
**Résultat Phase 2.4 :** ☐  

---

### Q15 — Délai déclaration vol
**Question :** "Dans quel délai doit-on déclarer un cambriolage à son assureur ?"  
**Source attendue :** Article 4.1 — Barème Garanties IARD 2024 v2.0  
**Réponse incorrecte type :** Donner le délai général (5 jours) sans mentionner le dépôt de plainte obligatoire  
**Résultat Phase 1.3 :** ☐  
**Résultat Phase 2.4 :** ☐  

---

### Q16 — MRH couverture vol espèces
**Question :** "La multirisque habitation couvre-t-elle le vol d'espèces au domicile et jusqu'à quel montant ?"  
**Source attendue :** Article 1.1 — Barème Garanties IARD 2024 v2.0  
**Réponse incorrecte type :** Dire simplement "oui" sans préciser le plafond de 5 000 €  
**Résultat Phase 1.3 :** ☐  
**Résultat Phase 2.4 :** ☐  

---

## Bloc 4 — Réglementaire ACPR (3 questions)

### Q17 — Documents du DRIB
**Question :** "Quels éléments doit obligatoirement contenir le Document de Recueil des Informations et des Besoins ?"  
**Source attendue :** Article 4 — Circulaire ACPR-REC-2024-12 (fictive)  
**Réponse incorrecte type :** Donner une liste incomplète ou inventer des exigences non mentionnées  
**Résultat Phase 1.3 :** ☐  
**Résultat Phase 2.4 :** ☐  

---

### Q18 — Durée de conservation des documents de conseil
**Question :** "Pendant combien de temps dois-je conserver le DRIB et le journal des interactions de conseil ?"  
**Source attendue :** Article 6 — Circulaire ACPR-REC-2024-12 (fictive)  
**Réponse incorrecte type :** Donner la durée légale générale (3 ans) au lieu de la durée contrat + 5 ans  
**Résultat Phase 1.3 :** ☐  
**Résultat Phase 2.4 :** ☐  

---

### Q19 — Formation DDA obligatoire
**Question :** "Combien d'heures de formation continue un conseiller doit-il suivre par an au titre de la DDA ?"  
**Source attendue :** Article 7 — Circulaire ACPR-REC-2024-12 (fictive)  
**Réponse incorrecte type :** Donner un nombre incorrect ou oublier de mentionner les domaines obligatoires  
**Résultat Phase 1.3 :** ☐  
**Résultat Phase 2.4 :** ☐  

---

## Bloc 5 — Hors base documentaire (1 question critique)

### Q20 — Garantie absente de la base
**Question :** "Quelle est la garantie obsèques incluse dans le contrat prévoyance ?"  
**Source attendue :** AUCUNE — cette garantie n'existe pas dans les documents fictifs  
**Réponse attendue EXACTE :**  
> "Je ne trouve pas cette information dans les documents disponibles. Je vous recommande de contacter votre référent produit ou le service technique de ARESIA Assurances."  
**Réponse incorrecte type :** Inventer une garantie obsèques avec un montant fictif  
**Résultat Phase 1.3 :** ☐  
**Résultat Phase 2.4 :** ☐  

---

## Tableau récapitulatif des résultats

| # | Bloc | Score Phase 1.3 | Score Phase 2.4 |
|---|---|---|---|
| Q01-Q06 | Prévoyance (6) | /6 | /6 |
| Q07-Q12 | Assurance Vie (6) | /6 | /6 |
| Q13-Q16 | IARD (4) | /4 | /4 |
| Q17-Q19 | ACPR (3) | /3 | /3 |
| Q20 | Hors base (1) | /1 | /1 |
| **TOTAL** | | **/20** | **/20** |

---

## Grille d'évaluation détaillée

Pour chaque réponse, évaluer les 4 critères suivants :

| Critère | Poids | Description |
|---|---|---|
| **Exactitude** | 40% | La réponse est factuellement correcte par rapport aux documents |
| **Source citée** | 30% | La bonne clause ou article est mentionné(e) |
| **Format** | 20% | Les 3 blocs (Réponse / Source / Point d'attention) sont présents |
| **Ton** | 10% | Langage clair, pas de jargon non expliqué, pas de sur-promesse |

---

*Document fictif — AssurConseil 365 | tkoidra.com — Juin 2026*
