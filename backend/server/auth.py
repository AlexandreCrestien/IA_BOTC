"""Routes des comptes : inscription, connexion, déconnexion, profil.

La connexion est un JWT dans un cookie HttpOnly (illisible par le JavaScript de la page) et SameSite=Lax
(pas envoyé par les requêtes POST d'un autre site). Les dépendances current_user et admin_user
protègent les autres routes (administration, statistiques…).
"""
import logging
import time
from collections import defaultdict, deque
from typing import Iterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.accounts import service
from backend.accounts.pseudo import normalize_pseudo
from backend.accounts.service import AccountError
from backend.accounts.tokens import COOKIE_NAME, TOKEN_LIFETIME, create_token
from backend.db import User, get_session, pseudo_key
from backend.server.game_records import claim_guest_game
from backend.server.session import current_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Comptes"])

NOT_LOGGED_IN = "Vous n'êtes pas connecté."
ADMIN_ONLY = "Accès réservé à l'administrateur."
BAD_CREDENTIALS = "Pseudo ou mot de passe incorrect."
TOO_MANY_ATTEMPTS = "Trop de tentatives de connexion. Réessayez dans quelques minutes."
PSEUDO_LOCKED = "Impossible de changer de pseudo pendant une partie en cours."


# --- Dépendances --------------------------------------------------------------------

def db_session() -> Iterator[Session]:
    with get_session() as db:
        yield db


def optional_user(request: Request, db: Session = Depends(db_session)) -> Optional[User]:
    """Compte connecté (cookie valide), ou None."""
    token = request.cookies.get(COOKIE_NAME)
    return service.user_from_token(db, token) if token else None


def current_user(user: Optional[User] = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, NOT_LOGGED_IN)
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, ADMIN_ONLY)
    return user


# --- Limitation des tentatives de connexion -------------------------------------------

class LoginLimiter:
    """Au-delà de MAX_FAILURES échecs en WINDOW secondes pour un même pseudo, la connexion est
    refusée jusqu'à ce que les plus anciens échecs sortent de la fenêtre (protection contre
    l'essai de mots de passe en série). Un succès efface les échecs. Gardé en mémoire."""
    MAX_FAILURES = 5
    WINDOW = 300

    def __init__(self):
        self.failures: dict[str, deque[float]] = defaultdict(deque)

    def _recent(self, key: str) -> deque[float]:
        attempts = self.failures[key]
        while attempts and time.monotonic() - attempts[0] > self.WINDOW:
            attempts.popleft()
        return attempts

    def blocked(self, key: str) -> bool:
        return len(self._recent(key)) >= self.MAX_FAILURES

    def failed(self, key: str) -> None:
        self._recent(key).append(time.monotonic())

    def succeeded(self, key: str) -> None:
        self.failures.pop(key, None)


login_limiter = LoginLimiter()


# --- Schémas --------------------------------------------------------------------------

class Credentials(BaseModel):
    # Longueurs maximales larges : les vraies règles sont vérifiées par le service (messages en français)
    pseudo: str = Field(max_length=100)
    password: str = Field(max_length=200)
    # Invité qui s'inscrit ou se connecte pendant sa partie, ou sur l'écran de fin : jeton reçu
    # à la connexion WebSocket (message guest_session) pour rattacher la partie à son compte
    guest_token: Optional[str] = Field(default=None, max_length=100)


class PseudoChange(BaseModel):
    current_password: str = Field(max_length=200)
    pseudo: str = Field(max_length=100)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


class UserOut(BaseModel):
    id: int
    pseudo: str
    is_admin: bool


class LoginOut(UserOut):
    game_claimed: bool = False  # la partie de l'invité a été rattachée au compte
    # Partie déjà terminée rattachée depuis l'écran de fin : succès qu'elle vient de débloquer
    achievements: list[dict] = []


def user_out(user: User) -> UserOut:
    return UserOut(id=user.id, pseudo=user.pseudo, is_admin=user.is_admin)


def login_out(user: User, guest_token: Optional[str]) -> LoginOut:
    claimed = claim_guest_game(user.id, guest_token)
    session = current_session()
    achievements = session.unlocked if claimed and session is not None and not session.running else []
    return LoginOut(id=user.id, pseudo=user.pseudo, is_admin=user.is_admin, game_claimed=claimed,
                    achievements=achievements)


def set_login_cookie(response: Response, user: User) -> None:
    response.set_cookie(
        COOKIE_NAME, create_token(user.id, user.token_version),
        max_age=int(TOKEN_LIFETIME.total_seconds()), httponly=True, samesite="lax",
        secure=False,  # serveur local en HTTP ; à passer à True derrière HTTPS
        path="/",
    )


def _refuse(error: AccountError):
    raise HTTPException(error.status, error.message)


# --- Routes ---------------------------------------------------------------------------

@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(body: Credentials, response: Response, db: Session = Depends(db_session)) -> LoginOut:
    """Crée le compte et connecte le joueur (avec guest_token : rattache aussi sa partie d'invité)."""
    try:
        user = service.register(db, body.pseudo, body.password)
    except AccountError as error:
        _refuse(error)
    set_login_cookie(response, user)
    return login_out(user, body.guest_token)


@router.post("/auth/login")
def login(body: Credentials, response: Response, db: Session = Depends(db_session)) -> LoginOut:
    key = pseudo_key(normalize_pseudo(body.pseudo))
    if login_limiter.blocked(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, TOO_MANY_ATTEMPTS)
    user = service.authenticate(db, body.pseudo, body.password)
    if user is None:
        login_limiter.failed(key)
        logger.warning("Échec de connexion pour %r", body.pseudo)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, BAD_CREDENTIALS)
    login_limiter.succeeded(key)
    set_login_cookie(response, user)
    return login_out(user, body.guest_token)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax")


@router.get("/auth/me")
def me(user: User = Depends(current_user)) -> UserOut:
    return user_out(user)


@router.patch("/account/pseudo")
def change_pseudo(body: PseudoChange, user: User = Depends(current_user),
                  db: Session = Depends(db_session)) -> UserOut:
    """Interdit pendant une partie en cours du compte : le pseudo y sert d'identifiant du joueur."""
    session = current_session()
    if session is not None and session.running and session.user_id == user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, PSEUDO_LOCKED)
    try:
        service.change_pseudo(db, user, body.current_password, body.pseudo)
    except AccountError as error:
        _refuse(error)
    return user_out(user)


@router.patch("/account/password")
def change_password(body: PasswordChange, response: Response, user: User = Depends(current_user),
                    db: Session = Depends(db_session)) -> UserOut:
    """Les autres appareils sont déconnectés ; celui-ci reçoit un nouveau jeton."""
    try:
        service.change_password(db, user, body.current_password, body.new_password)
    except AccountError as error:
        _refuse(error)
    set_login_cookie(response, user)
    return user_out(user)
