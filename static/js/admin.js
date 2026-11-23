'use strict';

// Routes réservées au compte admin : le cookie de connexion (HttpOnly) est envoyé automatiquement
const ADMIN_API_URL = "/admin/debug/all-states";
const USERS_API_URL = "/admin/users";
const LOGIN_API_URL = "/api/auth/login";
const LOGOUT_API_URL = "/api/auth/logout";
const NOT_ADMIN = "Ce compte n'a pas accès au panneau d'administration.";

// Données gardées en mémoire pour changer d'agent sans refaire de requête
let currentAdminData = null;
let selectedAgentId = null;

// Au chargement : branchement des événements, puis connexion directe si un jeton est mémorisé
window.addEventListener('DOMContentLoaded', () => {
    document.getElementById('login-form').addEventListener('submit', (event) => {
        event.preventDefault();
        login();
    });
    document.getElementById('refresh-btn').addEventListener('click', fetchAdminData);
    document.getElementById('delete-account-cancel').addEventListener('click', closeDeleteModal);
    document.getElementById('delete-account-confirm').addEventListener('click', confirmDeleteAccount);
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') closeDeleteModal();
    });
    document.getElementById('logout-btn').addEventListener('click', logout);

    // Déjà connecté (cookie) : panneau directement ; sinon l'écran de connexion reste affiché, sans erreur
    fetchAdminData({ silent: true });
});

// ================= CONNEXION / DÉCONNEXION =================
async function login() {
    const pseudoInput = document.getElementById('admin-pseudo-input');
    const passwordInput = document.getElementById('admin-password-input');
    const pseudo = pseudoInput.value.trim().normalize('NFC');
    const password = passwordInput.value;
    if (!pseudo || !password) {
        showLoginError("Veuillez entrer le pseudo et le mot de passe de l'administrateur.");
        (pseudo ? passwordInput : pseudoInput).focus();
        return;
    }

    setLoading(true);
    let response;
    try {
        response = await fetch(LOGIN_API_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ login: pseudo, password }),
        });
    } catch (err) {
        console.error(err);
        setLoading(false);
        return showLoginError("Impossible de joindre le serveur. Vérifiez qu'il est bien lancé, puis réessayez.");
    }
    setLoading(false);
    if (!response.ok) {
        // 401 identifiants refusés, 429 trop de tentatives : le serveur donne le motif
        return showLoginError(await errorDetail(response, "Connexion refusée."));
    }
    passwordInput.value = '';
    await fetchAdminData();
}

async function logout() {
    try {
        await fetch(LOGOUT_API_URL, { method: 'POST' });
    } catch (err) {
        console.error(err);
    }
    showLoginScreen(null);
}

function showLoginScreen(error) {
    currentAdminData = null;
    selectedAgentId = null;
    document.getElementById('admin-password-input').value = '';
    showLoginError(error);
    document.getElementById('dashboard-section').classList.add('hidden');
    document.getElementById('login-section').classList.remove('hidden');
    document.getElementById('admin-pseudo-input').focus();
}

// Motif d'erreur envoyé par le serveur ({"detail": "..."}), ou texte par défaut
async function errorDetail(response, fallback) {
    try {
        const body = await response.json();
        if (typeof body?.detail === 'string') return body.detail;
    } catch {
        // corps illisible : texte par défaut
    }
    return fallback;
}

function showLoginError(text) {
    const el = document.getElementById('login-error');
    el.textContent = text || '';
    el.classList.toggle('hidden', !text);
}

function setLoading(loading) {
    const loginBtn = document.getElementById('login-btn');
    const refreshBtn = document.getElementById('refresh-btn');
    loginBtn.disabled = loading;
    loginBtn.textContent = loading ? "Connexion…" : "Accéder au panneau";
    refreshBtn.disabled = loading;
    refreshBtn.textContent = loading ? "Chargement…" : "Rafraîchir";
}

