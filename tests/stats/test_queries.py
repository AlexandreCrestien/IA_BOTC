"""Statistiques, historique et succès d'un compte, lus dans une base en mémoire."""
from datetime import datetime, timedelta, timezone

from backend.db import GameRecord, GameStatus, User
from backend.models import Alignment, RoleKey
from backend.stats.achievements import BY_CODE
from backend.stats.queries import achievements_of, game_history, player_stats, unlock

ROLE_SIDE = {RoleKey.MEDIUM: Alignment.GOOD, RoleKey.REAPER: Alignment.EVIL}
START = datetime(2026, 11, 1, 20, 0, tzinfo=timezone.utc)


def player(db, pseudo="Vesper") -> User:
    user = User(pseudo=pseudo, password_hash="hash")
    db.add(user)
    db.commit()
    return user


def add_games(db, user, *games):
    """games : (rôle, statut, tours), de la plus ancienne à la plus récente."""
    for day, (role, status, turns) in enumerate(games):
        db.add(GameRecord(user=user, role=role, alignment=ROLE_SIDE[role], status=status, turns=turns,
                          started_at=START + timedelta(days=day)))
    db.commit()


def test_stats_without_games(db):
    stats = player_stats(db, player(db).id)
    assert stats == {"played": 0, "wins": 0, "win_rate": None,
                     "good": {"played": 0, "wins": 0, "win_rate": None},
                     "evil": {"played": 0, "wins": 0, "win_rate": None},
                     "average_turns": None}


def test_stats_by_side(db):
    user = player(db)
    add_games(db, user,
              (RoleKey.MEDIUM, GameStatus.WON, 2),
              (RoleKey.MEDIUM, GameStatus.LOST, 4),
              (RoleKey.MEDIUM, GameStatus.ABANDONED, 3),   # défaite
              (RoleKey.REAPER, GameStatus.WON, 5),
              (RoleKey.REAPER, GameStatus.INTERRUPTED, 9),  # hors statistiques
              (RoleKey.REAPER, GameStatus.IN_PROGRESS, 1))  # pas encore terminée
    stats = player_stats(db, user.id)
    assert (stats["played"], stats["wins"], stats["win_rate"]) == (4, 2, 0.5)
    assert stats["good"] == {"played": 3, "wins": 1, "win_rate": 0.333}
    assert stats["evil"] == {"played": 1, "wins": 1, "win_rate": 1.0}
    assert stats["average_turns"] == 3.5


def test_stats_are_per_account(db):
    user, other = player(db), player(db, "Ombre")
    add_games(db, other, (RoleKey.MEDIUM, GameStatus.WON, 2))
    assert player_stats(db, user.id)["played"] == 0


def test_history_newest_first_without_running_game(db):
    user = player(db)
    add_games(db, user,
              (RoleKey.MEDIUM, GameStatus.WON, 2),
              (RoleKey.REAPER, GameStatus.INTERRUPTED, 4),
              (RoleKey.REAPER, GameStatus.ABANDONED, 3),
              (RoleKey.MEDIUM, GameStatus.IN_PROGRESS, 1))
    history = game_history(db, user.id)
    assert [(g["role_name"], g["status"], g["counted"]) for g in history] == [
        ("Faucheur", "abandoned", True), ("Faucheur", "interrupted", False), ("Médium", "won", True)]
    assert history[0]["alignment"] == "evil" and history[0]["turns"] == 3 and history[0]["role"] == "reaper"
    assert history[-1]["date"] == "2026-11-01T20:00:00+00:00"


def test_unlock_only_new_achievements(db):
    user = player(db)
    first = unlock(db, user.id, None, [BY_CODE["win_medium"], BY_CODE["executed"]])
    db.commit()
    again = unlock(db, user.id, None, [BY_CODE["executed"], BY_CODE["quick_win"]])
    db.commit()
    assert [a.code for a in first] == ["win_medium", "executed"]
    assert [a.code for a in again] == ["quick_win"]


def test_achievements_list_hides_locked_secrets(db):
    user = player(db)
    unlock(db, user.id, None, [BY_CODE["win_medium"], BY_CODE["win_after_reaper"]])
    db.commit()
    by_code = {a["code"]: a for a in achievements_of(db, user.id)}
    assert len(by_code) == 14

    assert by_code["win_medium"]["unlocked"] and by_code["win_medium"]["unlocked_at"].endswith("+00:00")
    assert by_code["win_after_reaper"]["title"] == "Increvable"           # caché mais débloqué : révélé
    assert by_code["win_after_reaper"]["message"] == "Mort, mais pas vaincu."
    secret = by_code["one_turn_win"]                                       # caché et verrouillé
    assert (secret["title"], secret["description"], secret["message"]) == ("???", "Succès caché.", None)
    locked = by_code["executed"]                                           # visible et verrouillé
    assert locked["title"] == "Sur l'échafaud" and locked["message"] is None and not locked["unlocked"]
