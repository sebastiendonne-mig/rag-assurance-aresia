# Annotation humaine — fidélité au contrat (à l'aveugle)

40 réponses réelles du 25/09/2026 (évaluation du sous-lot 3.2, chemin upload) :
20 questions × Claude et Mistral, dans un ordre mélangé (graine 20260925).
Aucun résultat automatique n'est affiché ici.

**Contrats de référence** (texte intégral, articles en titres) :
`tests/judge/contrats/` — [ACPR-REC-2024-12](contrats/ACPR-REC-2024-12.md) · [BAR-IARD-2024-V2](contrats/BAR-IARD-2024-V2.md) · [CG-AV-MULTI-2024](contrats/CG-AV-MULTI-2024.md) · [CG-PREV-INV-2024](contrats/CG-PREV-INV-2024.md)

## Rappel de la grille (détail : `tests/judge/grille.md`)

Juger chaque réponse contre le **contrat entier** du document interrogé.
Écrire la justification (ligne Commentaire) **avant** de cocher.

- **C1 Fidélité** : chaque affirmation sur le contrat est appuyée par son texte.
  Une connaissance générale est tolérée si elle est présentée comme une
  hypothèse ou un conseil, sanctionnée si elle est présentée comme le contenu
  du contrat. Un chiffre faux reste un défaut C1 même sous la bonne citation.
  Pas de « sans objet » pour C1.
- **C2 Citations** : chaque article cité existe et traite de l'information
  attribuée (rattachement, pas exactitude). Un renvoi présent dans le texte
  même du document est accepté (cas connu : « 6.3 », renvoi de l'art. 6.1 du
  contrat prévoyance). « sans objet » si aucun article n'est cité.
- **C3 Refus** : si l'information n'est pas dans le contrat, la réponse le dit
  clairement sans rien inventer. « sans objet » si l'information est dans le
  contrat.

## A01 — Claude · Q02

- **Moteur** : Claude
- **Document** : CG-PREV-INV-2024 — [contrat](contrats/CG-PREV-INV-2024.md)
- **Question** : Quel est le montant maximum d'indemnité journalière pour quelqu'un qui gagne 80 000 € par an ?

**Réponse :**

> **Réponse directe**
> 
> Pour un revenu annuel net de 80 000 € (qui se situe dans la tranche « De 60 001 € à 100 000 € »), les montants maximaux d'indemnité journalière sont les suivants :
> 
> | Option | IJ maximale |
> |---|---|
> | **Option Standard** | **220 €/jour** |
> | **Option Premium** | **295 €/jour** |
> 
> ⚠️ Ces plafonds s'appliquent sous réserve que le montant souscrit soit bien défini dans vos **Conditions Particulières**, car c'est ce document qui fixe le montant retenu pour votre contrat spécifique.
> 
> ---
> 
> **Source(s)**
> 
> [Article 4.2 des CG Document visiteur — vupload] :
> > *« De 60 001 € à 100 000 € — IJ maximale (Option Standard) : 220 €/jour — IJ maximale (Option Premium) : 295 €/jour »*
> 
> Le même article précise également une **règle de cumul** : les indemnités perçues au titre du contrat, additionnées aux prestations des régimes obligatoires (Sécurité sociale, etc.), **ne peuvent pas dépasser 100 % du revenu net journalier habituel** de l'assuré, calculé sur les 12 derniers mois précédant le sinistre.
> 
> ---
> 
> **Point d'attention**
> 
> Deux nuances importantes à retenir :
> 
> 1. **Le montant effectif** de votre IJ n'est pas automatiquement égal au plafond : il est celui qui a été **souscrit dans vos Conditions Particulières**. Le tableau de l'article 4.2 fixe uniquement un *maximum* autorisé selon la tranche de revenu et l'option choisie.
> 2. **La règle des 100 %** peut conduire à une réduction des indemnités versées si, combinées aux prestations de la Sécurité sociale, elles dépassent votre revenu net journalier réel. Je vous recommande de vérifier ce point avec votre **référent produit ARESIA Assurances** pour simuler votre situation précise.

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A02 — Mistral · Q08

- **Moteur** : Mistral
- **Document** : CG-AV-MULTI-2024 — [contrat](contrats/CG-AV-MULTI-2024.md)
- **Question** : Quel est le montant minimum pour un versement complémentaire sur ARESIA Patrimoine+ ?

**Réponse :**

> **Réponse directe** :
> Le montant minimum pour un versement complémentaire libre sur le contrat **ARESIA Patrimoine+** est de **300 €**.
> 
> **Source(s)** :
> [Article 8 des CG ARESIA Patrimoine+ — v3.1]
> 
> **Point d'attention** :
> - Ce montant s'applique aux versements complémentaires **libres** (effectués à tout moment sans préavis).
> - Les versements programmés (mensuels, trimestriels ou annuels) ont des montants minimums différents (ex. : 100 €/mois pour un versement programmé mensuel).
> - Aucun frais n'est appliqué sur les versements complémentaires libres, mais des frais de gestion annuels (0,60 % pour le fonds euros, 0,80 % pour les unités de compte) impactent la performance nette [Article 9 des CG — v3.1].

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A03 — Mistral · Q06

- **Moteur** : Mistral
- **Document** : CG-PREV-INV-2024 — [contrat](contrats/CG-PREV-INV-2024.md)
- **Question** : Si un assuré reprend le travail pendant 3 semaines puis retombe en arrêt, doit-il resubir une franchise ?

**Réponse :**

> **Réponse directe** :
> Non, l'assuré n'a pas à subir une nouvelle franchise si la rechute survient dans les **30 jours suivant la reprise d'activité**. Cet arrêt est considéré comme la continuité du sinistre initial.
> 
> **Source(s)** :
> [Article 4.1 des CG — Document visiteur (UPLOAD-eval-2b5) — v{vupload}]
> *"En cas de rechute survenant dans les 30 jours suivant la reprise d'activité, l'arrêt est considéré comme la continuité du sinistre initial et aucune nouvelle franchise ne s'applique."*
> 
> **Point d'attention** :
> - La règle s'applique **uniquement** si la rechute intervient dans les **30 jours** après la reprise. Au-delà, une nouvelle franchise sera appliquée.
> - Vérifiez que la reprise d'activité a bien été **totale et effective** (pas de mi-temps thérapeutique ou activité partielle), car cela pourrait impacter l'appréciation du sinistre par l'assureur.
> - En cas de doute sur la durée exacte entre la reprise et la rechute, conservez les justificatifs médicaux et la date de reprise officielle (certificat de reprise du médecin traitant).

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A04 — Mistral · Q20

- **Moteur** : Mistral
- **Document** : CG-PREV-INV-2024 — [contrat](contrats/CG-PREV-INV-2024.md)
- **Question** : Quelle est la garantie obsèques incluse dans le contrat prévoyance ?

**Réponse :**

> **Réponse directe** :
> Les documents disponibles ne mentionnent pas explicitement une "garantie obsèques" incluse dans le contrat prévoyance ARESIA Assurances. Aucune référence à cette garantie, à son montant ou à ses conditions n'est présente dans les chunks fournis.
> 
> **Source(s)** :
> Aucune source pertinente identifiée dans les chunks fournis (Articles 1 à 21, CG Prévoyance v4.2).
> 
> **Point d'attention** :
> Je ne trouve pas cette information dans les documents disponibles. Je vous recommande de contacter votre référent produit ou le service technique de ARESIA Assurances pour obtenir des précisions sur l'existence et les modalités d'une garantie obsèques éventuelle. Les garanties évoquées dans les chunks se limitent à l'**ITT** (Incapacité Temporaire de Travail), l'**IPT/IPP** (Invalidité Permanente) et des exclusions générales, sans mention des frais d'obsèques.

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A05 — Claude · Q10

- **Moteur** : Claude
- **Document** : CG-AV-MULTI-2024 — [contrat](contrats/CG-AV-MULTI-2024.md)
- **Question** : Le fonds en euros ARESIA Sécurité garantit-il le capital investi ?

**Réponse :**

