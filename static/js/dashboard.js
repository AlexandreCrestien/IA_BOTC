/* ==========================================================
   dashboard.js — tableau de bord du joueur connecté :
   partie (commencer, reprendre, abandonner), statistiques, historique, succès, profil.
   Routes : /api/auth/*, /api/game/*, /api/me/*, /api/account/* (backend/server).
   ========================================================== */
'use strict';

const PLAY_URL = '/?play'; // l'accueil connecte directement le joueur à sa partie

const STATUS_LABELS = {
    won: "Victoire",
    lost: "Défaite",
    abandoned: "Défaite (abandon)",
    interrupted: "Interrompue (non comptée)",
};
const SIDE_LABELS = { good: "Villageois", evil: "Démons" };
const SIDE_TAGS = { good: "tag-good", evil: "tag-demon" };

let currentUser = null;

// ================= APPELS AU SERVEUR =================
async function api(url, { method = 'GET', data } = {}) {
    const options = { method };
    if (data !== undefined) {
        options.headers = { 'Content-Type': 'application/json' };
        options.body = JSON.stringify(data);
    }
    try {
        const response = await fetch(url, options);
        let body = null;
        try {
            body = await response.json();
        } catch {
            // réponse vide (204) ou illisible
        }
        if (response.status === 401 && !url.startsWith('/api/account')) {
            // Plus connecté (déconnexion ailleurs, session expirée) : retour à l'accueil
            location.replace('/');
        }
        return { ok: response.ok, status: response.status, body };
    } catch (err) {
        console.error(err);
        return { ok: false, status: 0, body: null };
    }
}

function errorText(result, fallback) {
    if (result.status === 0) return "Impossible de joindre le serveur. Vérifiez qu'il est bien lancé, puis réessayez.";
    return typeof result.body?.detail === 'string' ? result.body.detail : fallback;
}

// ================= AU CHARGEMENT =================
window.addEventListener('DOMContentLoaded', async () => {
    bindEvents();
    const me = await api('/api/auth/me');
    if (!me.ok) {
        if (me.status === 0) showGameError(errorText(me, ""));
        return; // 401 : redirection vers l'accueil
    }
    currentUser = me.body;
    showIdentity();
    document.getElementById('dashboard-main').classList.remove('hidden');
    await refreshAll();
});

// Retour sur l'onglet (ouvert depuis la partie) : la partie a pu avancer ou se terminer
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && currentUser) refreshAll();
});

// Raccourcis de l'en-tête : le lien de la section affichée est mis en valeur pendant le défilement.
// Section affichée : la dernière dont le haut est passé sous l'en-tête. En haut de la page : aucune.
// En bas de la page (après avoir défilé) : la dernière, même si son haut n'atteint pas l'en-tête.
const HEADER_OFFSET = 96; // en-tête collant (4rem) + marge

function currentSectionId(links) {
    const ids = [...links].map(link => link.dataset.section);
    if (window.scrollY <= 0) return null;
    if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2) return ids[ids.length - 1];
    return ids.filter(id => document.getElementById(id)?.getBoundingClientRect().top <= HEADER_OFFSET).pop() ?? null;
}

function watchSections() {
    const links = document.querySelectorAll('.dash-nav-link');
    let scheduled = false;
    const update = () => {
        scheduled = false;
        const current = currentSectionId(links);
        links.forEach(link => link.classList.toggle('is-active', link.dataset.section === current));
    };
    window.addEventListener('scroll', () => {
        if (!scheduled) {
            scheduled = true;
            requestAnimationFrame(update);
        }
    }, { passive: true });
    update();
}

function bindEvents() {
    watchSections();
    document.getElementById('start-game-btn').addEventListener('click', () => { location.href = PLAY_URL; });
    document.getElementById('resume-game-btn').addEventListener('click', () => { location.href = PLAY_URL; });
    document.getElementById('abandon-game-btn').addEventListener('click', () => toggleAbandonModal(true));
    document.getElementById('abandon-cancel').addEventListener('click', () => toggleAbandonModal(false));
    document.getElementById('abandon-confirm').addEventListener('click', abandonGame);
    document.getElementById('dashboard-logout').addEventListener('click', logout);
    document.getElementById('pseudo-form').addEventListener('submit', (event) => {
        event.preventDefault();
        changePseudo();
    });
    document.getElementById('email-form').addEventListener('submit', (event) => {
        event.preventDefault();
        changeEmail();
    });
    document.getElementById('password-form').addEventListener('submit', (event) => {
        event.preventDefault();
        changePassword();
    });
    document.getElementById('export-data-btn').addEventListener('click', exportData);
    document.getElementById('delete-account-btn').addEventListener('click', openDeleteModal);
    document.getElementById('delete-account-cancel').addEventListener('click', closeDeleteModal);
    document.getElementById('delete-account-form').addEventListener('submit', (event) => {
        event.preventDefault();
        deleteAccount();
    });
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            toggleAbandonModal(false);
            closeDeleteModal();
        }
    });
}

