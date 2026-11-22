/* ==========================================================
   account.js — comptes côté jeu : accueil (invité, connexion, inscription),
   connexion automatique du joueur connecté, menu de la partie,
   inscription ou connexion d'un invité pendant la partie ou sur l'écran de fin.

   La connexion est un cookie HttpOnly posé par le serveur : le JavaScript ne le voit pas,
   il demande simplement au serveur qui est connecté (/api/auth/me).
   ========================================================== */
'use strict';

const DASHBOARD_URL = '/dashboard.html';
const PLAY_PARAM = 'play'; // /?play : le joueur connecté rejoint directement sa partie

// ================= APPELS AU SERVEUR =================
// Réponse JSON d'une route, ou null (serveur injoignable, réponse illisible)
async function apiJson(url, options = {}) {
    try {
        const response = await fetch(url, options);
        let body = null;
        try {
            body = await response.json();
        } catch {
            // corps vide ou illisible
        }
        return { ok: response.ok, status: response.status, body };
    } catch (err) {
        console.error(err);
        return { ok: false, status: 0, body: null };
    }
}

function apiPost(url, data) {
    return apiJson(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data ?? {}),
    });
}

// Message d'erreur du serveur ({"detail": "..."}), ou texte par défaut
function apiError(result, fallback) {
    if (result.status === 0) return "Impossible de joindre le serveur. Vérifiez qu'il est bien lancé, puis réessayez.";
    const detail = result.body?.detail;
    return typeof detail === 'string' ? detail : fallback;
}

async function fetchCurrentUser() {
    const result = await apiJson('/api/auth/me');
    return result.ok ? result.body : null;
}

async function fetchCurrentGame() {
    const result = await apiJson('/api/game/current');
    return result.ok && result.body ? result.body : { running: false };
}

// Inscription ou connexion ; guest_token : rattache la partie de l'invité au compte
async function authenticate(mode, pseudo, password) {
    const url = mode === 'register' ? '/api/auth/register' : '/api/auth/login';
    return apiPost(url, { pseudo, password, guest_token: guestToken });
}

// Vérifications faites avant d'appeler le serveur (qui refait les siennes)
function credentialsError(mode, pseudo, password, confirm) {
    if (!pseudo || !password) return "Veuillez entrer un pseudo et un mot de passe.";
    if (mode === 'register' && password !== confirm) return "Les deux mots de passe ne correspondent pas.";
    return null;
}

function readField(id) {
    return document.getElementById(id).value;
}

function setFormError(id, text) {
    const el = document.getElementById(id);
    el.textContent = text || '';
    el.classList.toggle('hidden', !text);
}

// ================= ACCUEIL =================
const WELCOME_TABS = ['guest', 'login', 'register'];

function switchWelcomeTab(tab) {
    WELCOME_TABS.forEach(name => {
        const active = name === tab;
        const button = document.getElementById(`welcome-tab-${name}`);
        button.classList.toggle('is-active', active);
        button.setAttribute('aria-selected', String(active));
        document.querySelector(`.welcome-panel[data-panel="${name}"]`).classList.toggle('hidden', !active);
    });
    const firstField = { guest: 'welcome-player-id', login: 'login-pseudo', register: 'register-pseudo' }[tab];
    document.getElementById(firstField).focus();
}

