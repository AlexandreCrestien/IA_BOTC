# 1- Préparation de la partie
# Distribution des rôles - rules > distribution (à améliorer)
# Envoi des rôles à la fonction create_agents (déjà dans agent_factory)
# Affichage du rôle du joueur

# Boucle de jeu pour la succession des phase - à faire
# Utiliser les conditions de victoire pour arrêter la boucle - à faire


# 2A- Début de la partie : 1E NUIT
# Script pour appeler les rôles dans un ordre prédéfini - rules > à faire
# Solution de choix aléatoire si l'appel LLM échoue ou si l'IA répond de la merde - à faire
# Traiter la réponse du LLM et appliquer les changements de paramètres qui en découlent - à faire
# Ajouter les infos à l'historique personnel de l'agent (fonction déjà prête) > à faire

# 2B- Phase NUIT classique
# Idem que la 1ere nuit mais avec le diablotin qui tue et le moine qui protège
# Même script avec conditions


# 3- Annonce du mort éventuel


# 4A- Phase CONVERSATION PUBLIQUE [EDILENE]
# Script avec ordre défini par personnalité
# Selon la personnalité, on oblige à parler (ex: provocateur) ou on propose de répondre mais pas obligé (ex: observateur)
# Pas d'humain ici !!
# A 10 messages totaux, on arrête
# Penser à ajouter les historiques


# 4B- Phase CONVERSATION PRIVÉE [EDILENE]
# On demande au joueur s'il veut discuter avec 1 ou 2 agents (il coche ceux qu'il veut inclure)
# S'il ne veut pas, on lance une conversation privée (choix par un script : d'abord personnalité la + bavarde, ensuite les personnalités qui n'ont jamais discuté avec le joueur)
# Penser à ajouter les historiques


# 5- Phase JOUR - VOTE
# Script pour appeler les différents joueurs (faire attention à l'odre du majordome et l'informer qu'il ne peut pas voter sans faire d'appel LLM - juste ajouter à son historique perso)
# Traiter les réponses
# Ajouter les infos aux historiques
# Résultat du vote et mort potentielle


# Interface graphique + server [FLORA]