// ================= RÉCUPÉRATION DES DONNÉES =================
// silent : premier chargement de la page, pas d'erreur affichée si personne n'est connecté
async function fetchAdminData({ silent = false } = {}) {
    setLoading(true);
    let response;
    try {
        response = await fetch(ADMIN_API_URL);
    } catch (err) {
        console.error(err);
        setLoading(false);
        return showFetchError("Impossible de joindre le serveur. Vérifiez qu'il est bien lancé, puis réessayez.");
    }
    setLoading(false);

    if (response.status === 401) {
        // Pas connecté, ou connexion expirée / invalidée
        return showLoginScreen(silent ? null : "Votre session a expiré. Reconnectez-vous.");
    }
    if (response.status === 403) {
        // Connecté avec un compte joueur : on le déconnecte du panneau
        await fetch(LOGOUT_API_URL, { method: 'POST' }).catch(() => {});
        return showLoginScreen(NOT_ADMIN);
    }
    if (!response.ok) {
        return showFetchError(`Erreur du serveur (${response.status}). Réessayez plus tard.`);
    }

    let data = null;
    try {
        data = await response.json();
    } catch (err) {
        console.error(err);
    }

    showLoginError(null);
    document.getElementById('login-section').classList.add('hidden');
    document.getElementById('dashboard-section').classList.remove('hidden');
    document.getElementById('last-refresh').textContent =
        `Mis à jour à ${new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`;

    renderDashboard(data);
    await fetchAccounts();
}

// ================= COMPTES =================
async function fetchAccounts() {
    let users = null;
    try {
        const response = await fetch(USERS_API_URL);
        if (response.ok) users = await response.json();
    } catch (err) {
        console.error(err);
    }
    renderAccounts(Array.isArray(users) ? users : null);
}

function renderAccounts(users) {
    const container = document.getElementById('accounts-container');
    if (users === null) {
        container.innerHTML = emptyLine("Impossible de charger les comptes.");
        return;
    }
    if (!users.length) {
        container.innerHTML = emptyLine("Aucun compte.");
        return;
    }
    container.innerHTML = `
        <table class="admin-table w-full">
            <thead>
                <tr><th>Pseudo</th><th>Adresse e-mail</th><th>Créé le</th><th>Action</th></tr>
            </thead>
            <tbody>
                ${users.map(u => `
                    <tr>
                        <td class="font-semibold">${escapeHtml(u.pseudo)}${u.is_admin ? ' <span class="opacity-60 font-normal">(admin)</span>' : ''}</td>
                        <td>${u.email ? escapeHtml(u.email) : '<span class="opacity-50">—</span>'}</td>
                        <td>${escapeHtml(formatDate(u.created_at))}</td>
                        <td>${u.is_admin ? '<span class="opacity-50">—</span>' : `
                            <div class="flex flex-wrap gap-2">
                                <button type="button" class="btn-ghost admin-btn reset-password-btn"
                                    data-user-id="${escapeHtml(u.id)}" data-pseudo="${escapeHtml(u.pseudo)}">
                                    Réinitialiser le mot de passe
                                </button>
                                <button type="button" class="btn-ghost admin-btn admin-btn-danger delete-account-btn"
                                    data-user-id="${escapeHtml(u.id)}" data-pseudo="${escapeHtml(u.pseudo)}">
                                    Supprimer le compte
                                </button>
                            </div>`}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
    container.querySelectorAll('.reset-password-btn').forEach(btn => {
        btn.addEventListener('click', () => resetPassword(btn.dataset.userId, btn.dataset.pseudo));
    });
    container.querySelectorAll('.delete-account-btn').forEach(btn => {
        btn.addEventListener('click', () => openDeleteModal(btn.dataset.userId, btn.dataset.pseudo));
    });
}

// ================= SUPPRESSION D'UN COMPTE (confirmation en modale) =================
let accountToDelete = null; // { id, pseudo }

function openDeleteModal(userId, pseudo) {
    accountToDelete = { id: userId, pseudo };
    document.getElementById('delete-account-text').textContent = `Compte : ${pseudo}`;
    setDeleteError(null);
    document.getElementById('modal-delete-account').classList.remove('hidden');
    document.getElementById('delete-account-cancel').focus(); // Entrée par réflexe : annule
}

function closeDeleteModal() {
    accountToDelete = null;
    document.getElementById('modal-delete-account').classList.add('hidden');
}

function setDeleteError(text) {
    const el = document.getElementById('delete-account-error');
    el.textContent = text || '';
    el.classList.toggle('hidden', !text);
}

