/* ==========================================================
   game.js — état de la partie : en-tête, annonce, table ronde, rôle du joueur
   ========================================================== */
'use strict';

// Annonce par défaut quand le serveur change de phase sans en fournir
const DEFAULT_PHASE_ANNOUNCEMENTS = {
    nuit: "La nuit tombe... Les pouvoirs sont en cours d'invocation.",
    vote: "Phase de vote : réflexion et choix des joueurs en cours..."
};

function updateGameState(newState) {
    gameState = { ...gameState, ...newState };
    const phase = PHASES[String(gameState.phase).toLowerCase()] ? String(gameState.phase).toLowerCase() : 'nuit';

    // Une action demandée pour une autre phase n'a plus lieu d'être
    // (une action déjà envoyée reste affichée en attente de sa réponse)
    if (pendingAction && pendingAction.stage === "choosing" && newState.phase && phase !== pendingAction.kind) {
        pendingAction = null;
        actionSelection = [];
    }

    renderHeader(phase);

    if (newState.announcement) {
        setAnnouncement(newState.announcement);
    } else if (newState.phase && DEFAULT_PHASE_ANNOUNCEMENTS[phase]) {
        setAnnouncement(DEFAULT_PHASE_ANNOUNCEMENTS[phase]);
    }

    // Lueur d'ambiance de la zone centrale selon la phase
    document.getElementById('center-stage').dataset.phase = phase;

    renderRoundTable();
    renderPlayersList();
    renderActionPanel();
}

// ================= EN-TÊTE (tour, phase, vivants) =================
function renderHeader(phase) {
    document.getElementById('game-day').textContent = gameState.day;
    document.getElementById('alive-count').textContent = gameState.aliveCount;

    const phaseLabel = document.getElementById('game-phase');
    const phaseIcon = document.getElementById('phase-icon-container');
    phaseLabel.textContent = PHASES[phase].label;
    phaseLabel.dataset.phase = phase;
    phaseIcon.dataset.phase = phase;
    phaseIcon.innerHTML = icon(PHASES[phase].icon, 'size-5');
}

// ================= BANDEAU D'ANNONCE =================
function setAnnouncement(text) {
    const el = document.getElementById('game-announcement');
    const changed = el.textContent.trim() !== String(text).trim();

    // Le title permet de lire une annonce tronquée au survol
    el.textContent = text;
    el.title = text;

    // Effet doré si l'annonce a réellement changé (on relance l'animation si elle est en cours)
    if (changed) {
        el.classList.remove('announce-flash');
        void el.offsetWidth; // force le reflow pour redémarrer l'animation
        el.classList.add('announce-flash');
    }
}

// ================= TABLE RONDE =================
// Place les joueurs autour de la table (le Grimoire central est statique dans le HTML).
function renderRoundTable() {
    const seats = document.getElementById('round-table-seats');
    const players = gameState.players || [];

    if (!players.length) {
        seats.innerHTML = `<p class="absolute inset-x-0 bottom-[3%] text-center text-sm italic opacity-60">En attente des joueurs...</p>`;
        return;
    }

    seats.innerHTML = players.map((p, index) => {
        // Positions en % du carré : la table reste correcte quelle que soit sa taille.
        // Rayon 39 % = bord extérieur de la table (inset-[11%]) : le centre de la bulle est posé sur le cercle.
        const angle = (index / players.length) * 2 * Math.PI - Math.PI / 2;
        const left = 50 + 39 * Math.cos(angle);
        const top = 50 + 39 * Math.sin(angle);
        const isMe = p.id === playerId;
        const isAlive = p.alive !== false;
        const initial = escapeHtml((p.name || '?').trim().charAt(0).toUpperCase());
        const label = escapeHtml(p.name) + (isMe ? ' (vous)' : '') + (isAlive ? '' : ' (mort)');

        // Le siège est centré sur la bulle ; le nom est accroché en dessous sans décaler la bulle.
        return `
            <div class="seat ${isMe ? 'is-me' : ''} ${isAlive ? '' : 'is-dead'} pointer-events-auto absolute -translate-x-1/2 -translate-y-1/2"
                 style="left: ${left}%; top: ${top}%;" title="${label}">
                <div class="seat-avatar flex size-12 sm:size-14 items-center justify-center rounded-full font-display text-lg">${initial}</div>
                <span class="seat-name absolute left-1/2 top-full mt-1 w-32 sm:w-36 -translate-x-1/2 line-clamp-2 text-center leading-tight px-1 text-xs sm:text-sm font-medium">${label}</span>
            </div>
        `;
    }).join('');
}

// ================= RÔLE DU JOUEUR =================
function assignRole(name, description) {
    gameState.roleInfo = { name, description };
    gameState.allies = null; // inconnus tant que la première nuit ne les a pas révélés
    renderPlayersList(); // retire le rôle du joueur des listes de soupçons (ou les verrouille si rôle maléfique)

    document.getElementById('player-role-name').textContent = name;
    document.getElementById('player-role-desc').textContent = description;
    showRoleRevealModal(name, description);
}
