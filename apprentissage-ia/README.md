# Application d'apprentissage IA – backend

Compagnon d'apprentissage : cours importés (PDF, DOCX, TXT), QCM générés par IA, correction
expliquée, révisions espacées, gamification, abonnements en FCFA pour plusieurs pays d'Afrique
francophone.

Ce dossier contient **l'API (FastAPI)**. L'application mobile Flutter prévue dans la fiche projet
n'est pas encore écrite : elle consommera cette API.

## Décisions prises (à valider)

| Sujet | Choix | Pourquoi |
|---|---|---|
| Fournisseur IA | Anthropic Claude : `claude-haiku-5-5` (tâches simples) et `claude-sonnet-5-5` (analyses) | Modèle économique pour l'essentiel, modèle plus performant pour l'analyse de documents |
| Paiement | Flutterwave (Mobile Money + cartes) derrière une interface `PaymentProvider` | Couvre le Mobile Money dans plusieurs pays de la zone franc ; le prestataire reste remplaçable |
| Pays | CM, GA, CG (XAF) ; SN, CI, TG, BJ, BF (XOF) | Même monnaie régionale, mêmes prix ; surcharge possible par pays (`catalog.PRICE_OVERRIDES`) |
| Annuel | 16 500 FCFA, avec les fonctionnalités Étudiant | La fiche ne tranche pas ; à confirmer (risque de cannibalisation signalé) |
| Crédits IA | 100 crédits = 1 000 FCFA ; 300 = 2 500 FCFA | Pas de prix dans la fiche ; proposition |
| Quotas | Gratuit 5 opérations IA/jour, Étudiant 30, Premium 100 ; évaluations 1/5/5 par semaine | Fiche projet |

Les prix, quotas et tarifs IA sont dans `backend/app/catalog.py` et les variables d'environnement.

## Règles métier importantes

- **Une opération IA** = un appel au fournisseur (explication, génération de QCM, analyse de document).
  Les réponses déjà en cache (même question, mêmes extraits de cours) ne consomment rien.
- **Quota** : quota quotidien, puis crédits, sinon refus (HTTP 429). Un appel IA qui échoue est remboursé.
- **Plafond global** : `DAILY_AI_SPEND_CAP_USD` suspend l'IA pour la journée si le coût dépasse la limite.
- **Abonnement** : activé uniquement après une vérification côté serveur auprès du prestataire
  (montant et devise doivent correspondre). Un webhook n'est qu'un signal : il est revérifié, et
  la réception répétée d'un même paiement n'accorde rien une seconde fois.
- **Clé API** : uniquement côté serveur.
- **Suppression de compte** : `DELETE /me` efface toutes les données personnelles.

## Lancer en local

```bash
cd apprentissage-ia/backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env          # puis renseigner ANTHROPIC_API_KEY si besoin
export $(grep -v '^#' ../.env | xargs)
python -m app.cli create-tables
uvicorn app.main:app --reload
```

Documentation interactive : http://localhost:8000/docs

Créer un administrateur (après inscription) :

```bash
python -m app.cli make-admin admin@example.com
```

## Tests

```bash
cd apprentissage-ia/backend && python -m pytest -q
```

Les tests utilisent un faux client IA et un faux prestataire de paiement : aucun appel réseau,
aucune clé nécessaire.

## Structure

```
backend/app/
  main.py            application et routes
  config.py          variables d'environnement
  catalog.py         pays, plans, quotas, produits, prix
  models.py          tables SQLAlchemy
  quota.py           quotas, crédits, plafond de dépense, suivi des coûts
  security.py        mots de passe (PBKDF2) et jetons signés
  ai/                client Anthropic, prompts
  payments/          interface + Flutterwave + bac à sable
  services/          documents, QCM, révisions SM-2, XP, tuteur, facturation
  routers/           auth, content, learning, billing, admin
backend/tests/       39 tests (parcours, quotas, paiements, administration)
```

## Ce qui n'est pas encore fait (et pourquoi)

- **Intégration Flutterwave non validée** : pas de clés de test ici. Les endpoints et le webhook
  (`verif-hash`) suivent la documentation v3 et doivent être testés en sandbox avant la mise en production.
- **Google Sign-In et mot de passe oublié** : non implémentés (prévus dans la fiche).
- **Banque de QCM partagée et validée** : pour l'instant chaque étudiant génère ses propres questions.
  Une banque validée par matière réduirait le coût IA (idée de la fiche, section 3).
- **Recherche dans les cours** : par mots-clés, pas encore par embeddings. Suffisant pour démarrer,
  à améliorer ensuite.
- **Notifications (rappels, FCM)** : non implémentées.
- **Migrations** : tables créées par `create_all`. Alembic à ajouter avant la production.
- **Store policies** : Google Play et l'App Store exigent en général leur propre système d'achat pour
  les contenus numériques vendus dans l'app. Le paiement Flutterwave par lien web doit être validé
  juridiquement et au regard des règles des stores avant le lancement mobile.
- **Coûts IA réels** : `AI_INPUT_USD_PER_MTOK` et `AI_OUTPUT_USD_PER_MTOK` doivent recevoir les tarifs
  officiels, sinon le suivi des coûts et la marge affichée sont faux.