async function confirmDeleteAccount() {
    if (!accountToDelete) return;
    const { id, pseudo } = accountToDelete;
    const button = document.getElementById('delete-account-confirm');
    button.disabled = true;
    let response;
    try {
        response = await fetch(`${USERS_API_URL}/${encodeURIComponent(id)}`, { method: 'DELETE' });
    } catch (err) {
        console.error(err);
        button.disabled = false;
        return setDeleteError("Impossible de joindre le serveur.");
    }
    button.disabled = false;
    if (response.status === 401) {
        closeDeleteModal();
        return showLoginScreen("Votre session a expiré. Reconnectez-vous.");
    }
    if (!response.ok) return setDeleteError(await errorDetail(response, "La suppression a échoué."));
    closeDeleteModal();
    showResetResult(`Le compte ${pseudo} a été supprimé.`);
    await fetchAccounts();
}

async function resetPassword(userId, pseudo) {
    if (!window.confirm(`Réinitialiser le mot de passe de ${pseudo} ? Il sera déconnecté.`)) return;
    let response;
    try {
        response = await fetch(`${USERS_API_URL}/${encodeURIComponent(userId)}/reset-password`, { method: 'POST' });
    } catch (err) {
        console.error(err);
        return showResetResult("Impossible de joindre le serveur.");
    }
    if (response.status === 401) return showLoginScreen("Votre session a expiré. Reconnectez-vous.");
    if (!response.ok) return showResetResult(await errorDetail(response, "La réinitialisation a échoué."));
    const body = await response.json();
    showResetResult(`Mot de passe temporaire de ${body.pseudo} : ${body.temporary_password} — ` +
        "transmettez-le-lui, il pourra le changer depuis son profil. Il ne sera plus affiché.");
}

function showResetResult(text) {
    const el = document.getElementById('reset-result');
    el.textContent = text;
    el.classList.remove('hidden');
}

function formatDate(iso) {
    const date = new Date(iso);
    return Number.isNaN(date.getTime()) ? '—' : date.toLocaleDateString('fr-FR');
}

// Erreur affichée là où se trouve l'utilisateur (écran de connexion ou panneau)
function showFetchError(text) {
    const dashboardVisible = !document.getElementById('dashboard-section').classList.contains('hidden');
    if (dashboardVisible) showNotice(text);
    else showLoginError(text);
}

function showNotice(text) {
    const el = document.getElementById('no-data-notice');
    el.textContent = text || '';
    el.classList.toggle('hidden', !text);
}

// ================= RENDU DU TABLEAU DE BORD =================
// Champs envoyés par la route /admin/debug/all-states (backend/server/admin.py)
function renderDashboard(data) {
    if (!data || typeof data !== 'object') {
        showNotice("Réponse inattendue du serveur.");
        data = {};
    } else {
        // Aucune partie lancée depuis le démarrage du serveur : message du serveur
        showNotice(data.game_in_progress === false && !data.players ? data.message : null);
    }
    currentAdminData = data;

    // Champ absent → "—" (inconnu), plutôt que 0 qui laisserait croire à une partie vide
    document.getElementById('stat-agents-count').textContent = Array.isArray(data.agents) ? data.agents.length : '—';
    document.getElementById('stat-turn-phase').textContent =
        data.turn != null ? `Tour ${data.turn}${data.phase ? ` · ${data.phase}` : ''}${data.status === 'terminée' ? ' (terminée)' : ''}` : '—';
    document.getElementById('stat-channels-count').textContent = Array.isArray(data.channels) ? data.channels.length : '—';

    renderPlayers(data.players || []);
    renderPublicHistory(data.public_history || []);
    renderAgents();
    renderNightActions(data.night_actions || []);
    renderAgentFailures(data.agent_failures || []);
    renderNightHistory(data.night_history || []);
    renderVoteHistory(data.vote_history || []);
}

function emptyLine(text) {
    return `<span class="italic opacity-60">${escapeHtml(text)}</span>`;
}

