"""Textes des e-mails envoyés aux joueurs (français, texte brut). L'envoi : backend/mail.py."""
from datetime import datetime

from backend.mail import app_url

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
