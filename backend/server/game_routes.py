"""Routes HTTP sur la partie en cours, pour l'accueil et le tableau de bord (hors de l'écran de jeu) :
savoir si une partie attend le joueur (la reprendre), et l'abandonner sans la rouvrir.

Fermer l'onglet ne termine pas la partie : elle attend le joueur, qui choisit ensuite de la reprendre
ou de l'abandonner (défaite).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.db import User
from backend.server import game_runner
from backend.server.auth import optional_user, verified_user
from backend.server.protocol import send
from backend.server.schemas import GameAbandoned
from backend.server.session import current_session

router = APIRouter(prefix="/api/game", tags=["Partie"])

NO_GAME = "Aucune partie en cours."


class CurrentGame(BaseModel):
    running: bool
    pseudo: Optional[str] = None  # pseudo du joueur dans la partie (pour s'y reconnecter)
    turn: Optional[int] = None
    yours: bool = False           # partie de ce compte, ou partie d'invité que l'on peut reprendre


@router.get("/current")
def current_game(user: Optional[User] = Depends(optional_user)) -> CurrentGame:
    session = current_session()
    if session is None or not session.running:
        return CurrentGame(running=False)
    if session.user_id is None:
        yours = user is None  # partie d'invité : reprise possible sans compte (un compte joue sous son pseudo)
    else:
        yours = user is not None and user.id == session.user_id
    return CurrentGame(running=True, pseudo=session.human_id, yours=yours,
                       turn=session.state.turn if session.state is not None else None)


@router.post("/abandon", status_code=status.HTTP_204_NO_CONTENT)
async def abandon(user: User = Depends(verified_user)) -> None:
    """Abandon depuis le tableau de bord : défaite (abandon). Si l'écran de jeu est encore ouvert, il est prévenu."""
    session = current_session()
    if session is None or not session.running or session.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_GAME)
    human_id = session.human_id
    game_runner.abandon_game(human_id)
    await send(human_id, GameAbandoned())