> **Réponse directe**
> 
> Oui, le fonds en euros ARESIA Sécurité garantit le capital investi. La garantie en capital est fixée à **100% du capital versé, net de frais sur versements**. Concrètement, cela signifie que le montant que vous avez effectivement placé sur ce fonds (après déduction des éventuels frais d'entrée) est intégralement protégé. Par ailleurs, les intérêts crédités chaque année sont **définitivement acquis** et s'ajoutent au capital garanti (effet cliquet).
> 
> À titre d'information, le taux de rendement servi en 2023 était de **2,80% net de frais de gestion**, avec une participation aux bénéfices minimale de **85%** des bénéfices techniques et financiers.
> 
> ---
> 
> **Source(s)**
> 
> - [Article 10 des CG ARESIA Patrimoine+ — v3.1] : *"Garantie en capital : 100% du capital versé net de frais sur versements"*
> - [Article 2 des CG ARESIA Patrimoine+ — v3.1] : *"Support en euros : Fonds général de l'assureur offrant une garantie en capital. Les intérêts crédités sont définitivement acquis."*
> 
> ---
> 
> **Point d'attention**
> 
> Deux nuances importantes à garder en tête :
> 
> 1. **La garantie porte sur le capital net de frais sur versements** : si des frais d'entrée s'appliquent (jusqu'à 4,5% selon le réseau, cf. Article 9), le montant garanti est calculé *après* déduction de ces frais, et non sur la totalité de votre versement brut.
> 
> 2. **Le taux de rendement n'est pas garanti d'une année sur l'autre** : le taux 2023 (2,80%) ne préjuge pas des taux futurs. De plus, ARESIA Assurances se réserve le droit de **limiter les versements sur le fonds euros** ou d'**imposer une diversification minimale en unités de compte** (supports non garantis, à risque de perte en capital). [Article 10.3 des CG ARESIA Patrimoine+ — v3.1]

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A06 — Mistral · Q01

- **Moteur** : Mistral
- **Document** : CG-PREV-INV-2024 — [contrat](contrats/CG-PREV-INV-2024.md)
- **Question** : Quelles sont les options de franchise disponibles sur le contrat prévoyance invalidité ?

**Réponse :**

> **Réponse directe** :
> Les options de franchise disponibles sur le contrat prévoyance invalidité d'ARESIA Assurances sont les suivantes :
> - **15 jours** (cotisation de base × 1,00)
> - **30 jours** (cotisation de base × 0,82)
> - **60 jours** (cotisation de base × 0,64)
> - **90 jours** (cotisation de base × 0,51)
> 
> **Source(s)** :
> [Article 4.1 des CG Prévoyance — v4.2]
> 
> **Point d'attention** :
> - La franchise s'applique **par sinistre** et non par année civile.
> - En cas de rechute dans les **30 jours suivant la reprise d'activité**, l'arrêt est considéré comme la continuité du sinistre initial : **aucune nouvelle franchise ne s'applique**.
> - Le choix de la franchise impacte directement le montant de la cotisation (réduction pour les franchises longues). Vérifiez votre option souscrite dans vos **Conditions Particulières**.

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A07 — Claude · Q12

- **Moteur** : Claude
- **Document** : CG-AV-MULTI-2024 — [contrat](contrats/CG-AV-MULTI-2024.md)
- **Question** : Combien coûte un arbitrage entre supports sur ARESIA Patrimoine+ ?

**Réponse :**

> **Réponse directe**
> 
> Les frais d'arbitrage entre supports sur ARESIA Patrimoine+ s'élèvent à **0,50% du montant arbitré, avec un minimum de 15 €** par opération d'arbitrage.
> 
> Toutefois, une exception importante existe : en mode **gestion libre**, les **4 premiers arbitrages par an sont gratuits** pour les souscripteurs bénéficiant du tarif partenaire conseiller.
> 
> ---
> 
> **Source(s)**
> 
> [Article 9 des CG ARESIA Patrimoine+ — v3.1 Mars 2024]
> > *"Frais d'arbitrage : 0,50% du montant arbitré (min. 15 €) — Gratuit pour 4 arbitrages/an en gestion libre"*
> 
> ---
> 
> **Point d'attention**
> 
> ⚠️ Au-delà des 4 arbitrages gratuits annuels (en gestion libre), le tarif standard de **0,50% du montant arbitré** s'applique, avec un **plancher de 15 €** minimum par opération, même pour de petits montants. Si vous envisagez des arbitrages fréquents, il peut être judicieux d'en tenir compte dans votre stratégie de gestion.

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A08 — Mistral · Q19

- **Moteur** : Mistral
- **Document** : ACPR-REC-2024-12 — [contrat](contrats/ACPR-REC-2024-12.md)
- **Question** : Combien d'heures de formation continue un conseiller doit-il suivre par an au titre de la DDA ?

**Réponse :**

> **Réponse directe** :
> Un conseiller doit suivre **15 heures minimum de formation continue par an** au titre de la Directive sur la Distribution d'Assurances (DDA).
> 
> **Source(s)** :
> - [Article 7 des CG — Document visiteur (UPLOAD-eval-08f) — v1]
> 
> **Point d'attention** :
> Ces 15 heures sont réparties par domaines obligatoires (ex. : 5h sur les produits/marchés, 4h sur la réglementation). Le non-respect de cette obligation expose à des sanctions de l'ACPR, incluant des amendes ou des interdictions d'exercer [Article 8 des CG — Document visiteur (UPLOAD-eval-08f) — v1]. Vérifiez que les formations suivies couvrent bien les thèmes imposés.

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A09 — Mistral · Q14

- **Moteur** : Mistral
- **Document** : BAR-IARD-2024-V2 — [contrat](contrats/BAR-IARD-2024-V2.md)
- **Question** : Quel est le plafond de RC Professionnelle pour un conseiller en gestion de patrimoine ?

**Réponse :**

> **Réponse directe** :
> Le plafond de garantie Responsabilité Civile Professionnelle (RC Pro) pour un conseiller en gestion de patrimoine (CGP) est de **1 500 000 € par sinistre** et de **3 000 000 € par an**, avec une franchise de **1 500 €**.
> 
> **Source(s)** :
> - [Article 3.1 des CG — Document visiteur (UPLOAD-eval-f32) — v2.0] : *"Professions financières (CGPI, CIF, CGP) : Plafond par sinistre 1 500 000 €, Plafond annuel 3 000 000 €, Franchise 1 500 €"*.
> - [Article 3.1.5 des CG — Document visiteur (UPLOAD-eval-f32) — v2.0] : *"Pour les Conseillers en Gestion de Patrimoine (CGP) [...] la couverture minimale légale de 1 500 000 € par sinistre est incluse dans la formule standard"*.
> 
> **Point d'attention** :
> - Ces plafonds sont des **maximums** par sinistre et par an, tous sinistres confondus. En cas de dépassement, la garantie ne s’appliquera plus pour les sinistres supplémentaires sur la même période.
> - La franchise de 1 500 € reste à la charge de l’assuré pour chaque sinistre couvert.
> - Vérifiez si votre activité nécessite une **extension de garantie** (ex. : couverture des préjudices financiers spécifiques), non incluse dans la formule standard. Contactez votre référent ARESIA pour adapter votre contrat.

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A10 — Mistral · Q16

- **Moteur** : Mistral
- **Document** : BAR-IARD-2024-V2 — [contrat](contrats/BAR-IARD-2024-V2.md)
- **Question** : La multirisque habitation couvre-t-elle le vol d'espèces au domicile et jusqu'à quel montant ?

**Réponse :**

> **Réponse directe** :
> Oui, la multirisque habitation ARESIA couvre le vol d'espèces au domicile, dans la limite d'un plafond de **5 000 €** par sinistre.
> 
> **Source(s)** :
> - [Article 1.1 des CG Multirisque Habitation — v2.0] : *"Vol et actes de vandalisme 30 000 € (meubles) / 5 000 € (espèces) 300 € [franchise]"*.
> 
> **Point d'attention** :
> - La franchise de **300 €** s'applique à ce sinistre (montant déduit de l'indemnisation).
> - Le vol doit être **constaté par dépôt de plainte** dans les **48 heures** suivant sa découverte, sous peine de déchéance de garantie [Article 4.1 des CG — v2.0].
> - Aucune extension de plafond n'est prévue pour les espèces dans les options listées (ex. : objets de valeur identifiés ne concernent que les biens matériels).

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A11 — Claude · Q17

- **Moteur** : Claude
- **Document** : ACPR-REC-2024-12 — [contrat](contrats/ACPR-REC-2024-12.md)
- **Question** : Quels éléments doit obligatoirement contenir le Document de Recueil des Informations et des Besoins ?

**Réponse :**

> **Réponse directe**
> 
> Le Document de Recueil des Informations et des Besoins (DRIB) doit obligatoirement contenir les éléments suivants :
> 
> 1. **L'identité complète** du client et du distributeur
> 2. **La date du recueil**
> 3. **La synthèse des informations collectées** : situation personnelle, objectifs et profil de risque du client
> 4. **L'analyse des besoins** réalisée
> 5. **La ou les recommandations formulées**, accompagnées de leur justification
> 6. **La mention explicite des produits étudiés mais non recommandés**, avec la raison de leur exclusion
> 7. **La signature du client**, attestant de la réception et de la compréhension du document
> 
> Par ailleurs, ce document doit être **remis au client avant la souscription**, sous format papier ou électronique avec accusé de réception.
> 
> ---
> 
> **Source(s)**
> 
> [Article 4 des CG Document visiteur — vupload]
> [Article 4.3 des CG Document visiteur — vupload]
> 
> ---
> 
> **Point d'attention**
> 
> L'assureur a une obligation de conservation stricte : le DRIB doit être archivé **pendant toute la durée du contrat et 5 ans après sa résiliation**, dans un système de gestion sécurisé et auditable. [Article 4.3 & Article 6 — Document visiteur — vupload]
> 
> De plus, les informations contenues dans ce document doivent être **mises à jour régulièrement** (au minimum tous les 2 ans, ou lors de tout événement contractuel significatif). [Article 2 — Document visiteur — vupload]

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A12 — Claude · Q13

- **Moteur** : Claude
- **Document** : BAR-IARD-2024-V2 — [contrat](contrats/BAR-IARD-2024-V2.md)
- **Question** : Quelle est la franchise en cas de bris de pare-brise avec un réparateur agréé ?

**Réponse :**

> **Réponse directe**
> 
> En cas de bris de pare-brise (bris de glace) avec passage par un **réparateur agréé**, la franchise applicable est de **0 €**. En revanche, si vous choisissez un réparateur non agréé, une franchise de **75 €** sera retenue.
> 
> ---
> 
> **Source(s)**
> 
> [Article 2.3 des CG Barème IARD — v2.0] :
> > *"Bris de glace (pare-brise) : 0 € après réparateur agréé | 75 € autre"*
> 
> ---
> 
> **Point d'attention**
> 
> ⚠️ Cette franchise à 0 € avec réparateur agréé s'applique à la **franchise standard**. Si vous souscrivez l'**option Zéro**, la franchise est également de 0 € quel que soit le réparateur choisi. Notez également que le bris de glace n'est pas disponible dans toutes les formules : il est inclus à partir de la **formule Tiers+** [Article 2.1 des CG Barème IARD — v2.0]. Pensez à vérifier votre formule souscrite avant d'engager des réparations, et à contacter votre référent ARESIA Assurances pour confirmer la liste des réparateurs agréés dans votre secteur.

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A13 — Claude · Q20

- **Moteur** : Claude
- **Document** : CG-PREV-INV-2024 — [contrat](contrats/CG-PREV-INV-2024.md)
- **Question** : Quelle est la garantie obsèques incluse dans le contrat prévoyance ?

**Réponse :**

> **Réponse directe**
> 
> Je ne trouve pas cette information dans les documents disponibles. Les chunks fournis portent exclusivement sur les garanties ITT (Incapacité Temporaire de Travail), IPT/IPP (Invalidité Permanente), les conditions d'adhésion, les exclusions générales et le champ d'application territorial. Aucune mention d'une garantie obsèques n'y figure.
> 
> Je vous recommande de contacter votre référent produit ou le service technique de ARESIA Assurances.
> 
> ---
> 
> **Source(s)**
> 
> Les documents consultés couvrent les articles 1 à 21 des Conditions Générales — Prévoyance Invalidité (Réf. : CG-PREV-INV-2024, Version 4.2 — Janvier 2024). Aucun de ces articles ne traite d'une garantie obsèques.
> 
> ---
> 
> **Point d'attention**
> 
> Il est possible que la garantie obsèques :
> - **ne soit pas incluse** dans ce contrat prévoyance (elle fait souvent l'objet d'un contrat dédié séparé),
> - **figure dans un autre document contractuel** non disponible dans les chunks fournis (conditions particulières, tableau des garanties, avenant spécifique).
> 
> Avant toute conclusion, vérifiez l'ensemble des documents remis lors de la souscription ou contactez directement **ARESIA Assurances** pour obtenir une réponse précise et opposable.

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A14 — Claude · Q03

- **Moteur** : Claude
- **Document** : CG-PREV-INV-2024 — [contrat](contrats/CG-PREV-INV-2024.md)
- **Question** : Combien de temps peut-on être indemnisé en arrêt de travail avant de basculer en invalidité ?

**Réponse :**

> **Réponse directe**
> 
> L'indemnisation au titre de l'arrêt de travail (ITT — Incapacité Temporaire de Travail) peut durer **au maximum 1 095 jours, soit 3 ans**, par sinistre et par assuré. Une fois ce plafond atteint, si l'assuré n'est toujours pas en mesure de reprendre son activité professionnelle, son dossier est **automatiquement orienté vers l'évaluation de la garantie Invalidité Permanente**, conformément aux articles 5 à 7 du contrat. Cette évaluation implique notamment un examen par le médecin conseil de l'assureur dans un délai de 45 jours ouvrés.
> 
> ---
> 
> **Source(s)**
> 
> - [Article 4.3 des CG Prévoyance Invalidité — v4.2] : *"La durée maximale d'indemnisation au titre de la garantie ITT est de 1 095 jours (soit 3 ans) par sinistre et par assuré, tous sinistres confondus sur la durée du contrat. Au-delà de cette durée, si l'assuré ne peut reprendre son activité professionnelle, le dossier est automatiquement orienté vers l'évaluation de la garantie Invalidité Permanente (Articles 5 à 7 des présentes)."*
> - [Article 6.1 des CG Prévoyance Invalidité — v4.2] : procédure d'évaluation du taux d'invalidité en 5 étapes, avec un délai d'examen de 45 jours ouvrés par le médecin conseil.
> 
> ---
> 
> **Point d'attention**
> 
> ⚠️ La durée de 1 095 jours s'entend **tous sinistres confondus sur la durée du contrat**, et non par événement isolé. Par ailleurs, le basculement vers la garantie Invalidité Permanente n'est pas automatiquement synonyme d'indemnisation : l'assuré doit atteindre un **taux d'invalidité fonctionnelle d'au moins 33%** pour ouvrir droit à une prestation (IPP à partir de 33%, IPT à partir de 66%). En dessous de ce seuil, aucune prestation n'est versée au titre de l'invalidité. [Article 6.2 des CG Prévoyance Invalidité — v4.2]

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A15 — Claude · Q14

- **Moteur** : Claude
- **Document** : BAR-IARD-2024-V2 — [contrat](contrats/BAR-IARD-2024-V2.md)
- **Question** : Quel est le plafond de RC Professionnelle pour un conseiller en gestion de patrimoine ?

**Réponse :**

> **Réponse directe**
> 
> Pour un Conseiller en Gestion de Patrimoine (CGP), les plafonds de RC Professionnelle sont les suivants :
> 
> - **Plafond par sinistre : 1 500 000 €**
> - **Plafond annuel : 3 000 000 €**
> - **Franchise : 1 500 €**
> 
> Ces plafonds s'appliquent à la catégorie "Professions financières (CGPI, CIF, CGP)". Il est également précisé que la couverture minimale de **1 500 000 € par sinistre** correspond à l'exigence légale imposée par l'ORIAS et l'AMF, et qu'elle est **incluse dans la formule standard**.
> 
> ---
> 
> **Source(s)**
> 
> - [Article 3.1 des CG Barème IARD — v2.0] — Tableau des plafonds par catégorie professionnelle, ligne "Professions financières (CGPI, CIF, CGP)"
> - [Article 3.1.5 des CG Barème IARD — v2.0] — Obligation de RC Pro pour les CGP et CIF en vertu des exigences ORIAS et AMF, couverture minimale légale de 1 500 000 € par sinistre incluse en formule standard
> 
> ---
> 
> **Point d'attention**
> 
> Ces plafonds sont des **maximums contractuels** : le plafond annuel de 3 000 000 € s'entend **tous sinistres confondus** sur l'année. Si plusieurs sinistres surviennent, leur cumul est limité à ce plafond annuel. Par ailleurs, la franchise de 1 500 € reste à la charge du professionnel à chaque sinistre. Si vous souhaitez des garanties supérieures à ces plafonds, il convient de vous rapprocher de votre référent produit ARESIA Assurances pour étudier d'éventuelles options de surplafonnement.

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A16 — Claude · Q04

- **Moteur** : Claude
- **Document** : CG-PREV-INV-2024 — [contrat](contrats/CG-PREV-INV-2024.md)
- **Question** : À partir de quel taux d'invalidité est-on reconnu en Invalidité Permanente Totale ?

**Réponse :**

> **Réponse directe**
> 
> L'Invalidité Permanente Totale (IPT) est reconnue à partir d'un taux d'invalidité fonctionnelle **supérieur ou égal à 66%**. Concrètement, le barème prévoit trois seuils distincts :
> 
> - **En dessous de 33%** : aucune prestation n'est versée
> - **Entre 33% et 65%** : l'assuré relève de l'IPP (Invalidité Permanente Partielle)
> - **Entre 66% et 99%** : l'assuré est reconnu en **IPT**, ouvrant droit à une rente mensuelle
> - **À 100%** : statut d'invalide absolu, avec une rente IPT majorée et une aide tierce personne
> 
> Cette reconnaissance est prononcée par le **médecin conseil de l'assureur**, après examen du dossier médical complet et, si nécessaire, expertise médicale contradictoire.
> 
> ---
> 
> **Source(s)**
> 
> - [Article 6 des CG Prévoyance Invalidité — v4.2] : seuil de 66% pour la reconnaissance IPT
> - [Article 6.2 des CG Prévoyance Invalidité — v4.2] : tableau complet du barème d'évaluation par tranches
> - [Article 1 des CG Prévoyance Invalidité — v4.2] : définition contractuelle de l'IPT
> 
> ---
> 
> **Point d'attention**
> 
> Le taux d'invalidité est évalué selon le **barème médical du CCSF** adopté par ARESIA Assurances, et non selon d'autres référentiels (Sécurité sociale, etc.). Ce barème est disponible sur simple demande au service médical de l'assureur. Par ailleurs, la reconnaissance de l'IPT intervient **après la date de consolidation** de l'état de santé de l'assuré, c'est-à-dire une fois que son état est stabilisé — ce critère est indispensable pour déclencher l'évaluation.

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A17 — Mistral · Q02

- **Moteur** : Mistral
- **Document** : CG-PREV-INV-2024 — [contrat](contrats/CG-PREV-INV-2024.md)
- **Question** : Quel est le montant maximum d'indemnité journalière pour quelqu'un qui gagne 80 000 € par an ?

**Réponse :**

> **Réponse directe** :
> Pour un revenu annuel net de **80 000 €**, le montant maximum d'indemnité journalière (IJ) est de :
> - **220 €/jour** en *Option Standard*,
> - **295 €/jour** en *Option Premium*.
> 
> **Source(s)** :
> [Article 4.2 des CG — Document visiteur (UPLOAD-eval-2b5) — v{vupload}]
> 
> **Point d'attention** :
> 1. **Plafond de cumul** : Le total des indemnités (contrat + régimes obligatoires) ne peut dépasser **100% du revenu net journalier habituel** de l'assuré (calculé sur les 12 derniers mois avant le sinistre). [Article 4.2]
> 2. **Option souscrite** : Le montant exact dépend de l'option choisie aux *Conditions Particulières* (non précisée dans votre question). Vérifiez votre contrat pour confirmer l'option applicable.
> 3. **Exclusions** : Aucune indemnité n'est versée pendant la *franchise* (délai de carence défini à l'Article 4.1).

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A18 — Mistral · Q18