function renderPlayers(players) {
    const container = document.getElementById('players-container');
    if (!players.length) {
        container.innerHTML = emptyLine("Aucune partie en cours.");
        return;
    }
    container.innerHTML = `
        <table class="admin-table w-full">
            <thead>
                <tr><th>Joueur</th><th>Rôle</th><th>Camp</th><th>Personnalité</th><th>Statut</th></tr>
            </thead>
            <tbody>
                ${players.map(p => `
                    <tr>
                        <td class="font-semibold">${escapeHtml(p.name)}${p.is_human ? ' <span class="opacity-60 font-normal">(humain)</span>' : ''}</td>
                        <td class="text-gold">${escapeHtml(p.role)}</td>
                        <td><span class="role-tag ${teamTagClass(p.team)}">${escapeHtml(p.team)}</span></td>
                        <td>${p.personality ? escapeHtml(p.personality) : '<span class="opacity-50">—</span>'}</td>
                        <td>${p.alive
                            ? '<span class="status-alive">Vivant</span>'
                            : `<span class="status-dead">Mort</span> <span class="opacity-60">· vote ${p.has_vote ? 'dispo' : 'utilisé'}</span>`}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

// Mêmes couleurs d'étiquette que le Codex du jeu
function teamTagClass(team) {
    return { "Démon": "tag-demon", "Complice": "tag-accomplice", "Paria": "tag-outcast" }[team] || "tag-good";
}

function renderNightActions(actions) {
    const container = document.getElementById('night-actions-container');
    container.innerHTML = actions.length
        ? actions.map(a => `
            <div class="history-line">
                <span class="memory-role mr-2">Nuit ${escapeHtml(a.turn)}</span>
                <span class="font-semibold text-gold">${escapeHtml(a.player)}</span>
                <span class="opacity-50 mx-1">·</span>
                <span class="memory-content">${escapeHtml(a.content)}</span>
            </div>
        `).join('')
        : emptyLine("Aucune action de nuit pour l'instant.");
}

// IA dont le modèle n'a pas répondu : moment, agent, et ce qu'elle devait faire
function renderAgentFailures(failures) {
    const container = document.getElementById('agent-failures-container');
    container.innerHTML = failures.length
        ? failures.map(f => `
            <div class="history-line">
                <span class="memory-role mr-2">${escapeHtml(f.moment)}</span>
                <span class="font-semibold text-gold">${escapeHtml(f.agent)}</span>
                <span class="opacity-50 mx-1">·</span>
                <span class="memory-content">${escapeHtml(f.step)}</span>
            </div>
        `).join('')
        : emptyLine("Aucune IA indisponible pour l'instant.");
}

function renderNightHistory(history) {
    const container = document.getElementById('night-history-container');
    container.innerHTML = history.length
        ? history.map(item => `
            <div class="history-line ${item.type === 'result' ? 'is-death' : ''}">
                <span class="memory-role mr-2">Tour ${escapeHtml(item.turn)}</span>
                <span class="memory-content">${escapeHtml(item.info)}</span>
            </div>
        `).join('')
        : emptyLine("Aucun événement nocturne pour l'instant.");
}

function renderVoteHistory(votes) {
    const container = document.getElementById('vote-history-container');
    if (!votes.length) {
        container.innerHTML = emptyLine("Aucun vote pour l'instant.");
        return;
    }
    // Regroupement par tour, du plus récent au plus ancien
    const turns = {};
    votes.forEach(v => {
        if (!turns[v.turn]) turns[v.turn] = { executed: v.executed, ballots: [] };
        turns[v.turn].ballots.push(v);
    });
    container.innerHTML = Object.keys(turns).sort((a, b) => b - a).map(turn => `
        <div class="flex flex-col gap-1">
            <div class="memory-role">Tour ${escapeHtml(turn)} — ${turns[turn].executed ? `${escapeHtml(turns[turn].executed)} exécuté·e` : 'aucune exécution'}</div>
            ${turns[turn].ballots.map(b => `
                <div class="history-line">
                    <span class="font-semibold">${escapeHtml(b.voter)}</span>
                    <span class="opacity-50 mx-1">→</span>
                    <span class="${b.target ? 'text-gold' : 'italic opacity-60'}">${b.target ? escapeHtml(b.target) : 'Personne'}</span>
                </div>
            `).join('')}
        </div>
    `).join('');
}

function renderPublicHistory(history) {
    const container = document.getElementById('public-history-container');
    if (!Array.isArray(history) || history.length === 0) {
        container.innerHTML = `<span class="italic opacity-60">Aucun message enregistré dans l'historique public.</span>`;
        return;
    }
    container.innerHTML = history.map(item => `
        <div class="history-line">
            ${item.moment ? `<span class="memory-role mr-2">${escapeHtml(item.moment)}</span>` : ''}
            <span class="font-semibold text-gold">${escapeHtml(item.sender || 'Système')}</span>
            <span class="opacity-50 mx-1">·</span>
            <span class="memory-content">${escapeHtml(contentToText(item.content ?? item))}</span>
        </div>
    `).join('');
    container.scrollTop = container.scrollHeight;
}

function getAgentHistories() {
    return currentAdminData?.agent_histories || {};
}

// Liste des agents + mémoire de l'agent sélectionné
function renderAgents() {
    const agentHistories = getAgentHistories();
    const agentIds = Object.keys(agentHistories);
    const tabsContainer = document.getElementById('agents-tabs-container');
    const detailContainer = document.getElementById('agent-detail-container');

    if (agentIds.length === 0) {
        tabsContainer.innerHTML = `<span class="italic opacity-60 text-sm">Aucun agent disponible.</span>`;
        detailContainer.innerHTML = `<span class="italic opacity-60 text-sm">Aucune mémoire disponible.</span>`;
        return;
    }

    // Premier agent par défaut, ou si l'agent sélectionné n'existe plus
    if (!selectedAgentId || !agentIds.includes(selectedAgentId)) {
        selectedAgentId = agentIds[0];
    }

    tabsContainer.innerHTML = agentIds.map(agentId => {
        const count = Array.isArray(agentHistories[agentId]) ? agentHistories[agentId].length : 0;
        return `
            <button type="button" class="agent-tab ${agentId === selectedAgentId ? 'is-active' : ''}" data-agent-id="${escapeHtml(agentId)}">
                <span class="truncate">${escapeHtml(agentId)}</span>
                <span class="agent-count">${count}</span>
            </button>
        `;
    }).join('');

    // data-attribute + écouteur : un identifiant contenant une apostrophe ne casse plus le bouton
    tabsContainer.querySelectorAll('.agent-tab').forEach(btn => {
        btn.addEventListener('click', () => selectAgent(btn.dataset.agentId));
    });

    renderAgentDetail(selectedAgentId, agentHistories);
}

function selectAgent(agentId) {
    selectedAgentId = agentId;
    renderAgents();
}

function renderAgentDetail(agentId, agentHistories) {
    const detailContainer = document.getElementById('agent-detail-container');
    const messages = Array.isArray(agentHistories[agentId]) ? agentHistories[agentId] : [];

    const header = `
        <div class="flex items-center justify-between gap-2 pb-2 mb-3 border-b border-[var(--border)]">
            <span class="font-display text-lg text-gold truncate">Mémoire de l'agent : ${escapeHtml(agentId)}</span>
            <span class="text-xs opacity-60 shrink-0">${messages.length} message(s) en contexte</span>
        </div>
    `;

    if (messages.length === 0) {
        detailContainer.innerHTML = header + `<span class="italic opacity-60 text-sm">La mémoire de cet agent est vide.</span>`;
        return;
    }

    detailContainer.innerHTML = header + `
        <div class="flex flex-col gap-2 max-h-[420px] overflow-y-auto pr-2">
            ${messages.map(msg => {
                const role = String(msg.role || 'inconnu').toLowerCase();
                return `
                    <div class="memory-msg" data-role="${escapeHtml(role)}">
                        <div class="memory-role mb-1">${escapeHtml(role)}</div>
                        <div class="memory-content">${escapeHtml(contentToText(msg.content ?? msg))}</div>
                    </div>
                `;
            }).join('')}
        </div>
    `;
}

// ================= UTILITAIRES =================
// Contenu texte d'un message, quelle que soit sa forme (texte, objet, liste de blocs…)
function contentToText(content) {
    if (typeof content === 'string') return content;
    try {
        return JSON.stringify(content, null, 2);
    } catch {
        return String(content);
    }
}

// Les réponses des LLM sont affichées comme du texte, jamais interprétées comme du HTML
function escapeHtml(text) {
    if (text == null) return '';
    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}