async function refreshAll() {
    await Promise.all([refreshGame(), refreshStats(), refreshHistory(), refreshAchievements()]);
}

// ================= PARTIE =================
async function refreshGame() {
    const result = await api('/api/game/current');
    const game = result.ok && result.body ? result.body : { running: false };
    const mine = game.running && game.yours;
    const start = document.getElementById('start-game-btn');

    start.disabled = game.running;
    start.textContent = game.running ? "Une partie est déjà en cours" : "Commencer une partie";
    document.getElementById('resume-game-btn').classList.toggle('hidden', !mine);
    document.getElementById('abandon-game-btn').classList.toggle('hidden', !mine);
    document.getElementById('game-status').textContent = !game.running
        ? "Aucune partie en cours."
        : mine
            ? `Votre partie est en cours${game.turn ? ` (tour ${game.turn})` : ''}.`
            : "Une autre partie est en cours sur ce serveur.";
}

function toggleAbandonModal(open) {
    document.getElementById('modal-abandon').classList.toggle('hidden', !open);
}

async function abandonGame() {
    toggleAbandonModal(false);
    const result = await api('/api/game/abandon', { method: 'POST' });
    showGameError(result.ok ? null : errorText(result, "L'abandon a échoué."));
    await refreshAll();
}

function showGameError(text) {
    const el = document.getElementById('game-error');
    el.textContent = text || '';
    el.classList.toggle('hidden', !text);
}

async function logout() {
    await api('/api/auth/logout', { method: 'POST' });
    location.href = '/';
}

// ================= STATISTIQUES =================
function percent(rate) {
    return rate == null ? '—' : `${Math.round(rate * 100)} %`;
}

function winsText(summary) {
    if (!summary || !summary.played) return "aucune partie";
    return `${summary.wins} victoire${summary.wins > 1 ? 's' : ''} sur ${summary.played}`;
}

async function refreshStats() {
    const result = await api('/api/me/stats');
    if (!result.ok || !result.body) return;
    const stats = result.body;
    setText('stat-played', stats.played ?? '—');
    setText('stat-win-rate', percent(stats.win_rate));
    setText('stat-wins', winsText(stats));
    setText('stat-good-rate', percent(stats.good?.win_rate));
    setText('stat-good-wins', winsText(stats.good));
    setText('stat-evil-rate', percent(stats.evil?.win_rate));
    setText('stat-evil-wins', winsText(stats.evil));
    setText('stat-turns', stats.average_turns ?? '—');
}