- **Moteur** : Mistral
- **Document** : ACPR-REC-2024-12 — [contrat](contrats/ACPR-REC-2024-12.md)
- **Question** : Pendant combien de temps dois-je conserver le DRIB et le journal des interactions de conseil ?

**Réponse :**

> **Réponse directe** :
> Vous devez conserver le **DRIB (Document de Recueil des Informations et Besoins)** et le **journal des interactions de conseil** pendant **la durée du contrat + 5 ans**, sur un support sécurisé et traçable.
> 
> ---
> 
> **Source(s)** :
> - [Article 6 des CG *Document visiteur (UPLOAD-eval-08f)* — v1] : *"DRIB [...] Durée contrat + 5 ans"* et *"Journal des interactions de conseil [...] Durée contrat + 5 ans"*.
> - [Article 4.3 des CG *Document visiteur (UPLOAD-eval-08f)* — v1] : *"L'assureur doit conserver ce document [DRIB] pendant toute la durée du contrat et 5 ans après sa résiliation"*.
> 
> ---
> 
> **Point d'attention** :
> - Les supports de conservation doivent être **auditables** (pour le DRIB) et **horodatés/immuables** (pour le journal des interactions), conformément aux exigences de l'ACPR.
> - En cas de contrôle, l'absence de ces documents ou leur conservation insuffisante peut entraîner des sanctions (cf. [Article 8 des CG — v1]).
> - Les durées s'appliquent à partir de la **résiliation du contrat**, et non de la dernière interaction.

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A19 — Claude · Q09

