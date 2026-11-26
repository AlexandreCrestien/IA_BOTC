/* ==========================================================
   verify-email.js — page ouverte depuis le lien de vérification reçu par e-mail.
   Le jeton est dans l'adresse (?token=…) ; le serveur le vérifie (usage unique, 24 heures).
   Le lien marche sans être connecté (il peut être ouvert sur un autre appareil).
   ========================================================== */
'use strict';

const token = new URLSearchParams(location.search).get('token');
// Le jeton est retiré de l'adresse affichée (historique, partage d'écran)
if (token) history.replaceState(null, '', location.pathname);

function show(title, text, success) {
    document.getElementById('verify-title').textContent = title;
    document.getElementById('verify-status').textContent = text;
    document.getElementById('verify-continue').classList.toggle('hidden', !success);
}

async function verify() {
    if (!token) {
        show("Lien incomplet", "Ce lien est incomplet. Connectez-vous : votre tableau de bord permet d'en recevoir un nouveau.", false);
        return;
    }
    let response;
    try {
        response = await fetch('/api/auth/verify-email', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token }),
        });
    } catch (err) {
        console.error(err);
        show("Serveur injoignable", "Impossible de joindre le serveur. Réessayez en rouvrant le lien.", false);
        return;
    }
    let body = null;
    try {
        body = await response.json();
    } catch {
        // réponse illisible : message par défaut
    }
    if (response.ok) {
        show("Adresse confirmée", `Merci ${body?.pseudo ?? ''} : votre adresse ${body?.email ?? ''} est confirmée.`.replace(/\s+:/, ' :'), true);
        return;
    }
    show("Lien non valable", typeof body?.detail === 'string' ? body.detail : "La confirmation a échoué.", false);
}

verify();
