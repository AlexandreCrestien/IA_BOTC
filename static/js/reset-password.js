/* ==========================================================
   reset-password.js — page ouverte depuis le lien « mot de passe oublié » reçu par e-mail.
   Le jeton est dans l'adresse (?token=…) ; le serveur le vérifie (usage unique, 30 minutes).
   ========================================================== */
'use strict';

const token = new URLSearchParams(location.search).get('token');
// Le jeton est retiré de l'adresse affichée (historique, partage d'écran)
if (token) history.replaceState(null, '', location.pathname);

function showInvalidLink(text) {
    document.getElementById('reset-form').classList.add('hidden');
    const box = document.getElementById('reset-invalid');
    box.textContent = text;
    box.classList.remove('hidden');
}

function setError(text) {
    const el = document.getElementById('reset-error');
    el.textContent = text || '';
    el.classList.toggle('hidden', !text);
}

async function submitNewPassword() {
    const password = document.getElementById('reset-password').value;
    const confirm = document.getElementById('reset-password-confirm').value;
    if (!password) return setError("Veuillez entrer un nouveau mot de passe.");
    if (password !== confirm) return setError("Les deux mots de passe ne correspondent pas.");
    setError(null);

    const button = document.getElementById('reset-btn');
    button.disabled = true;
    let response;
    try {
        response = await fetch('/api/auth/reset-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token, new_password: password }),
        });
    } catch (err) {
        console.error(err);
        button.disabled = false;
        return setError("Impossible de joindre le serveur. Réessayez.");
    }
    button.disabled = false;
    if (response.ok) {
        location.replace('/?reset=done'); // l'accueil confirme et ouvre la connexion
        return;
    }
    let detail = "Le changement de mot de passe a échoué.";
    try {
        const body = await response.json();
        if (typeof body?.detail === 'string') detail = body.detail;
    } catch {
        // texte par défaut
    }
    // Lien expiré ou déjà utilisé : inutile de réessayer avec ce lien
    if (detail.includes("plus valable")) return showInvalidLink(detail);
    setError(detail);
}

if (!token) {
    showInvalidLink("Ce lien est incomplet. Depuis l'accueil, choisissez « Mot de passe oublié ? » pour en recevoir un nouveau.");
}

document.getElementById('reset-form').addEventListener('submit', (event) => {
    event.preventDefault();
    submitNewPassword();
});