- **Moteur** : Claude
- **Document** : CG-AV-MULTI-2024 — [contrat](contrats/CG-AV-MULTI-2024.md)
- **Question** : Peut-on faire une avance sur son contrat d'assurance vie et jusqu'à quel montant ?

**Réponse :**

> **Réponse directe**
> 
> Oui, le souscripteur peut demander une avance sur son contrat ARESIA Patrimoine+ à tout moment. Les plafonds sont les suivants :
> 
> - **Fonds euros** : jusqu'à **80% de la valeur de rachat** (c'est-à-dire 80% de ce que vous pourriez récupérer si vous clôturiez le contrat)
> - **Unités de compte** : jusqu'à **60% de la valeur de rachat**
> 
> Un montant **minimum de 1 500 €** est requis par avance.
> 
> Concernant les taux d'intérêt appliqués à l'avance :
> 
> | Durée | Taux annuel | Renouvellement |
> |-------|-------------|----------------|
> | 1 an | Taux OAT 10 ans + 1,5% | Renouvelable 2 fois |
> | 2 ans | Taux OAT 10 ans + 2% | Non renouvelable |
> | 3 ans (maximum) | Taux OAT 10 ans + 2,5% | Non renouvelable |
> 
> > 💡 **Bon à savoir** : L'avance n'est **pas un rachat**. Elle ne génère donc **aucune fiscalité** et ne remet pas à zéro l'ancienneté fiscale du contrat.
> 
> ---
> 
> **Source(s)**
> 
> [Article 15 et Article 15.4 des CG ARESIA Patrimoine+ — CG-AV-MULTI-2024 v3.1 — Mars 2024]
> 
> ---
> 
> **Point d'attention**
> 
> ⚠️ En cas de **non-remboursement à l'échéance**, l'avance est automatiquement **transformée en rachat partiel et devient fiscalisée** selon les règles applicables aux rachats (durée de détention, date des versements). Cela peut avoir un impact fiscal significatif. Pour toute question sur les conséquences fiscales d'un tel scénario, ARESIA Assurances recommande de consulter un **conseiller fiscal ou un notaire** [Article 23.3 des CG ARESIA Patrimoine+ — v3.1].

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A20 — Claude · Q07

- **Moteur** : Claude
- **Document** : CG-AV-MULTI-2024 — [contrat](contrats/CG-AV-MULTI-2024.md)
- **Question** : Quelle est la fiscalité d'un rachat partiel sur une assurance vie ouverte il y a 10 ans ?

**Réponse :**

> **Réponse directe**
> 
> Pour un contrat ouvert il y a 10 ans (donc **de plus de 8 ans**), la fiscalité d'un rachat partiel s'applique comme suit — seule la part des **plus-values** (intérêts et gains) est imposable, jamais le capital versé :
> 
> **Selon la date de versement des primes :**
> 
> | Primes versées **avant septembre 2017** | Primes versées **après septembre 2017** |
> |---|---|
> | 7,5% d'IR après abattement + 17,2% de prélèvements sociaux | 7,5% d'IR après abattement (si encours < 150 000 €) + 17,2% PS |
> | Au-delà de 150 000 € : 7,5% jusqu'au seuil + **12,8% au-delà** + PS | Même règle — seuil de 150 000 € tous contrats confondus |
> 
> **Les abattements applicables après 8 ans :**
> - **4 600 €/an** pour une personne seule
> - **9 200 €/an** pour un couple soumis à imposition commune
> *(tous contrats d'assurance vie confondus)*
> 
> ---
> 
> **Source(s)**
> 
> - [Article 23 des CG ARESIA Patrimoine+ — v3.1] : tableau de fiscalité des rachats selon la durée et la date des versements
> - [Article 23.1 des CG ARESIA Patrimoine+ — v3.1] : montants des abattements après 8 ans (4 600 € / 9 200 €), précisés comme susceptibles d'évoluer selon la législation fiscale en vigueur
> - [Article 2 des CG ARESIA Patrimoine+ — v3.1] : définition des prélèvements sociaux (CSG, CRDS et prélèvements annexes)
> 
> ---
> 
> **Point d'attention**
> 
> ⚠️ Trois nuances importantes à ne pas négliger :
> 
> 1. **Seuil des 150 000 €** : il s'apprécie **tous contrats d'assurance vie confondus**, pas uniquement sur ce contrat.
> 2. **Date des versements** : si le contrat mélange des primes versées avant et après septembre 2017, les deux régimes fiscaux s'appliquent **en proportion**, ce qui peut complexifier le calcul.
> 3. **Conseil fiscal fortement recommandé** : comme le précise [Article 23.3 des CG ARESIA Patrimoine+ — v3.1], *"la fiscalité de l'assurance vie est complexe et personnelle"*. ARESIA Assurances recommande vivement de consulter **un conseiller fiscal ou un notaire** avant toute décision de rachat ayant un impact fiscal significatif. Les informations ci-dessus sont données **à titre indicatif** et ne constituent pas un conseil fiscal personnalisé.

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A21 — Mistral · Q11

- **Moteur** : Mistral
- **Document** : CG-AV-MULTI-2024 — [contrat](contrats/CG-AV-MULTI-2024.md)
- **Question** : Un conjoint bénéficiaire d'une assurance vie est-il exonéré de droits de succession ?

**Réponse :**

> **Réponse directe** :
> Oui, le conjoint (ou partenaire de PACS) bénéficiaire d'un contrat d'assurance vie ARESIA Patrimoine+ est **totalement exonéré de toute taxation** sur les capitaux décès, **quel que soit le montant ou la date des versements**.
> 
> ---
> 
> **Source(s)** :
> [Article 24.2 des CG *ARESIA Patrimoine+* — v3.1]
> 
> ---
> 
> **Point d'attention** :
> - Cette exonération s'applique **uniquement** au conjoint ou partenaire de PACS, **pas aux autres bénéficiaires** (enfants, tiers, etc.), qui restent soumis aux règles d'abattement et de taxation précisées à l'Article 24.
> - L'exonération concerne **uniquement la fiscalité** des capitaux décès. Les règles successorales (réserve héréditaire, etc.) ou les éventuelles dettes de l'assuré ne sont pas couvertes par cette disposition. Pour une analyse complète, consultez un notaire ou un conseiller fiscal.

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A22 — Claude · Q11

- **Moteur** : Claude
- **Document** : CG-AV-MULTI-2024 — [contrat](contrats/CG-AV-MULTI-2024.md)
- **Question** : Un conjoint bénéficiaire d'une assurance vie est-il exonéré de droits de succession ?

**Réponse :**

> **Réponse directe**
> 
> Oui. Selon les conditions générales du contrat ARESIA Patrimoine+, le conjoint ou le partenaire de PACS désigné comme bénéficiaire en cas de décès est **totalement exonéré de toute taxation** sur les capitaux décès d'assurance vie, et ce **quel que soit le montant transmis et la date des versements** (qu'ils aient été effectués avant ou après 70 ans).
> 
> ---
> 
> **Source(s)**
> 
> > [Article 24.2 des CG ARESIA Patrimoine+ — v3.1 Mars 2024] :
> > *« Le conjoint ou partenaire de PACS bénéficiaire est totalement exonéré de toute taxation sur les capitaux décès d'assurance vie, quel que soit le montant et la date des versements. »*
> 
> À titre de contexte, le même article rappelle que pour les autres bénéficiaires, la fiscalité applicable dépend de l'âge auquel les versements ont été effectués :
> - **Primes versées avant 70 ans** : abattement de 152 500 € par bénéficiaire, puis taxation à 20 % jusqu'à 852 500 €, et 31,25 % au-delà.
> - **Primes versées après 70 ans** : abattement global de 30 500 € (tous bénéficiaires confondus), puis droits de succession ordinaires sur le surplus.
> 
> > [Article 24 des CG ARESIA Patrimoine+ — v3.1 Mars 2024]
> 
> ---
> 
> **Point d'attention**
> 
> ⚠️ Cette exonération concerne uniquement la **fiscalité assurance vie** (hors droits de succession). Les règles successorales (réserve héréditaire, primes manifestement exagérées, etc.) relèvent d'un cadre juridique distinct et peuvent avoir des implications spécifiques selon votre situation familiale et patrimoniale. Conformément à l'Article 23.3 des CG, **ARESIA Assurances recommande vivement de consulter un notaire ou un conseiller fiscal** avant toute décision ayant un impact fiscal ou successoral significatif.

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A23 — Mistral · Q09

