# Fonctionnalités

Ce que fait le jeu, côté joueur et côté administrateur, et comment les données personnelles sont traitées.
Installation et lancement : [README](../README.md). Configuration : [configuration.md](configuration.md).

## Le jeu

Une partie se joue à **6 joueurs** : un humain et **5 agents IA**. Chaque agent reçoit un rôle secret et une personnalité, et parle grâce à un LLM.

### Rôles

| Rôle | Camp | Pouvoir |
|---|---|---|
| 😈 Faucheur | Démon | Chaque nuit, choisit un habitant à tuer. |
| 🧪 Apothicaire | Complice | Chaque nuit, empoisonne un habitant, jusqu'à la fin de la journée suivante. |
| 🛡️ Veilleur | Villageois | Chaque nuit, protège un habitant de l'attaque du Faucheur. |
| 🔮 Médium | Villageois | Chaque nuit, sonde deux joueurs et apprend si l'un d'eux est démon (une fausse piste est tirée en début de partie). |
| 🔍 Inquisiteur | Villageois | Au début de la partie, voit un complice parmi deux joueurs. |
| 🎩 Valet | Paria | Chaque nuit, choisit un maître ; ne peut voter que si son maître vote. |

**Personnalités** des agents : Provocateur, Parano, Bouffon, Stratège, Observateur (`skills/personalities/`), une différente par agent.

### Déroulement d'un tour

- **Nuit** : les IA puis l'humain font leur choix ; les morts sont annoncés. La première nuit, personne ne meurt : le camp du mal apprend qui est son allié, l'Inquisiteur reçoit son information.
- **Discussion** : les IA parlent sur la place publique (10 messages au plus), puis l'humain. Il peut ensuite ouvrir un salon privé avec 1 ou 2 agents (3 messages), ou passer. Sans choix pendant 10 secondes, un agent lui propose un entretien. Pendant ce temps, deux autres agents s'entretiennent en privé : la conversation n'est pas jouée (un seul appel au LLM en écrit un résumé pour chacun), mais elle est annoncée publiquement, ce qui donne un indice.
- **Vote** : les IA puis l'humain votent pour exécuter un joueur.
- Les morts restent dans la partie : ils parlent et gardent un dernier vote (voix d'outre-tombe).
- **Victoire** : le bien gagne si le Faucheur meurt ; le mal gagne s'il ne reste plus de joueur du bien en vie, ou un seul après le vote.
- Une IA qui ne répond pas ou fait un choix invalide : un choix légal est tiré au hasard (abstention pour un vote), et le joueur en est prévenu, sauf la nuit pour ne rien révéler de son rôle.

### Interface

Table ronde et liste des joueurs (avec une note de soupçon), chat par salon, historiques des nuits et des votes, panneau d'actions selon la phase, Codex (rôles, règles, et onglet « IA & données » : le joueur sait qu'il joue contre des IA, quelles données leur sont envoyées et à qui). Fermer l'onglet ne termine pas la partie : elle reprend où elle en était. Une seule partie à la fois sur le serveur.

## Comptes

