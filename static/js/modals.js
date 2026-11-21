/* ==========================================================
   modals.js — modales : rôle, entretien, exécution, nuit, fin de partie,
   connexion perdue, Grimoire
   ========================================================== */
'use strict';

let currentWhisperAgent = null; // agent qui demande un entretien
let gameIsOver = false;

function openModal(id) {
    document.getElementById(id).classList.remove('hidden');
}

function closeModal(id) {
    document.getElementById(id).classList.add('hidden');
}

// ================= RÔLE SECRET =================
function showRoleRevealModal(name, description) {
    document.getElementById('modal-role-title').textContent = name;
    document.getElementById('modal-role-description').textContent = description;
    openModal('modal-role-reveal');
}

function closeRoleRevealModal() {
    closeModal('modal-role-reveal');
}

// ================= DEMANDE D'ENTRETIEN D'UN AGENT =================
// Le joueur n'a choisi aucun salon privé à temps : un agent lui propose un entretien.
// Accepter ouvre le salon (l'agent parle en premier) ; refuser passe au vote.
function showAgentWhisperModal(agentId, agentName, message) {
    currentWhisperAgent = agentId;
    const name = agentName || getPlayerName(agentId);
    document.getElementById('agent-whisper-text').textContent =
        message || `${name} souhaite s'entretenir discrètement avec vous dans l'ombre.`;
    openModal('modal-agent-whisper');
}

function answerAgentWhisper(accepted) {
    const agentId = currentWhisperAgent;
    if (!agentId) return;
    if (!sendAction("respond_whisper_invitation", { target_agent_id: agentId, accepted })) {
        // La modale reste ouverte : la proposition sera renvoyée à la reconnexion
        appendSystemMessage("Connexion perdue : votre réponse n'a pas été envoyée.");
        return;
    }
    closeModal('modal-agent-whisper');
    currentWhisperAgent = null;
    // Accepté : le salon s'ouvrira à la réception de "private_channel_opened"
    appendSystemMessage(accepted
        ? `Vous avez accepté l'entretien avec ${getPlayerName(agentId)}. Ouverture du salon…`
        : `Vous avez refusé l'entretien avec ${getPlayerName(agentId)}.`);
}

// ================= EXÉCUTION DU JOUEUR =================
// Les résultats détaillés du vote sont dans l'encadré d'action ; cette modale
// ne s'ouvre que si le joueur lui-même est exécuté.
function showExecutionModal(turnNumber) {
    document.getElementById('vote-result-header').textContent = `Jour ${turnNumber} — ${getPlayerName(playerId)} exécuté·e`;
    openModal('modal-vote-result');
}

function closeVoteResultModal() {
    closeModal('modal-vote-result');
}

// ================= RÉVEIL DU VILLAGE =================
function showNightResultModal(turnNumber, deadPlayerId) {
    const messageEl = document.getElementById('night-result-message');
    const deathNoticeEl = document.getElementById('night-death-notice');
    const isMe = deadPlayerId && deadPlayerId === playerId;

    if (!deadPlayerId) {
        messageEl.innerHTML = `Les esprits ont protégé le village…<br><span class="modal-highlight-good">Personne n'est mort</span> cette nuit !`;
    } else if (isMe) {
        messageEl.textContent = "L'obscurité a frappé cette nuit…";
    } else {
        messageEl.innerHTML = `Les ténèbres ont frappé…<br><span class="modal-highlight-blood">${escapeHtml(getPlayerName(deadPlayerId))}</span> est mort·e cette nuit.`;
    }
    deathNoticeEl.classList.toggle('hidden', !isMe);

    addNightHistory(turnNumber, "result",
        deadPlayerId ? `${getPlayerName(deadPlayerId)} est mort·e cette nuit.` : "Personne n'est mort cette nuit.");
    openModal('modal-night-result');
}

function closeNightResultModal() {
    closeModal('modal-night-result');
}

// ================= INFORMATION NOCTURNE =================
// (l'enregistrement dans l'historique est fait par handleServerMessage)
function showNightInfoModal(turnNumber, infoText) {
    document.getElementById('night-info-content').innerHTML = `
        <span class="modal-kicker block mb-2">Tour ${escapeHtml(turnNumber ?? '')}</span>
        <p class="font-serif text-base italic leading-relaxed">${escapeHtml(infoText)}</p>
    `;
    openModal('modal-night-info');
}

function closeNightInfoModal() {
    closeModal('modal-night-info');
}

// ================= FIN DE PARTIE =================
function triggerGameOver(winner, details) {
    gameIsOver = true;
    document.getElementById('gameover-title').textContent = `Victoire des ${winner}`;
    document.getElementById('gameover-desc').textContent = details;

    // Victoire ou défaite du joueur, si son rôle est connu
    const outcomeEl = document.getElementById('gameover-outcome');
    const card = document.getElementById('gameover-card');
    if (resolveRoleKey(gameState.roleInfo?.name)) {
        const evilWon = /d[ée]mon|mal|sbire/i.test(String(winner));
        const playerWon = evilWon === isEvilRole();
        outcomeEl.textContent = playerWon ? "Votre camp l'emporte !" : "Votre camp a perdu…";
        outcomeEl.dataset.outcome = playerWon ? 'win' : 'loss';
        outcomeEl.classList.remove('hidden');
        card.dataset.tone = playerWon ? 'gold' : 'blood';
    }

    openModal('modal-gameover');
}

// La partie a planté côté serveur : même fenêtre que la fin de partie, avec un autre message
function showGameInterrupted(text) {
    gameIsOver = true;
    document.getElementById('gameover-title').textContent = "Partie interrompue";
    document.getElementById('gameover-desc').textContent = text || "Une erreur a interrompu la partie.";
    document.getElementById('gameover-outcome').classList.add('hidden');
    document.getElementById('gameover-card').dataset.tone = 'blood';
    openModal('modal-gameover');
}

// ================= ABANDON =================
// Délai de secours : si le serveur ne confirme pas l'abandon, on revient quand même à l'accueil
const ABANDON_FALLBACK_MS = 3000;

function confirmAbandon() {
    closeModal('modal-abandon');
    // Partie déjà finie ou connexion perdue : rien à prévenir côté serveur
    if (gameIsOver || !sendAction("abandon_game")) {
        leaveGame();
        return;
    }
    setTimeout(leaveGame, ABANDON_FALLBACK_MS);
}

// Retour à l'accueil (page rechargée : le front repart d'un état vierge)
function leaveGame() {
    gameIsOver = true; // pas de fenêtre « Connexion perdue » pendant le rechargement
    location.reload();
}

// ================= CONNEXION PERDUE =================
function showDisconnectedModal() {
    const gameVisible = !document.getElementById('screen-game').classList.contains('hidden');
    if (!gameVisible || gameIsOver) return; // pas pendant l'accueil ni après la fin de partie
    openModal('modal-disconnected');
}

function closeDisconnectedModal() {
    closeModal('modal-disconnected');
}

// ================= GRIMOIRE =================
function openGrimoireModal() {
    openModal('modal-grimoire');
}

function closeGrimoireModal() {
    closeModal('modal-grimoire');
}

function switchGrimoireTab(tabName) {
    const showRoles = tabName === 'roles';
    document.getElementById('grimoire-tab-roles').classList.toggle('hidden', !showRoles);
    document.getElementById('grimoire-tab-rules').classList.toggle('hidden', showRoles);
    document.getElementById('grimoire-tab-btn-roles').classList.toggle('is-active', showRoles);
    document.getElementById('grimoire-tab-btn-rules').classList.toggle('is-active', !showRoles);
}