- **Moteur** : Mistral
- **Document** : CG-AV-MULTI-2024 — [contrat](contrats/CG-AV-MULTI-2024.md)
- **Question** : Peut-on faire une avance sur son contrat d'assurance vie et jusqu'à quel montant ?

**Réponse :**

> **Réponse directe** :
> Oui, vous pouvez demander une avance sur votre contrat d’assurance vie ARESIA Patrimoine+. Le montant maximal de l’avance est de **80 % de la valeur de rachat pour le fonds en euros** et de **60 % pour les unités de compte**, avec un **minimum de 1 500 € par avance**. L’avance n’est pas fiscalisée et n’interrompt pas l’antériorité fiscale du contrat.
> 
> ---
> 
> **Source(s)** :
> - [Article 15 des CG *ARESIA Patrimoine+* — v3.1] : *"Le souscripteur peut demander une avance sur son contrat à tout moment, dans la limite de 80% de la valeur de rachat pour le fonds euros et 60% pour les unités de compte, avec un minimum de 1 500 € par avance."*
> - [Article 15.4 des CG *ARESIA Patrimoine+* — v3.1] : *"L'avance ne constitue pas un rachat et n'est pas fiscalisée. Elle n'interrompt pas l'antériorité fiscale du contrat. En cas de non-remboursement à l'échéance, l'avance est transformée en rachat partiel et fiscalisée en conséquence."*
> 
> ---
> 
> **Point d'attention** :
> 1. **Non-remboursement** : Si l’avance n’est pas remboursée à l’échéance, elle est automatiquement transformée en **rachat partiel**, ce qui peut entraîner une **fiscalité** sur les plus-values (selon la durée du contrat et la date des primes). Consultez un conseiller fiscal pour évaluer l’impact.
> 2. **Taux d’intérêt** : L’avance est soumise à un taux d’intérêt annuel (ex. : OAT 10 ans + 1,5 % pour 1 an), qui peut varier selon la durée choisie. Vérifiez les conditions avant de souscrire.
> 3. **Limite de renouvellement** : Une avance de 1 an est renouvelable **2 fois maximum**, tandis que les avances de 2 ou 3 ans ne sont pas renouvelables.
> 4. **Valeur des UC** : Pour les unités de compte, le montant de l’avance dépend de leur valeur à la date de demande, qui peut fluctuer (risque de perte en capital). [Article 1.2 des CG — v3.1].

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A24 — Claude · Q18

- **Moteur** : Claude
- **Document** : ACPR-REC-2024-12 — [contrat](contrats/ACPR-REC-2024-12.md)
- **Question** : Pendant combien de temps dois-je conserver le DRIB et le journal des interactions de conseil ?

**Réponse :**

> **Réponse directe**
> 
> Le DRIB et le journal des interactions de conseil doivent tous deux être conservés pendant **la durée du contrat + 5 ans après sa résiliation/fin**. Concernant le support, les recommandations sont les suivantes :
> - **DRIB** : système de gestion sécurisé avec accès auditable
> - **Journal des interactions de conseil** : base de données horodatée et immuable (archivage électronique NF Z42-013 recommandé)
> 
> ---
> 
> **Source(s)**
> 
> - [Article 6 — Durées de conservation — Document visiteur (UPLOAD-eval-08f) vupload] : *"DRIB — Durée contrat + 5 ans — Système de gestion sécurisé, accès auditable"* et *"Journal des interactions de conseil — Durée contrat + 5 ans — Base de données horodatée et immuable"*
> - [Article 4.3 — Document visiteur (UPLOAD-eval-08f) vupload] : *"L'assureur doit conserver ce document pendant toute la durée du contrat et 5 ans après sa résiliation."*
> 
> ---
> 
> **Point d'attention**
> 
> Le non-respect des durées de conservation peut être considéré comme un manquement aux obligations de traçabilité et exposer le distributeur à des sanctions de l'ACPR, potentiellement très lourdes [Article 8 — Document visiteur (UPLOAD-eval-08f) vupload]. Veillez également à ce que les systèmes de stockage utilisés respectent les exigences techniques mentionnées (horodatage, immuabilité, auditabilité) pour être conformes en cas de contrôle.

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A25 — Claude · Q06

- **Moteur** : Claude
- **Document** : CG-PREV-INV-2024 — [contrat](contrats/CG-PREV-INV-2024.md)
- **Question** : Si un assuré reprend le travail pendant 3 semaines puis retombe en arrêt, doit-il resubir une franchise ?

**Réponse :**

> **Réponse directe**
> 
> Dans le cas décrit — reprise du travail pendant 3 semaines (21 jours) puis nouvel arrêt — **une nouvelle franchise s'applique**.
> 
> En effet, le contrat prévoit que l'arrêt est considéré comme la continuité du sinistre initial (et donc sans nouvelle franchise) **uniquement si la rechute survient dans les 30 jours suivant la reprise d'activité**.
> 
> Or, une reprise de 3 semaines (21 jours) reste bien dans cette fenêtre de 30 jours. **Aucune nouvelle franchise ne s'appliquerait donc dans ce cas précis** : le nouvel arrêt serait traité comme la suite du sinistre initial.
> 
> > 💡 Pour être clair : 21 jours < 30 jours → la rechute est dans le délai → **pas de nouvelle franchise**.
> 
> ---
> 
> **Source(s)**
> 
> > *"En cas de rechute survenant dans les 30 jours suivant la reprise d'activité, l'arrêt est considéré comme la continuité du sinistre initial et aucune nouvelle franchise ne s'applique."*
> > **[Article 4.1 des CG Document visiteur — vupload]**
> 
> > *"La franchise est calculée par sinistre et non par année civile."*
> > **[Article 4.1 des CG Document visiteur — vupload]**
> 
> ---
> 
> **Point d'attention**
> 
> ⚠️ Le seuil de **30 jours est strictement encadré** : si la reprise d'activité avait duré **31 jours ou plus**, le nouvel arrêt constituerait un **nouveau sinistre** et la franchise contractuelle (15, 30, 60 ou 90 jours selon les Conditions Particulières de l'assuré) s'appliquerait à nouveau depuis le premier jour du nouvel arrêt. Il convient donc de vérifier précisément la date de reprise et la date du nouvel arrêt pour qualifier correctement la situation.

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A26 — Mistral · Q17

- **Moteur** : Mistral
- **Document** : ACPR-REC-2024-12 — [contrat](contrats/ACPR-REC-2024-12.md)
- **Question** : Quels éléments doit obligatoirement contenir le Document de Recueil des Informations et des Besoins ?

**Réponse :**

> **Réponse directe** :
> Le Document de Recueil des Informations et des Besoins (DRIB) doit obligatoirement contenir les éléments suivants :
> 1. Identité complète du client et du distributeur.
> 2. Date du recueil.
> 3. Synthèse des informations collectées (situation personnelle, professionnelle, patrimoniale, objectifs, profil de risque, situation fiscale et couvertures existantes).
> 4. Analyse des besoins réalisée.
> 5. Recommandation(s) formulée(s) avec leur justification.
> 6. Mention explicite des produits étudiés mais non recommandés, avec la raison de leur exclusion.
> 7. Signature du client attestant de la réception et de la compréhension du document.
> 
> **Source(s)** :
> - [Article 4 des CG (Document visiteur — UPLOAD-eval-08f) — v non précisée]
> - [Article 1 des CG (Document visiteur — UPLOAD-eval-08f) — v non précisée]
> 
> **Point d'attention** :
> Le DRIB doit être remis au client **avant la souscription**, sous format papier ou électronique avec accusé de réception. L'absence de signature du client ou l'omission d'un élément obligatoire (comme la justification des produits non recommandés) peut entraîner un manquement aux obligations de conseil, exposant le distributeur à des sanctions (ex. : avertissement, sanction pécuniaire) [Article 8 des CG]. Une mise à jour régulière des informations est également requise (tous les 2 ans ou en cas de changement significatif) [Article 2 des CG].

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A27 — Mistral · Q05

