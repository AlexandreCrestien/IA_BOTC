"""Joueurs de démonstration : 10 comptes fictifs, avec des parties et des succès, pour montrer la comparaison
aux autres joueurs du tableau de bord (elle n'apparaît qu'à partir de 10 joueurs).

    python scripts/demo_players.py            ajouter les joueurs de démonstration (dans la base de DATABASE_URL)
    python scripts/demo_players.py --remove   les retirer, avec leurs parties et leurs succès

Les comptes de démonstration sont reconnaissables à leur adresse en @demo.lantern-hollow.invalid
(le domaine .invalid est réservé : aucun e-mail ne peut y partir). Leur mot de passe est aléatoire et jamais
affiché : on ne peut pas s'y connecter. Le retrait les efface entièrement (pas d'anonymisation : ce ne sont
pas de vraies parties, rien ne doit rester dans les statistiques).
"""
import argparse
import random
import secrets
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from backend.accounts.passwords import hash_password  # noqa: E402
from backend.db import (  # noqa: E402
    AccountEvent,
    GameDetail,
    GameRecord,
    GameStatus,
    UnlockedAchievement,
    User,
    get_session,
)
from backend.db.models import utcnow  # noqa: E402
from backend.models import RoleKey  # noqa: E402
from backend.rules import get_role  # noqa: E402
from backend.stats.achievements import GameFacts, GameSummary, earned_achievements  # noqa: E402

DEMO_DOMAIN = "demo.lantern-hollow.invalid"
DEMO_PSEUDOS = ["Aldric", "Brune", "Corentin", "Delphine", "Eloi", "Fanchon", "Gaspard", "Hortense", "Isidore",
                "Jacinthe"]
SEED = 1888  # même tirage à chaque fois : les mêmes joueurs, les mêmes parties


def demo_accounts(db: Session) -> list[User]:
    return list(db.scalars(select(User).where(User.email.like(f"%@{DEMO_DOMAIN}"))))


def _demo_game(rng: random.Random, user: User, days_ago: int) -> tuple[GameRecord, GameSummary]:
    role = rng.choice(list(RoleKey))
    won = rng.random() < (0.55 if get_role(role).alignment.value == "good" else 0.45)
    status = GameStatus.WON if won else rng.choices([GameStatus.LOST, GameStatus.ABANDONED], weights=[5, 1])[0]
    turns = rng.randint(1, 7) if won else rng.randint(2, 7)
    started = utcnow() - timedelta(days=days_ago, hours=rng.randint(0, 23))
    record = GameRecord(user_id=user.id, role=role, alignment=get_role(role).alignment, status=status, turns=turns,
                        started_at=started, ended_at=started + timedelta(minutes=10 * turns))
    executed = rng.random() < 0.3
    facts = GameFacts(ghost_vote_used=rng.random() < 0.4, voted_for_executed=rng.random() < 0.6,
                      executed_turn=rng.randint(1, turns) if executed else None,
                      killed_at_night=not executed and rng.random() < 0.3)
    return record, GameSummary(role=role, won=won, turns=turns, facts=facts)


def add_demo_players(db: Session, rng: random.Random | None = None) -> list[str]:
    """Ajoute les 10 joueurs de démonstration (rien si déjà présents). Renvoie les pseudos ajoutés."""
    if demo_accounts(db):
        return []
    rng = rng or random.Random(SEED)
    now = utcnow()
    added = []
    for index, pseudo in enumerate(DEMO_PSEUDOS):
        if db.scalar(select(User).where(User.pseudo_key == pseudo.casefold())) is not None:
            continue  # pseudo pris par un vrai compte : on le saute
        user = User(pseudo=pseudo, email=f"demo-{index + 1}@{DEMO_DOMAIN}",
                    password_hash=hash_password(secrets.token_urlsafe(24)),
                    created_at=now - timedelta(days=90), last_seen_at=now, email_verified_at=now - timedelta(days=90))
        db.add(user)
        db.flush()
        unlocked: dict[str, int] = {}
        for _ in range(rng.randint(3, 25)):
            record, summary = _demo_game(rng, user, days_ago=rng.randint(0, 85))
            db.add(record)
            db.flush()
            if record.status in (GameStatus.WON, GameStatus.LOST):
                for achievement in earned_achievements(summary):
                    unlocked.setdefault(achievement.code, record.id)
        db.add_all(UnlockedAchievement(user_id=user.id, code=code, game_id=game_id, unlocked_at=now)
                   for code, game_id in unlocked.items())
        added.append(pseudo)
    db.commit()
    return added


def remove_demo_players(db: Session) -> list[str]:
    """Supprime les joueurs de démonstration et TOUT ce qui les concerne (parties comprises). Renvoie les pseudos."""
    users = demo_accounts(db)
    ids = [u.id for u in users]
    if not ids:
        return []
    game_ids = select(GameRecord.id).where(GameRecord.user_id.in_(ids))
    db.execute(delete(GameDetail).where(GameDetail.game_id.in_(game_ids)))
    db.execute(delete(UnlockedAchievement).where(UnlockedAchievement.user_id.in_(ids)))
    db.execute(delete(AccountEvent).where(AccountEvent.user_id.in_(ids)))
    db.execute(delete(GameRecord).where(GameRecord.user_id.in_(ids)))
    pseudos = [u.pseudo for u in users]
    for user in users:
        db.delete(user)
    db.commit()
    return pseudos


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--remove", action="store_true", help="retirer les joueurs de démonstration")
    args = parser.parse_args()
    with get_session() as db:
        if args.remove:
            removed = remove_demo_players(db)
            print(f"{len(removed)} joueur(s) de démonstration retiré(s) : {', '.join(removed) or 'aucun'}")
        else:
            added = add_demo_players(db)
            if added:
                print(f"{len(added)} joueur(s) de démonstration ajouté(s) : {', '.join(added)}")
            else:
                print("Joueurs de démonstration déjà présents (python scripts/demo_players.py --remove pour les retirer).")


if __name__ == "__main__":
    main()