// Au chargement : joueur connecté → tableau de bord (ou sa partie avec /?play) ;
// invité → accueil, avec la reprise de sa partie si l'onglet avait été fermé
async function initWelcome() {
    const wantsToPlay = new URLSearchParams(location.search).has(PLAY_PARAM);
    const [user, game] = await Promise.all([fetchCurrentUser(), fetchCurrentGame()]);
    currentUser = user;
    refreshGameMenu();

    if (user) {
        if (!wantsToPlay) {
            location.replace(DASHBOARD_URL);
            return;
        }
        // Partie en cours du compte (son pseudo peut être celui d'invité, s'il s'est inscrit en jouant)
        const pseudo = game.running && game.yours ? game.pseudo : user.pseudo;
        showAccountJoin(`Connexion à la partie de ${user.pseudo}…`);
        joinGame(pseudo);
        return;
    }
    if (wantsToPlay) {
        // Lien /?play sans être connecté (session expirée) : connexion demandée
        switchWelcomeTab('login');
        setFormError('login-error', "Votre session a expiré : reconnectez-vous pour reprendre votre partie.");
    }
    if (game.running && game.yours && game.pseudo) {
        document.getElementById('welcome-resume-text').textContent =
            `Une partie est en cours sous le pseudo ${game.pseudo}.`;
        document.getElementById('welcome-resume').dataset.pseudo = game.pseudo;
        document.getElementById('welcome-resume').classList.remove('hidden');
    }
}

// Joueur connecté : l'accueil n'affiche que l'état de la connexion à sa partie
function showAccountJoin(text) {
    document.querySelector('.welcome-tabs').classList.add('hidden');
    document.querySelectorAll('.welcome-panel').forEach(panel => panel.classList.add('hidden'));
    document.getElementById('welcome-account-text').textContent = text;
    document.getElementById('welcome-account').classList.remove('hidden');
}

function resumeGuestGame() {
    const pseudo = document.getElementById('welcome-resume').dataset.pseudo;
    if (pseudo) joinGame(pseudo);
}

// Connexion ou inscription depuis l'accueil : direction le tableau de bord
async function submitWelcomeAccount(mode) {
    const prefix = mode === 'register' ? 'register' : 'login';
    const pseudo = readField(`${prefix}-pseudo`).trim().normalize('NFC');
    const password = readField(`${prefix}-password`);
    const confirm = mode === 'register' ? readField('register-password-confirm') : null;
    const error = credentialsError(mode, pseudo, password, confirm);
    setFormError(`${prefix}-error`, error);
    if (error) return;

    const button = document.getElementById(`${prefix}-btn`);
    button.disabled = true;
    const result = await authenticate(mode, pseudo, password);
    button.disabled = false;
    if (!result.ok) {
        setFormError(`${prefix}-error`, apiError(result, "La connexion a échoué."));
        return;
    }
    location.href = DASHBOARD_URL;
}

// ================= MENU DE LA PARTIE =================
function toggleGameMenu(open) {
    const menu = document.getElementById('game-menu');
    const show = open ?? menu.classList.contains('hidden');
    menu.classList.toggle('hidden', !show);
    document.getElementById('menu-btn').setAttribute('aria-expanded', String(show));
}

// Entrées du menu selon que le joueur est connecté ou invité
function refreshGameMenu() {
    const loggedIn = Boolean(currentUser);
    ['menu-dashboard', 'menu-logout'].forEach(id => document.getElementById(id).classList.toggle('hidden', !loggedIn));
    ['menu-register', 'menu-login'].forEach(id => document.getElementById(id).classList.toggle('hidden', loggedIn));
    document.getElementById('menu-player').textContent = loggedIn ? `Connecté : ${currentUser.pseudo}` : 'Invité';
    document.getElementById('gameover-dashboard').classList.toggle('hidden', !loggedIn);
}

// Déconnexion : la partie du compte reste en cours, le joueur la reprendra après s'être reconnecté
async function logout() {
    toggleGameMenu(false);
    await apiPost('/api/auth/logout');
    gameIsOver = true; // pas de fenêtre « Connexion perdue » pendant le départ
    location.href = '/';
}

// ================= COMPTE DEPUIS LA PARTIE (INVITÉ) =================
let accountMode = 'register';

const ACCOUNT_TEXTS = {
    register: { title: "Créer un compte", submit: "Créer mon compte", switchTo: "J'ai déjà un compte" },
    login: { title: "Se connecter", submit: "Se connecter", switchTo: "Créer un compte" },
};