- **Moteur** : Mistral
- **Document** : CG-PREV-INV-2024 — [contrat](contrats/CG-PREV-INV-2024.md)
- **Question** : Le burn-out est-il couvert par le contrat prévoyance invalidité ?

**Réponse :**

> **Réponse directe** :
> Oui, le burn-out est couvert par le contrat prévoyance invalidité d’ARESIA Assurances **sous certaines conditions** :
> - Pour la garantie **Incapacité Temporaire de Travail (ITT)** : le burn-out est couvert sans exclusion temporaire si l’adhérent a fourni un questionnaire médical favorable **et** souscrit avant toute prescription médicale liée à cette pathologie.
> - Pour la garantie **Invalidité Permanente Totale (IPT)** : le burn-out (affection psychiatrique) est couvert sans limitation de durée **uniquement si l’assuré a souscrit l’option Premium**, sous réserve d’un suivi psychiatrique régulier et d’un taux d’invalidité ≥ 66 % reconnu par le médecin conseil.
> 
> ---
> 
> **Source(s)** :
> - [Article 13.5 des CG Prévoyance — v4.2] : *« Les pathologies psychiatriques et le burn-out sont couverts sans exclusion temporaire pour les adhérents ayant fourni un questionnaire médical de santé favorable et souscrit avant toute prescription médicale liée à ces pathologies. »*
> - [Article 5.1 des CG Prévoyance — v4.2] : *« Les affections psychiatriques (dépression, burn-out, troubles anxieux) sont couvertes sans limitation de durée spécifique pour les assurés ayant souscrit l'option Premium, sous réserve d'un suivi psychiatrique régulier attesté. »*
> - [Article 6 des CG Prévoyance — v4.2] : *« La garantie IPT est acquise lorsque le médecin conseil de l'assureur reconnaît un taux d'invalidité fonctionnelle supérieur ou égal à 66%. »*
> 
> ---
> 
> **Point d'attention** :
> 1. **Questionnaire médical obligatoire** : La couverture du burn-out en ITT dépend de la déclaration préalable d’un état de santé favorable (sans symptômes ni diagnostic antérieur). Une omission ou une fausse déclaration peut entraîner un refus de prise en charge [Article 13.5].
> 2. **Option Premium requise pour l’IPT** : Sans cette option, le burn-out peut être soumis à une surprime ou une exclusion spécifique après avis du médecin conseil [Article 5.1].
> 3. **Suivi psychiatrique** : Pour l’option Premium, la continuité des soins est une condition sine qua non pour le maintien des prestations [Article 5.1].
> 4. **Délai d’évaluation** : La reconnaissance de l’IPT (taux ≥ 66 %) peut prendre jusqu’à 45 jours ouvrés après transmission du dossier complet [Article 6.1]. En cas de contestation, une expertise contradictoire est possible [Article 6.3].
> 5. **Reprise d’activité** : La rente IPT est suspendue si l’assuré reprend une activité générant plus de 30 % de son revenu pré-sinistre pendant 6 mois consécutifs [Article 7.2].

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A28 — Claude · Q01

- **Moteur** : Claude
- **Document** : CG-PREV-INV-2024 — [contrat](contrats/CG-PREV-INV-2024.md)
- **Question** : Quelles sont les options de franchise disponibles sur le contrat prévoyance invalidité ?

**Réponse :**

> **Réponse directe**
> 
> Le contrat prévoyance invalidité ARESIA Assurances propose **4 options de franchise**, correspondant chacune à un délai de carence et à un impact sur la cotisation :
> 
> | Option franchise | Délai de carence | Multiplicateur de cotisation |
> |---|---|---|
> | Franchise 15 jours | 15 jours consécutifs | × 1,00 (cotisation de base) |
> | Franchise 30 jours | 30 jours consécutifs | × 0,82 |
> | Franchise 60 jours | 60 jours consécutifs | × 0,64 |
> | Franchise 90 jours | 90 jours consécutifs | × 0,51 |
> 
> > 💡 *La franchise correspond au nombre de jours d'arrêt continu à partir duquel l'assureur commence à verser les indemnités journalières.*
> 
> L'option retenue est celle définie aux **Conditions Particulières** de votre contrat.
> 
> ---
> 
> **Source(s)**
> 
> - [Article 4.1 des CG Prévoyance Invalidité — v4.2] : tableau des options de franchise et leurs impacts sur la cotisation
> - [Article 1 des CG Prévoyance Invalidité — v4.2] : définition de la notion de franchise
> - [Article 4 des CG Prévoyance Invalidité — v4.2] : conditions de déclenchement de la garantie ITT en lien avec la franchise choisie
> 
> ---
> 
> **Point d'attention**
> 
> Deux règles importantes à retenir concernant l'application de la franchise :
> 
> 1. **La franchise est calculée par sinistre**, et non par année civile — chaque nouvel arrêt de travail fait repartir le délai de carence.
> 2. **Règle de rechute** : si l'assuré reprend son activité puis subit un nouvel arrêt **dans les 30 jours suivant la reprise**, cet arrêt est considéré comme la **continuité du sinistre initial** — aucune nouvelle franchise ne s'applique dans ce cas. [Article 4.1 des CG Prévoyance Invalidité — v4.2]
> 
> ⚠️ Par ailleurs, la franchise est **non rachetable**, sauf mention contraire expressément stipulée dans vos Conditions Particulières. [Article 1 des CG Prévoyance Invalidité — v4.2]

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A29 — Claude · Q19

- **Moteur** : Claude
- **Document** : ACPR-REC-2024-12 — [contrat](contrats/ACPR-REC-2024-12.md)
- **Question** : Combien d'heures de formation continue un conseiller doit-il suivre par an au titre de la DDA ?

**Réponse :**

