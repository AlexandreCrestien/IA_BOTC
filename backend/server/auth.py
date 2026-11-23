"""Routes des comptes : inscription, connexion (pseudo ou e-mail), déconnexion, mot de passe oublié, profil.

La connexion est un JWT dans un cookie HttpOnly (illisible par le JavaScript de la page) et SameSite=Lax
(pas envoyé par les requêtes POST d'un autre site). Les dépendances current_user et admin_user
protègent les autres routes (administration, statistiques…).
"""
import asyncio
import logging
import time
from collections import defaultdict, deque
from typing import Iterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.accounts import emails, service
from backend.accounts.passwords import verify_password
from backend.accounts.service import AccountError
from backend.accounts.tokens import COOKIE_NAME, TOKEN_LIFETIME, create_token
from backend.db import User, get_session
from backend.mail import mask_email, send_mail
from backend.server.account_removal import remove_account
from backend.server.game_records import claim_guest_game
from backend.server.session import current_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Comptes"])

NOT_LOGGED_IN = "Vous n'êtes pas connecté."
ADMIN_ONLY = "Accès réservé à l'administrateur."
BAD_CREDENTIALS = "Identifiant ou mot de passe incorrect."
TOO_MANY_ATTEMPTS = "Trop de tentatives de connexion. Réessayez dans quelques minutes."
PSEUDO_LOCKED = "Impossible de changer de pseudo pendant une partie en cours."
# Même réponse que l'adresse existe ou non : la page ne révèle pas qui a un compte
RESET_REQUESTED = ("Si un compte existe avec cette adresse, un e-mail vient d'y être envoyé avec un lien "
                   "pour choisir un nouveau mot de passe (valable 30 minutes).")
PASSWORD_RESET_DONE = "Mot de passe modifié. Vous pouvez vous connecter avec le nouveau."


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
    """Au-delà de MAX_FAILURES échecs en WINDOW secondes pour un même compte, la connexion est
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


class ResetLimiter(LoginLimiter):
    """Demandes « mot de passe oublié » : 3 au plus par adresse en 15 minutes (évite d'inonder une boîte mail)."""
    MAX_FAILURES = 3
    WINDOW = 900


login_limiter = LoginLimiter()
reset_limiter = ResetLimiter()


# --- Schémas --------------------------------------------------------------------------

# Longueurs maximales larges : les vraies règles sont vérifiées par le service (messages en français).
# guest_token : invité qui s'inscrit ou se connecte pendant sa partie, ou sur l'écran de fin ; jeton reçu
# à la connexion WebSocket (message guest_session) pour rattacher la partie à son compte.
class Registration(BaseModel):
    pseudo: str = Field(max_length=100)
    email: str = Field(max_length=300)
    password: str = Field(max_length=200)
    guest_token: Optional[str] = Field(default=None, max_length=100)


class Credentials(BaseModel):
    login: str = Field(max_length=300)  # pseudo ou adresse e-mail
    password: str = Field(max_length=200)
    guest_token: Optional[str] = Field(default=None, max_length=100)


class ForgotPassword(BaseModel):
    email: str = Field(max_length=300)


class PasswordReset(BaseModel):
    token: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


class EmailChange(BaseModel):
    current_password: str = Field(max_length=200)
    email: str = Field(max_length=300)


class PseudoChange(BaseModel):
    current_password: str = Field(max_length=200)
    pseudo: str = Field(max_length=100)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


class AccountDeletion(BaseModel):
    current_password: str = Field(max_length=200)


class UserOut(BaseModel):
    id: int
    pseudo: str
    email: Optional[str]
    is_admin: bool


class LoginOut(UserOut):
    game_claimed: bool = False  # la partie de l'invité a été rattachée au compte
    # Partie déjà terminée rattachée depuis l'écran de fin : succès qu'elle vient de débloquer
    achievements: list[dict] = []


def user_out(user: User) -> UserOut:
    return UserOut(id=user.id, pseudo=user.pseudo, email=user.email, is_admin=user.is_admin)


def login_out(user: User, guest_token: Optional[str]) -> LoginOut:
    claimed = claim_guest_game(user.id, guest_token)
    session = current_session()
    achievements = session.unlocked if claimed and session is not None and not session.running else []
    return LoginOut(**user_out(user).model_dump(), game_claimed=claimed, achievements=achievements)


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
def register(body: Registration, response: Response, db: Session = Depends(db_session)) -> LoginOut:
    """Crée le compte et connecte le joueur (avec guest_token : rattache aussi sa partie d'invité)."""
    try:
        user = service.register(db, body.pseudo, body.password, body.email)
    except AccountError as error:
        _refuse(error)
    set_login_cookie(response, user)
    return login_out(user, body.guest_token)


@router.post("/auth/login")
def login(body: Credentials, response: Response, db: Session = Depends(db_session)) -> LoginOut:
    """Connexion avec le pseudo ou l'adresse e-mail."""
    # Échecs comptés par compte : alterner pseudo et e-mail ne donne pas plus d'essais
    target = service.find_by_login(db, body.login)
    key = f"compte:{target.id}" if target is not None else f"inconnu:{body.login.strip().casefold()}"
    if login_limiter.blocked(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, TOO_MANY_ATTEMPTS)
    user = service.authenticate(db, body.login, body.password)
    if user is None:
        login_limiter.failed(key)
        # Adresse masquée : les journaux ne gardent pas les adresses e-mail en clair
        shown = mask_email(body.login) if "@" in body.login else body.login
        logger.warning("Échec de connexion pour %r", shown)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, BAD_CREDENTIALS)
    login_limiter.succeeded(key)
    set_login_cookie(response, user)
    return login_out(user, body.guest_token)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax")


@router.post("/auth/forgot-password")
async def forgot_password(body: ForgotPassword, db: Session = Depends(db_session)) -> dict:
    """Envoie un lien pour choisir un nouveau mot de passe. Réponse identique que l'adresse existe ou non."""
    email = service.normalize_email(body.email)
    if not reset_limiter.blocked(email):
        reset_limiter.failed(email)  # chaque demande compte
        user = service.find_by_email(db, email)
        if user is not None:
            token = service.create_reset_token(db, user)
            minutes = int(service.RESET_TOKEN_LIFETIME.total_seconds() // 60)
            subject, text = emails.password_reset(user.pseudo, token, minutes)
            await asyncio.to_thread(send_mail, user.email, subject, text)  # SMTP : sans bloquer le serveur
    return {"message": RESET_REQUESTED}


@router.post("/auth/reset-password")
def reset_password(body: PasswordReset, db: Session = Depends(db_session)) -> dict:
    """Nouveau mot de passe choisi depuis le lien reçu par e-mail. Tous les appareils sont déconnectés."""
    try:
        service.reset_password_with_token(db, body.token, body.new_password)
    except AccountError as error:
        _refuse(error)
    return {"message": PASSWORD_RESET_DONE}


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


@router.patch("/account/email")
def change_email(body: EmailChange, user: User = Depends(current_user),
                 db: Session = Depends(db_session)) -> UserOut:
    try:
        service.change_email(db, user, body.current_password, body.email)
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


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_account(body: AccountDeletion, response: Response, user: User = Depends(current_user),
                            db: Session = Depends(db_session)) -> None:
    """Le joueur supprime son compte (mot de passe actuel demandé) : compte et succès effacés, parties gardées
    anonymement. Sa partie en cours est arrêtée, et il est déconnecté."""
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, service.WRONG_PASSWORD)
    try:
        await remove_account(db, user, reason="à sa demande")
    except AccountError as error:
        _refuse(error)
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax")

