"""Envoi des e-mails (mot de passe oublié, avertissement avant suppression d'un compte inactif).

Mode choisi par MAIL_MODE (.env) :
- "console" (défaut) : l'e-mail n'est pas envoyé, il est écrit dans la console du serveur
  (pratique en local : le lien « mot de passe oublié » s'y copie directement) ;
- "smtp" : envoi à un serveur SMTP (SMTP_HOST, SMTP_PORT, MAIL_FROM ; SMTP_USER, SMTP_PASSWORD et
  SMTP_STARTTLS pour un vrai fournisseur). En local : Mailpit (docker-compose.yml), qui capture les e-mails
  et les affiche sur http://localhost:8025 sans rien envoyer pour de vrai ;
- "memory" : gardé dans OUTBOX (tests).

Un échec d'envoi est journalisé mais ne fait jamais échouer la requête : la réponse au joueur ne doit pas
révéler si l'adresse existe (mot de passe oublié).
"""
import logging
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Mail:
    to: str
    subject: str
    body: str


OUTBOX: list[Mail] = []  # mode "memory" (tests)


def mask_email(email: str) -> str:
    """Adresse masquée pour les journaux : « zoe@exemple.fr » → « z***@exemple.fr »."""
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def app_url() -> str:
    """Adresse du jeu dans les liens envoyés par e-mail (APP_URL, sinon le serveur local)."""
    return os.getenv("APP_URL", "http://127.0.0.1:8000").rstrip("/")


def _send_smtp(mail: Mail) -> None:
    message = EmailMessage()
    message["From"] = os.getenv("MAIL_FROM", "Lantern Hollow <no-reply@lantern-hollow.local>")
    message["To"] = mail.to
    message["Subject"] = mail.subject
    message.set_content(mail.body)
    host, port = os.getenv("SMTP_HOST", "localhost"), int(os.getenv("SMTP_PORT", "1025"))
    with smtplib.SMTP(host, port, timeout=10) as smtp:
        if os.getenv("SMTP_STARTTLS", "").lower() in ("1", "true", "yes"):
            smtp.starttls()
        if os.getenv("SMTP_USER"):
            smtp.login(os.environ["SMTP_USER"], os.getenv("SMTP_PASSWORD", ""))
        smtp.send_message(message)


def send_mail(to: str, subject: str, body: str) -> bool:
    """Envoie (ou affiche, ou garde) l'e-mail selon MAIL_MODE. Renvoie False si l'envoi a échoué."""
    mail = Mail(to=to, subject=subject, body=body)
    mode = os.getenv("MAIL_MODE", "console").lower()
    if mode == "memory":
        OUTBOX.append(mail)
        return True
    if mode == "smtp":
        try:
            _send_smtp(mail)
            logger.info("E-mail envoyé à %s : %s", mask_email(to), subject)
            return True
        except (OSError, smtplib.SMTPException):
            logger.exception("Échec de l'envoi de l'e-mail « %s » à %s", subject, mask_email(to))
            return False
    # Mode console (développement local) : l'e-mail entier, adresse et lien compris, pour pouvoir s'en servir
    separator = "-" * 64
    logger.info("E-mail (MAIL_MODE=console, non envoyé)\n%s\nÀ : %s\nObjet : %s\n\n%s\n%s",
                separator, to, subject, body, separator)
    return True