> **Réponse directe**
> 
> Un conseiller (ou tout distributeur d'assurance) doit suivre un minimum de **15 heures de formation continue par an** au titre de la DDA. Cette obligation s'applique à toute personne physique intervenant dans la distribution, y compris les mandataires et sous-agents.
> 
> Ces 15 heures se répartissent indicativement comme suit :
> - **Produits et marchés d'assurance** : 5 heures/an
> - **Réglementation et conformité** (DDA, RGPD, LAB-FT, Solvabilité II) : 4 heures/an
> - **Compétences relationnelles** (gestion des réclamations, communication client) : 3 heures/an
> - **Prévention des conflits d'intérêts** : 2 heures/an
> - **Éthique professionnelle** : 1 heure/an
> 
> ---
> 
> **Source(s)**
> 
> [Article 7 — Document visiteur (UPLOAD-eval-08f) — vupload]
> 
> ---
> 
> **Point d'attention**
> 
> ⚠️ Le document source utilisé est explicitement identifié comme **entièrement fictif**, créé à des fins de démonstration (mention visible en Article 8 du même document). Ces informations **ne constituent pas une référence réglementaire officielle**. Pour connaître les obligations exactes et actuellement en vigueur au titre de la DDA, je vous recommande de consulter directement la réglementation française en vigueur (ordonnance n° 2018-361 du 16 mai 2018 et ses textes d'application) ou de contacter **votre référent produit ou le service technique de ARESIA Assurances**.

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A30 — Claude · Q08

- **Moteur** : Claude
- **Document** : CG-AV-MULTI-2024 — [contrat](contrats/CG-AV-MULTI-2024.md)
- **Question** : Quel est le montant minimum pour un versement complémentaire sur ARESIA Patrimoine+ ?

**Réponse :**

> **Réponse directe**
> 
> Le montant minimum pour un versement complémentaire libre sur le contrat ARESIA Patrimoine+ est de **300 €**, effectuable à tout moment et sans préavis. Si vous optez pour des versements programmés, les minimums diffèrent selon la périodicité choisie : 100 €/mois, 250 €/trimestre ou 1 000 €/an.
> 
> ---
> 
> **Source(s)**
> 
> [Article 8 des CG ARESIA Patrimoine+ — v3.1, Mars 2024] — Tableau récapitulatif des versements :
> - Versement complémentaire libre : **300 €** minimum, à tout moment, sans préavis
> - Versement programmé mensuel : **100 €/mois**
> - Versement programmé trimestriel : **250 €/trimestre**
> - Versement programmé annuel : **1 000 €/an**
> 
> ---
> 
> **Point d'attention**
> 
> Pour rappel, le versement initial à l'ouverture du contrat est soumis à un minimum distinct de **1 000 €** [Article 8 des CG ARESIA Patrimoine+ — v3.1]. Par ailleurs, des frais sur versements peuvent s'appliquer (de 0% à 4,5% selon le réseau), **sauf pour les versements programmés en tarif partenaire conseiller, qui en sont exonérés** [Article 9 des CG ARESIA Patrimoine+ — v3.1]. Pensez à vérifier les conditions tarifaires applicables à votre situation avec votre conseiller.

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A31 — Claude · Q15

- **Moteur** : Claude
- **Document** : BAR-IARD-2024-V2 — [contrat](contrats/BAR-IARD-2024-V2.md)
- **Question** : Dans quel délai doit-on déclarer un cambriolage à son assureur ?

**Réponse :**

> **Réponse directe**
> 
> En cas de cambriolage (vol), vous disposez de **48 heures après constat** pour déclarer le sinistre à votre assureur. Cette déclaration doit obligatoirement être accompagnée d'un **dépôt de plainte** préalable auprès des autorités compétentes (police ou gendarmerie).
> 
> ---
> 
> **Source(s)**
> 
> [Article 4.1 des CG Document visiteur (UPLOAD-eval-f32) — vupload]
> > *"Vol / Cambriolage : 48 heures après constat — Dépôt de plainte obligatoire + déclaration"*
> 
> ---
> 
> **Point d'attention**
> 
> Le dépôt de plainte n'est pas une simple formalité : il constitue une **condition obligatoire** pour l'ouverture de votre dossier sinistre. Sans ce document, votre déclaration pourrait être irrecevable. Par ailleurs, le délai de 48 heures est particulièrement court — pensez à agir rapidement dès la constatation du vol, même si l'inventaire complet des biens dérobés n'est pas encore finalisé. Vous pourrez compléter votre déclaration ultérieurement.

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A32 — Mistral · Q03

- **Moteur** : Mistral
- **Document** : CG-PREV-INV-2024 — [contrat](contrats/CG-PREV-INV-2024.md)
- **Question** : Combien de temps peut-on être indemnisé en arrêt de travail avant de basculer en invalidité ?

**Réponse :**

> **Réponse directe** :
> La durée maximale d'indemnisation en arrêt de travail (ITT) est de **1 095 jours (soit 3 ans)** par sinistre et par assuré. Au-delà de cette période, si l'assuré ne peut reprendre son activité professionnelle, son dossier est automatiquement orienté vers l'évaluation de la garantie **Invalidité Permanente** (IPT ou IPP).
> 
> ---
> 
> **Source(s)** :
> - [Article 4.3 des CG Prévoyance Invalidité — v4.2] : *"La durée maximale d'indemnisation au titre de la garantie ITT est de 1 095 jours (soit 3 ans) par sinistre et par assuré, tous sinistres confondus sur la durée du contrat. Au-delà de cette durée, si l'assuré ne peut reprendre son activité professionnelle, le dossier est automatiquement orienté vers l'évaluation de la garantie Invalidité Permanente (Articles 5 à 7 des présentes)."*
> 
> ---
> 
> **Point d'attention** :
> 1. **Cumul des sinistres** : La durée de 3 ans s’applique *tous sinistres confondus* sur la durée du contrat (ex. : un nouvel arrêt pour une cause différente ne rouvre pas un nouveau délai de 3 ans).
> 2. **Transition vers l’invalidité** : Le basculement en invalidité n’est pas automatique. Il nécessite une **évaluation médicale** par le médecin conseil d’ARESIA (Article 6.1) pour déterminer le taux d’invalidité (IPT ≥ 66% ou IPP entre 33% et 65%).
> 3. **Franchise** : La période d’indemnisation ne commence qu’après la franchise contractuelle (délai non rachetable sauf mention contraire aux Conditions Particulières). Vérifiez sa durée dans votre contrat.

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A33 — Mistral · Q12

- **Moteur** : Mistral
- **Document** : CG-AV-MULTI-2024 — [contrat](contrats/CG-AV-MULTI-2024.md)
- **Question** : Combien coûte un arbitrage entre supports sur ARESIA Patrimoine+ ?

**Réponse :**

> **Réponse directe** :
> Les frais d'arbitrage entre supports sur le contrat **ARESIA Patrimoine+** s'élèvent à **0,50 % du montant arbitré**, avec un **minimum de 15 € par arbitrage**. En gestion libre, **4 arbitrages par an sont gratuits**.
> 
> ---
> 
> **Source(s)** :
> - [Article 9.4 des CG *ARESIA Patrimoine+* — v3.1] : *"Frais d'arbitrage : 0,50 % du montant arbitré (min. 15 €). Gratuit pour 4 arbitrages/an en gestion libre."*
> 
> ---
> 
> **Point d'attention** :
> - Les frais d'arbitrage sont prélevés **automatiquement sur le montant arbitré** et réduisent donc le capital réinvesti.
> - Au-delà de 4 arbitrages annuels en gestion libre, chaque opération supplémentaire est facturée.
> - Les arbitrages entre supports en unités de compte (UC) et fonds euros peuvent être soumis à des **délais de valorisation** (ex. : 6 mois pour les SCPI) ou à des **frais spécifiques** non détaillés ici. Vérifiez l'Annexe 4 des CG pour les supports concernés.

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A34 — Mistral · Q15

- **Moteur** : Mistral
- **Document** : BAR-IARD-2024-V2 — [contrat](contrats/BAR-IARD-2024-V2.md)
- **Question** : Dans quel délai doit-on déclarer un cambriolage à son assureur ?

**Réponse :**

> **Réponse directe** :
> Un cambriolage doit être déclaré à votre assureur **dans un délai de 48 heures après le constat du sinistre**, avec l'obligation de déposer une plainte.
> 
> **Source(s)** :
> [Article 4.1 des CG — Document visiteur (UPLOAD-eval-f32) — v2.0]
> 
> **Point d'attention** :
> - Le dépôt de plainte est **obligatoire** pour valider la déclaration. Sans ce document, la garantie pourrait être refusée.
> - Le délai de 48 heures court à partir du **constat du vol**, et non de la découverte du sinistre si celui-ci est différé (ex. : retour de vacances). En cas de dépassement, vérifiez les conséquences avec votre assureur, car un retard peut entraîner une réduction ou un refus d'indemnisation.

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A35 — Mistral · Q07

- **Moteur** : Mistral
- **Document** : CG-AV-MULTI-2024 — [contrat](contrats/CG-AV-MULTI-2024.md)
- **Question** : Quelle est la fiscalité d'un rachat partiel sur une assurance vie ouverte il y a 10 ans ?

**Réponse :**

> **Réponse directe** :
> Pour un rachat partiel sur un contrat d’assurance vie ouvert il y a **10 ans** (donc détenu depuis plus de 8 ans), la fiscalité applicable aux **plus-values** (intérêts et gains) dépend de la date de versement des primes :
> - **Primes versées avant septembre 2017** :
>   - **7,5 %** d’impôt sur le revenu (IR) **après abattement** (4 600 € pour une personne seule / 9 200 € pour un couple) + **17,2 %** de prélèvements sociaux (PS).
>   - Si le contrat dépasse **150 000 €** (tous contrats confondus), la part des plus-values au-delà de ce seuil est taxée à **12,8 %** (au lieu de 7,5 %) + PS.
> - **Primes versées après septembre 2017** :
>   - **7,5 %** d’IR après abattement (mêmes seuils) + **17,2 %** de PS, **uniquement si le contrat est < 150 000 €**.
>   - Au-delà de 150 000 €, **12,8 %** d’IR sur la fraction excédentaire + PS.
> 
> **Source(s)** :
> - [Article 23 des CG ARESIA Patrimoine+ — v3.1] : *"Durée contrat > 8 ans : 7,5% IR après abattement + 17,2% PS (contrat < 150 k€) / 7,5% IR sur 150 k€ + 12,8% au-delà + PS (contrat > 150 k€)."*
> - [Article 23.1 des CG ARESIA Patrimoine+ — v3.1] : *"Abattements après 8 ans : 4 600 € (personne seule) ou 9 200 € (couple), par an et tous contrats confondus."*
> - [Article 23 des CG ARESIA Patrimoine+ — v3.1] : *"Primes versées avant 09/2017 : 35% IR ou barème progressif + PS si < 4 ans ; 15% IR ou barème + PS si 4-8 ans ; 7,5% IR après abattement + PS si > 8 ans."*
> 
> **Point d'attention** :
> 1. **Abattement annuel** : Les seuils de 4 600 €/9 200 € s’appliquent **par an et tous contrats confondus** (pas par contrat). Un rachat en décembre et un autre en janvier peuvent optimiser l’usage de l’abattement.
> 2. **Seuil de 150 000 €** : Ce plafond concerne **l’ensemble des contrats d’assurance vie** du souscripteur (pas seulement ARESIA). Vérifiez le montant total de vos encours avant un rachat.
> 3. **Complexité fiscale** : La fiscalité dépend de la date des versements, du montant du contrat, et de votre situation personnelle. [Article 23.3 des CG ARESIA Patrimoine+ — v3.1] recommande de **consulter un conseiller fiscal ou un notaire** pour une simulation précise.
> 4. **Prélèvements sociaux** : Les 17,2 % de PS s’appliquent **même en cas d’abattement non utilisé** (ils ne sont pas réduits par l’abattement IR).

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A36 — Mistral · Q13

- **Moteur** : Mistral
- **Document** : BAR-IARD-2024-V2 — [contrat](contrats/BAR-IARD-2024-V2.md)
- **Question** : Quelle est la franchise en cas de bris de pare-brise avec un réparateur agréé ?

**Réponse :**

> **Réponse directe** :
> La franchise en cas de bris de pare-brise avec un réparateur agréé est de **0 €**.
> 
> **Source(s)** :
> - [Article 2.3 des CG Automobiles 2024 — v2024] : *"Bris de glace (pare-brise) : 0 € après réparateur agréé | 75 €"*.
> 
> **Point d'attention** :
> - La franchise de **0 €** s'applique **uniquement** si la réparation est effectuée par un réparateur agréé par ARESIA. Dans le cas contraire, une franchise de **75 €** reste applicable pour les autres vitrages (hors pare-brise).
> - Vérifiez que le réparateur choisi figure bien dans le réseau agréé pour éviter toute surprise.

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A37 — Mistral · Q04

- **Moteur** : Mistral
- **Document** : CG-PREV-INV-2024 — [contrat](contrats/CG-PREV-INV-2024.md)
- **Question** : À partir de quel taux d'invalidité est-on reconnu en Invalidité Permanente Totale ?

**Réponse :**

> **Réponse directe** :
> L’Invalidité Permanente Totale (IPT) est reconnue à partir d’un **taux d’invalidité fonctionnelle supérieur ou égal à 66%**, évalué par le médecin conseil d’ARESIA Assurances après consolidation de l’état de santé.
> 
> ---
> 
> **Source(s)** :
> - [Article 6.2 des CG Prévoyance Invalidité — v4.2] : *« 66% à 99% IPT — Invalidité Permanente Totale »*.
> - [Article 6 des CG Prévoyance Invalidité — v4.2] : *« La garantie IPT est acquise lorsque [...] le médecin conseil [...] reconnaît un taux d'invalidité fonctionnelle supérieur ou égal à 66% »*.
> - [Article 1 des CG Prévoyance Invalidité — v4.2] : *« Invalidité Permanente Totale (IPT) : État de l'assuré dont le taux d'invalidité fonctionnelle est supérieur ou égal à 66% »*.
> 
> ---
> 
> **Point d'attention** :
> - Le taux d’invalidité est déterminé **uniquement** selon le barème médical du CCSF (Comité Consultatif du Secteur Financier), et non par le médecin traitant seul. Une expertise contradictoire est possible en cas de désaccord ([Article 6.1 et 6.3]).
> - La reconnaissance de l’IPT est **définitive** après consolidation, sauf amélioration significative justifiant une réévaluation ([Article 6]).
> - Aucune prestation n’est versée pour un taux **inférieur à 66%** (seule l’IPP, entre 33% et 65%, est couverte).

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A38 — Claude · Q16

- **Moteur** : Claude
- **Document** : BAR-IARD-2024-V2 — [contrat](contrats/BAR-IARD-2024-V2.md)
- **Question** : La multirisque habitation couvre-t-elle le vol d'espèces au domicile et jusqu'à quel montant ?

**Réponse :**

> **Réponse directe**
> 
> Oui, la multirisque habitation (MRH) ARESIA Assurances couvre bien le vol d'espèces au domicile. Le plafond de remboursement pour les espèces est fixé à **5 000 €**, avec une franchise standard de **300 €** applicable au sinistre. À titre de comparaison, le plafond pour le vol de mobilier est distinct et s'élève à 30 000 €.
> 
> ---
> 
> **Source(s)**
> 
> > [Article 1.1 des CG Barème des Garanties IARD 2024 — v2.0] — Tableau des garanties de base :
> > *"Vol et actes de vandalisme — 30 000 € (meubles) / **5 000 € (espèces)** — Franchise : 300 €"*
> 
> ---
> 
> **Point d'attention**
> 
> Deux éléments importants à garder en tête :
> 
> - ⚠️ **Dépôt de plainte obligatoire** : en cas de vol ou cambriolage, le dépôt de plainte est une condition nécessaire à l'ouverture du dossier, et la déclaration doit être effectuée **dans les 48 heures après constat** [Article 4.1 — v2.0]. Tout retard peut compromettre la prise en charge.
> - 💡 **Plafond non extensible pour les espèces** : contrairement aux objets de valeur identifiés (couverts jusqu'à 15 000 € via l'option dédiée), aucune extension spécifique aux espèces n'est mentionnée dans les documents disponibles. Le plafond de 5 000 € semble donc être le maximum applicable en l'état.
> 
> Si vous souhaitez vérifier l'existence d'une éventuelle option d'extension pour les espèces, je vous recommande de contacter votre référent produit ou le service technique de ARESIA Assurances.

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A39 — Claude · Q05

- **Moteur** : Claude
- **Document** : CG-PREV-INV-2024 — [contrat](contrats/CG-PREV-INV-2024.md)
- **Question** : Le burn-out est-il couvert par le contrat prévoyance invalidité ?

**Réponse :**

> **Réponse directe**
> 
> Oui, le burn-out est couvert par le contrat prévoyance invalidité ARESIA, mais cette couverture est soumise à des **conditions précises qui varient selon la garantie concernée** :
> 
> - **Au titre de la garantie ITT** (Incapacité Temporaire de Travail — c'est-à-dire l'impossibilité totale et médicalement constatée d'exercer son activité professionnelle) : le burn-out est couvert **sans exclusion temporaire**, à condition que l'assuré ait fourni un **questionnaire médical de santé favorable** ET ait souscrit le contrat **avant toute prescription médicale liée à cette pathologie**.
> 
> - **Au titre des affections psychiatriques en général** : le burn-out est couvert **sans limitation de durée spécifique**, mais uniquement pour les assurés ayant souscrit l'**option Premium**, et sous réserve d'un **suivi psychiatrique régulier attesté**.
> 
> - **Attention au questionnaire médical** : pour les affections psychiatriques en général, une surprime ou une exclusion spécifique peut être appliquée sur la base du questionnaire médical, après avis du médecin conseil de l'assureur.
> 
> ---
> 
> **Source(s)**
> 
> - [Article 13.5 des CG Prévoyance Invalidité — v4.2] : couverture du burn-out sans exclusion temporaire pour la garantie ITT, sous conditions de questionnaire médical favorable et de souscription avant prescription.
> - [Article 5.1 des CG Prévoyance Invalidité — v4.2] : couverture des affections psychiatriques (dont le burn-out) sans limitation de durée pour les assurés ayant souscrit l'option Premium, sous réserve de suivi psychiatrique attesté.
> - [Article 5 des CG Prévoyance Invalidité — v4.2] : possibilité de surprime ou d'exclusion spécifique pour les affections psychiatriques sur la base du questionnaire médical.
> 
> ---
> 
> **Point d'attention**
> 
> ⚠️ Deux conditions cumulatives sont particulièrement critiques et doivent être vérifiées avec soin :
> 
> 1. **La date de souscription** : si l'assuré avait déjà reçu une prescription médicale liée au burn-out **avant** la souscription du contrat, la couverture ITT peut être remise en cause.
> 2. **L'option souscrite** : la couverture sans limitation de durée des pathologies psychiatriques est **réservée à l'option Premium**. Les assurés ayant souscrit les options Essentiel, Confort ou Dirigeant doivent se référer aux conditions qui leur ont été notifiées lors de la souscription.
> 
> En cas de doute sur l'éligibilité d'un dossier, je vous recommande de **contacter votre référent produit ou le service technique de ARESIA Assurances** afin d'examiner les Conditions Particulières du contrat concerné.

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---

## A40 — Mistral · Q10

- **Moteur** : Mistral
- **Document** : CG-AV-MULTI-2024 — [contrat](contrats/CG-AV-MULTI-2024.md)
- **Question** : Le fonds en euros ARESIA Sécurité garantit-il le capital investi ?

**Réponse :**

> **Réponse directe** :
> Oui, le fonds en euros **ARESIA Sécurité** garantit **100 % du capital versé**, net de frais sur versements.
> 
> ---
> 
> **Source(s)** :
> - [Article 10 des CG *ARESIA Patrimoine+* — v3.1] : *"Garantie en capital : 100% du capital versé net de frais sur versements"*.
> - [Article 2 des CG *ARESIA Patrimoine+* — v3.1] : *"Support en euros : Fonds général de l'assureur offrant une garantie en capital. Les intérêts crédités sont définitivement acquis."*
> 
> ---
> 
> **Point d'attention** :
> 1. **Frais sur versements** : La garantie s’applique sur le capital *net* de ces frais (ex. : jusqu’à 4,5 % selon le réseau de distribution). Le montant effectivement garanti peut donc être inférieur au montant brut versé.
> 2. **Variabilité du rendement** : Le taux de rendement (ex. : 2,80 % en 2023) n’est pas garanti pour les années futures et peut être ajusté par l’assureur [Article 10.3].
> 3. **Limitations possibles** : ARESIA Assurances se réserve le droit de limiter les versements sur ce fonds ou d’imposer une diversification minimale en unités de compte [Article 10.3].

- **C1 Fidélité** : ☐ oui ☐ non
- **C2 Citations** : ☐ oui ☐ non ☐ sans objet
- **C3 Refus** : ☐ oui ☐ non ☐ sans objet
- **Commentaire** :

---
