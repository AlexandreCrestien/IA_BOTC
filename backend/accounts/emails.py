"""Textes des e-mails envoyés aux joueurs (français, texte brut). L'envoi : backend/mail.py."""
import os
from datetime import datetime

from backend.mail import app_url, mask_email

SIGNATURE = "\n\n—\nLantern Hollow\n(E-mail automatique : merci de ne pas y répondre.)"


def password_reset(pseudo: str, token: str, minutes: int) -> tuple[str, str]:
    """(objet, texte) de l'e-mail « mot de passe oublié »."""
    link = f"{app_url()}/reset-password.html?token={token}"
    body = (
        f"Bonjour {pseudo},\n\n"
        "Une demande de nouveau mot de passe a été faite pour votre compte Lantern Hollow.\n"
        f"Pour choisir un nouveau mot de passe, ouvrez ce lien (valable {minutes} minutes, une seule fois) :\n\n"
        f"{link}\n\n"
        "Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail : votre mot de passe ne change pas."
        + SIGNATURE
    )
    return "Lantern Hollow : choisir un nouveau mot de passe", body


def inactivity_warning(pseudo: str, deletion: datetime) -> tuple[str, str]:
    """(objet, texte) de l'avertissement envoyé avant la suppression d'un compte inactif."""
    body = (
        f"Bonjour {pseudo},\n\n"
        "Vous ne vous êtes pas connecté à Lantern Hollow depuis bientôt un an.\n"
        f"Sans connexion d'ici le {deletion.strftime('%d/%m/%Y')}, votre compte et vos succès seront supprimés "
        "automatiquement ; le résumé de vos parties sera gardé de façon anonyme pour les statistiques du jeu.\n\n"
        f"Pour garder votre compte, il suffit de vous connecter : {app_url()}/"
        + SIGNATURE
    )
    return "Lantern Hollow : votre compte sera bientôt supprimé", body


def email_verification(pseudo: str, token: str, hours: int, change: bool) -> tuple[str, str]:
    """(objet, texte) de l'e-mail de vérification : à l'inscription, ou pour confirmer une nouvelle adresse."""
    link = f"{app_url()}/verify-email.html?token={token}"
    if change:
        reason = "Vous avez demandé à utiliser cette adresse pour votre compte Lantern Hollow."
        otherwise = "l'adresse du compte ne changera pas."
    else:
        reason = "Bienvenue à Lantern Hollow ! Il reste une étape pour activer votre compte."
        otherwise = "un compte jamais vérifié est supprimé automatiquement au bout de 72 heures."
    body = (
        f"Bonjour {pseudo},\n\n"
        f"{reason}\n"
        f"Pour confirmer votre adresse e-mail, ouvrez ce lien (valable {hours} heures, une seule fois) :\n\n"
        f"{link}\n\n"
        f"Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail : {otherwise}"
        + SIGNATURE
    )
    subject = "Lantern Hollow : confirmez votre nouvelle adresse" if change else "Lantern Hollow : confirmez votre adresse e-mail"
    return subject, body


def _contact_line() -> str:
    """Qui prévenir si la modification ne vient pas du joueur : CONTACT_EMAIL, sinon ADMIN_EMAIL (.env)."""
    contact = os.getenv("CONTACT_EMAIL") or os.getenv("ADMIN_EMAIL")
    where = f": {contact}" if contact else " du jeu"
    return ("Si vous n'êtes pas à l'origine de cette modification, quelqu'un a peut-être accès à votre compte. "
            f"Contactez l'administrateur {where}.")


def _when(moment: datetime) -> str:
    return moment.strftime("%d/%m/%Y à %H:%M (heure UTC)")


def email_changed(pseudo: str, new_email: str, moment: datetime) -> tuple[str, str]:
    """(objet, texte) envoyé à l'ANCIENNE adresse quand une nouvelle adresse a été confirmée."""
    body = (
        f"Bonjour {pseudo},\n\n"
        f"L'adresse e-mail de votre compte Lantern Hollow a été remplacée par {mask_email(new_email)} "
        f"le {_when(moment)}. Cette adresse-ci ne recevra plus d'e-mails du jeu.\n\n"
        + _contact_line()
        + SIGNATURE
    )
    return "Lantern Hollow : l'adresse de votre compte a changé", body


def password_changed(pseudo: str, moment: datetime, how: str) -> tuple[str, str]:
    """(objet, texte) après un changement de mot de passe. how : « depuis votre profil »,
    « avec le lien « mot de passe oublié » » ou « par l'administrateur »."""
    body = (
        f"Bonjour {pseudo},\n\n"
        f"Le mot de passe de votre compte Lantern Hollow a été modifié {how}, le {_when(moment)}. "
        "Par sécurité, tous les appareils connectés à votre compte ont été déconnectés.\n\n"
        + _contact_line()
        + SIGNATURE
    )
    return "Lantern Hollow : votre mot de passe a été modifié", body