// ================= HISTORIQUE =================
function formatDate(iso) {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return '—';
    return date.toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

async function refreshHistory() {
    const result = await api('/api/me/games');
    const container = document.getElementById('history-container');
    const games = result.ok && Array.isArray(result.body) ? result.body : [];
    if (!games.length) {
        container.innerHTML = `<span class="italic opacity-60">Aucune partie jouée pour l'instant.</span>`;
        return;
    }
    container.innerHTML = `
        <table class="dash-table">
            <thead><tr><th>Date</th><th>Rôle</th><th>Résultat</th><th>Tours</th></tr></thead>
            <tbody>
                ${games.map(g => `
                    <tr data-status="${escapeHtml(g.status)}">
                        <td>${escapeHtml(formatDate(g.date))}</td>
                        <td>${escapeHtml(g.role_name)}
                            <span class="role-tag ${SIDE_TAGS[g.alignment] || ''}">${escapeHtml(SIDE_LABELS[g.alignment] || g.alignment)}</span></td>
                        <td class="result-${escapeHtml(g.status)}">${escapeHtml(STATUS_LABELS[g.status] || g.status)}</td>
                        <td>${escapeHtml(g.turns)}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

// ================= SUCCÈS =================
async function refreshAchievements() {
    const result = await api('/api/me/achievements');
    const list = result.ok && Array.isArray(result.body) ? result.body : [];
    const unlocked = list.filter(a => a.unlocked).length;
    setText('achievements-count', list.length ? `(${unlocked} / ${list.length})` : '');
    document.getElementById('achievements-container').innerHTML = list.map(a => `
        <div class="achievement ${a.unlocked ? 'is-unlocked' : 'is-locked'}" data-code="${escapeHtml(a.code)}">
            <span class="achievement-icon" aria-hidden="true">${a.unlocked ? '🏆' : (a.hidden ? '❔' : '🔒')}</span>
            <div class="min-w-0">
                <div class="achievement-title">${escapeHtml(a.title)}</div>
                <div class="achievement-description">${escapeHtml(a.description)}</div>
                ${a.message ? `<div class="achievement-message">${escapeHtml(a.message)}</div>` : ''}
            </div>
        </div>
    `).join('');
}

// ================= PROFIL =================
function setFormMessages(prefix, error, success) {
    const errorEl = document.getElementById(`${prefix}-error`);
    const successEl = document.getElementById(`${prefix}-success`);
    errorEl.textContent = error || '';
    errorEl.classList.toggle('hidden', !error);
    successEl.textContent = success || '';
    successEl.classList.toggle('hidden', !success);
}

async function changePseudo() {
    const pseudo = document.getElementById('new-pseudo').value.trim().normalize('NFC');
    const password = document.getElementById('pseudo-current-password').value;
    if (!pseudo || !password) return setFormMessages('pseudo', "Entrez le nouveau pseudo et votre mot de passe actuel.");

    const result = await api('/api/account/pseudo', { method: 'PATCH', data: { pseudo, current_password: password } });
    if (!result.ok) return setFormMessages('pseudo', errorText(result, "Le changement de pseudo a échoué."));
    currentUser = result.body;
    showIdentity();
    document.getElementById('pseudo-form').reset();
    setFormMessages('pseudo', null, `Votre pseudo est maintenant ${currentUser.pseudo}.`);
}

async function changeEmail() {
    const email = document.getElementById('new-email').value.trim();
    const password = document.getElementById('email-current-password').value;
    if (!email || !password) return setFormMessages('email', "Entrez la nouvelle adresse et votre mot de passe actuel.");

    const result = await api('/api/account/email', { method: 'PATCH', data: { email, current_password: password } });
    if (!result.ok) return setFormMessages('email', errorText(result, "Le changement d'adresse a échoué."));
    currentUser = result.body;
    showIdentity();
    document.getElementById('email-form').reset();
    setFormMessages('email', null, `Votre adresse est maintenant ${currentUser.email}.`);
}

// Pseudo dans l'en-tête, adresse e-mail dans le profil
function showIdentity() {
    document.getElementById('dashboard-pseudo').textContent = currentUser.pseudo;
    document.getElementById('profile-email').textContent = currentUser.email || "aucune";
}

async function changePassword() {
    const current = document.getElementById('password-current').value;
    const next = document.getElementById('password-new').value;
    const confirm = document.getElementById('password-confirm').value;
    if (!current || !next) return setFormMessages('password', "Entrez votre mot de passe actuel et le nouveau.");
    if (next !== confirm) return setFormMessages('password', "Les deux nouveaux mots de passe ne correspondent pas.");

    const result = await api('/api/account/password', { method: 'PATCH', data: { current_password: current, new_password: next } });
    if (!result.ok) return setFormMessages('password', errorText(result, "Le changement de mot de passe a échoué."));
    document.getElementById('password-form').reset();
    setFormMessages('password', null, "Mot de passe modifié. Vos autres appareils ont été déconnectés.");
}

// ================= EXPORT DES DONNÉES =================
// Le serveur renvoie le fichier (Content-Disposition) ; on le télécharge sans quitter la page
async function exportData() {
    const button = document.getElementById('export-data-btn');
    const errorEl = document.getElementById('export-error');
    errorEl.classList.add('hidden');
    button.disabled = true;
    try {
        const response = await fetch('/api/me/export');
        if (response.status === 401) return location.replace('/');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const disposition = response.headers.get('Content-Disposition') || '';
        const filename = disposition.match(/filename="([^"]+)"/)?.[1] || 'lantern-hollow-mes-donnees.json';
        const url = URL.createObjectURL(await response.blob());
        const link = Object.assign(document.createElement('a'), { href: url, download: filename });
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    } catch (err) {
        console.error(err);
        errorEl.textContent = "Le téléchargement a échoué. Réessayez.";
        errorEl.classList.remove('hidden');
    } finally {
        button.disabled = false;
    }
}

// ================= SUPPRESSION DU COMPTE =================
function openDeleteModal() {
    document.getElementById('delete-account-form').reset();
    setDeleteError(null);
    document.getElementById('modal-delete-account').classList.remove('hidden');
    document.getElementById('delete-account-password').focus();
}

function closeDeleteModal() {
    document.getElementById('modal-delete-account').classList.add('hidden');
}

function setDeleteError(text) {
    const el = document.getElementById('delete-account-error');
    el.textContent = text || '';
    el.classList.toggle('hidden', !text);
}

async function deleteAccount() {
    const password = document.getElementById('delete-account-password').value;
    if (!password) return setDeleteError("Entrez votre mot de passe actuel pour confirmer.");
    const button = document.getElementById('delete-account-confirm');
    button.disabled = true;
    const result = await api('/api/account', { method: 'DELETE', data: { current_password: password } });
    button.disabled = false;
    if (!result.ok) return setDeleteError(errorText(result, "La suppression a échoué."));
    location.replace('/?deleted'); // l'accueil confirme la suppression
}

// ================= UTILITAIRES =================
function setText(id, text) {
    document.getElementById(id).textContent = text;
}

function escapeHtml(text) {
    if (text == null) return '';
    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}