- **Invité ou compte** : un invité joue avec un simple pseudo, rien n'est enregistré. Un compte (pseudo, adresse e-mail, mot de passe) se connecte avec le pseudo ou l'adresse. Un invité qui crée un compte pendant la partie ou sur l'écran de fin y rattache la partie.
- **Adresse confirmée** par un lien reçu par e-mail (valable 24 heures) avant d'accéder au compte ; compte non confirmé supprimé après 72 heures. Un changement d'adresse se confirme de la même façon.
- **Mot de passe oublié** : lien par e-mail (usage unique, 30 minutes), même réponse que l'adresse ait un compte ou non, 3 demandes par adresse en 15 minutes.
- **Notifications de sécurité** par e-mail : adresse remplacée (à l'ancienne adresse), mot de passe modifié ou réinitialisé, avec l'adresse à contacter si ce n'est pas le joueur.
- **Tableau de bord** : lancer, reprendre ou abandonner sa partie ; statistiques (parties, victoires par camp, tours moyens) comparées à la moyenne des joueurs (à partir de 10 joueurs) ; historique des parties ; succès ; profil (pseudo, adresse, mot de passe) ; export de ses données ; suppression du compte. Pour démontrer la comparaison en local, `uv run scripts/demo_players.py` crée 10 joueurs factices avec leurs parties et leurs succès, et `--remove` les retire (voir [configuration.md](configuration.md#scripts)).
- **Succès** (14, dont 4 cachés), débloqués à la fin d'une partie gagnée ou perdue : victoire avec chaque rôle, voix d'outre-tombe, exécutions, victoires rapides… Définitions : `backend/stats/achievements.py`.

## Retours des joueurs sur les IA

Réservés aux joueurs connectés. Ils servent à améliorer les prompts à la main et ne sont **jamais renvoyés aux agents** (un commentaire de joueur dans un prompt ouvrirait la porte à la manipulation).

- **Signaler un message** d'un agent (drapeau au survol) : information qu'il ne devrait pas connaître, incohérence, sortie de personnage, contenu inapproprié, autre. Commentaire facultatif (obligatoire pour « Autre »). Un signalement par message, 10 par partie. Le signalement garde le modèle qui a écrit le message.
- **Évaluer les agents** en fin de partie : une note de 1 à 5 par personnage et un commentaire facultatif, une fois par partie.

## Panel admin

`http://127.0.0.1:8000/admin`, avec le compte admin du `.env`. Raccourcis vers l'accueil, les signalements et la partie en cours.

- **Partie en cours** (ou dernière terminée), sans rien cacher : rôles, personnalités, historique public, mémoire de chaque agent, actions de nuit, votes, IA indisponibles.
- **Comptes** : réinitialiser un mot de passe (mot de passe temporaire affiché une fois), supprimer un compte, et « Historique » : parties du joueur avec leur détail complet, et registre des modifications du compte (type et date).
- **Signalements**, filtrables par statut, agent, personnalité, modèle et problème, avec un lien vers la partie et un statut « traité ».
- **Évaluations** : moyennes par personnalité et par modèle, commentaires.

## Données personnelles (RGPD)

| Donnée | Conservation |
|---|---|
| Compte (pseudo, adresse, empreinte du mot de passe), succès | Tant que le compte existe ; supprimé après un an sans connexion, un mois après un e-mail d'avertissement |
| Compte jamais confirmé | 72 heures |
| Résumé des parties (date, rôle, camp, issue, tours) | Anonymisé à la suppression du compte (détaché, daté au jour près), gardé pour les statistiques |
| Détail des parties (chat, votes, mémoire des IA) | 6 mois, et supprimé avec le compte |
| Registre des modifications du compte (type et date) | 1 an, et supprimé avec le compte |
| Signalements | Supprimés 6 mois après leur traitement ; à la suppression du compte, détachés et sans commentaire |
| Évaluations | Commentaire effacé après 6 mois ; à la suppression du compte, détachées et sans commentaire ; la note est gardée |
| Liens envoyés par e-mail | Effacés un jour après leur expiration |

- La suppression d'un compte est la même par le joueur, par l'admin ou pour inactivité. La tâche de nettoyage tourne au démarrage du serveur puis une fois par jour.
- Rien n'est collecté sur les invités (pas de signalement ni d'évaluation).
- Le pseudo du joueur, que les agents citent souvent, est remplacé par « [joueur] » dans les signalements et commentaires enregistrés.
- Le joueur télécharge toutes ses données depuis son tableau de bord (droit d'accès), et les supprime en supprimant son compte.
- L'usage de l'adresse e-mail est expliqué là où elle est demandée (icône « ? ») ; les adresses sont masquées dans les journaux du serveur, qui ne contiennent jamais le contenu des messages ni des commentaires.
- Un seul cookie, nécessaire à la connexion (7 jours), sans suivi ni publicité.