function openAccountModal(mode) {
    toggleGameMenu(false);
    setAccountMode(mode);
    // Pseudo d'invité proposé pour le compte
    document.getElementById('account-pseudo').value = mode === 'register' ? playerId : '';
    document.getElementById('account-password').value = '';
    document.getElementById('account-password-confirm').value = '';
    document.getElementById('account-hint').textContent = gameIsOver
        ? "Cette partie sera enregistrée dans votre compte, avec les succès qu'elle débloque."
        : "Cette partie sera enregistrée dans votre compte.";
    openModal('modal-account');
    document.getElementById(mode === 'register' ? 'account-password' : 'account-pseudo').focus();
}

function setAccountMode(mode) {
    accountMode = mode;
    const texts = ACCOUNT_TEXTS[mode];
    document.getElementById('account-title').textContent = texts.title;
    document.getElementById('account-submit').textContent = texts.submit;
    document.getElementById('account-switch').textContent = texts.switchTo;
    document.getElementById('account-confirm-row').classList.toggle('hidden', mode !== 'register');
    document.getElementById('account-password').autocomplete = mode === 'register' ? 'new-password' : 'current-password';
    setFormError('account-error', null);
}

function switchAccountMode() {
    setAccountMode(accountMode === 'register' ? 'login' : 'register');
}

function closeAccountModal() {
    closeModal('modal-account');
}

async function submitGameAccount() {
    const pseudo = readField('account-pseudo').trim().normalize('NFC');
    const password = readField('account-password');
    const error = credentialsError(accountMode, pseudo, password, readField('account-password-confirm'));
    setFormError('account-error', error);
    if (error) return;

    const button = document.getElementById('account-submit');
    button.disabled = true;
    const result = await authenticate(accountMode, pseudo, password);
    button.disabled = false;
    if (!result.ok) {
        setFormError('account-error', apiError(result, "La connexion a échoué."));
        return;
    }

    const body = result.body;
    currentUser = { id: body.id, pseudo: body.pseudo, is_admin: body.is_admin };
    guestToken = null; // usage unique : la partie est rattachée (ou ne peut plus l'être)
    closeAccountModal();
    refreshGameMenu();
    document.getElementById('gameover-register').classList.add('hidden');

    const welcome = accountMode === 'register' ? `Compte ${body.pseudo} créé.` : `Connecté en tant que ${body.pseudo}.`;
    if (!body.game_claimed) {
        appendSystemMessage(`${welcome} Cette partie n'a pas pu être rattachée à votre compte.`);
    } else if (gameIsOver) {
        appendSystemMessage(`${welcome} La partie est enregistrée dans votre compte.`);
        showUnlockedAchievements(body.achievements || []);
    } else {
        appendSystemMessage(`${welcome} Cette partie sera enregistrée dans votre compte.`);
    }
}

// ================= FIN DE PARTIE =================
// Succès débloqués : liste sous le résultat de la partie
function showUnlockedAchievements(achievements) {
    const box = document.getElementById('gameover-achievements');
    box.classList.toggle('hidden', !achievements.length);
    document.getElementById('gameover-achievements-list').innerHTML = achievements.map(a => `
        <li class="achievement-unlock">
            <span class="achievement-unlock-title">🏆 ${escapeHtml(a.title)}</span>
            ${a.message ? `<span class="achievement-unlock-message block">${escapeHtml(a.message)}</span>` : ''}
        </li>
    `).join('');
}

// Invité : proposition de créer un compte pour garder la partie (pas pour une partie interrompue)
function offerAccountAfterGame(canClaim) {
    document.getElementById('gameover-register').classList.toggle('hidden', Boolean(currentUser) || !canClaim || !guestToken);
}

// Nouvelle partie : le joueur connecté la lance directement, l'invité repasse par l'accueil
function startNewGame() {
    gameIsOver = true;
    location.href = currentUser ? `/?${PLAY_PARAM}` : '/';
}
