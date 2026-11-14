/* ==========================================================
   core.js — configuration, état partagé, icônes, utilitaires, données des rôles
   Chargé en premier : les autres scripts s'appuient sur ces déclarations.
   Les scripts sont "classiques" (pas des modules ES) : leurs déclarations
   de haut niveau sont partagées, ce qui permet aussi de piloter le jeu depuis
   la console (snippets de simulation).
   ========================================================== */
'use strict';

// ================= CONFIGURATION =================
const SERVER_WS_URL = "ws://127.0.0.1:8000/ws";

// ================= ÉTAT GLOBAL =================
let ws = null;
let playerId = "";
let gameState = {
    day: 1,
    phase: "discussion", // "discussion" | "nuit" | "vote" (valeurs envoyées par le serveur)
    aliveCount: 0,
    players: [], // { id, name, alive, has_vote }
    messages: { public: [] }, // channel_id -> [{ sender, content, time } | { system: true, content }]
    currentChannel: "public",
    roleInfo: { name: "En attente...", description: "La partie va démarrer." },
    allies: null, // [{ id, role }] une fois révélés (camp du mal), null sinon
    vote_history: [],
    night_info_history: []
};

// ================= ICÔNES (Lucide) =================
const ICON_PATHS = {
    sun: '<circle cx="12" cy="12" r="4"></circle><path d="M12 2v2"></path><path d="M12 20v2"></path><path d="m4.93 4.93 1.41 1.41"></path><path d="m17.66 17.66 1.41 1.41"></path><path d="M2 12h2"></path><path d="M20 12h2"></path><path d="m6.34 17.66-1.41 1.41"></path><path d="m19.07 4.93-1.41 1.41"></path>',
    moon: '<path d="M20.985 12.486a9 9 0 1 1-9.473-9.472c.405-.022.617.46.402.803a6 6 0 0 0 8.268 8.268c.344-.215.825-.004.803.401"></path>',
    scale: '<path d="M12 3v18"></path><path d="m19 8 3 8a5 5 0 0 1-6 0zV7"></path><path d="M3 7h1a17 17 0 0 0 8-2 17 17 0 0 0 8 2h1"></path><path d="m5 8 3 8a5 5 0 0 1-6 0zV7"></path><path d="M7 21h10"></path>',
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M22 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path>',
    check: '<path d="M20 6 9 17l-5-5"></path>',
    close: '<path d="M18 6 6 18"></path><path d="m6 6 12 12"></path>'
};

// SVG d'une icône ; `className` fixe la taille (et d'éventuelles classes en plus)
function icon(name, className = 'size-4') {
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="${className}" aria-hidden="true">${ICON_PATHS[name]}</svg>`;
}

// ================= PHASES =================
// Libellé et icône de chaque phase (en-tête) ; les couleurs sont dans le CSS ([data-phase]).
const PHASES = {
    discussion: { label: 'Jour', icon: 'sun' },
    nuit:       { label: 'Nuit', icon: 'moon' },
    vote:       { label: 'Vote', icon: 'scale' }
};

// ================= RÔLES =================
// Textes de la nuit selon le rôle (clé = name_EN du catalogue backend)
const NIGHT_ROLE_TEXTS = {
    imp:       { label: "Diablotin",    prompt: "Qui sera votre victime cette nuit ?" },
    poisoner:  { label: "Empoisonneur", prompt: "Qui empoisonnerez-vous jusqu'à la fin de la prochaine journée ?" },
    monk:      { label: "Moine",        prompt: "Qui protégerez-vous des griffes du Diablotin cette nuit ?" },
    psychic:   { label: "Voyante",      prompt: "Quels sont les deux joueurs que vous souhaitez sonder ?" },
    butler:    { label: "Majordome",    prompt: "Qui choisissez-vous comme Maître ? Vous ne pourrez voter que s'il vote aussi." }
};

// Accepte indifféremment "imp", "Diablotin", "diablotin"…
function resolveRoleKey(role) {
    if (!role) return null;
    const wanted = normalizeText(role);
    return Object.keys(NIGHT_ROLE_TEXTS).find(
        key => key === wanted || normalizeText(NIGHT_ROLE_TEXTS[key].label) === wanted
    ) || null;
}

// Rôle maléfique du joueur humain (Diablotin ou Empoisonneur)
function isEvilRole() {
    return ["imp", "poisoner"].includes(resolveRoleKey(gameState.roleInfo?.name));
}

// ================= UTILITAIRES =================
function escapeHtml(text) {
    if (text == null) return '';
    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

// Minuscules, sans accents ni espaces superflus (comparaisons de noms de rôles)
function normalizeText(s) {
    return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
}

// Heure locale (HH:MM)
function currentTime() {
    return new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
}

function getPlayerName(id) {
    const player = (gameState.players || []).find(p => p.id === id);
    return player ? player.name : id;
}

function isWsOpen() {
    return !!ws && ws.readyState === WebSocket.OPEN;
}

// Envoie une action au serveur ; renvoie false si la connexion est fermée
function sendAction(action, payload = {}) {
    if (!isWsOpen()) return false;
    ws.send(JSON.stringify({ action, payload }));
    return true;
}

// Ajoute une entrée dans l'historique de l'onglet "Nuits" (type : "role_info" | "result")
function addNightHistory(turn, type, info) {
    gameState.night_info_history.push({ turn: turn ?? gameState.day, type, info });
    renderNightInfoHistory();
}

// Ajoute les bulletins d'un vote dans l'historique de l'onglet "Votes"
function addVoteHistory(turn, executed, votes) {
    (votes || []).forEach(v => {
        gameState.vote_history.push({ turn, voter: v.voter, target: v.target, executed });
    });
    renderVoteHistory();
}
