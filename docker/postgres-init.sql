-- Exécuté une seule fois, à la création du volume de données (premier `docker compose up`).
-- Base séparée pour les tests sur PostgreSQL : ils la vident à chaque test, la base du jeu n'est jamais touchée.
CREATE DATABASE lantern_hollow_test;
