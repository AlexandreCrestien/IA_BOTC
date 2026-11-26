/* ==========================================================
   modals.js — modales : rôle, entretien, exécution, nuit, fin de partie,
   connexion perdue, Codex
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
function showAgentWhisperModal(agentId) {
    currentWhisperAgent = agentId;
    document.getElementById('agent-whisper-text').textContent =
        `${getPlayerName(agentId)} souhaite s'entretenir discrètement avec vous dans l'ombre.`;
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

    addNightHistory({ turn: turnNumber, type: "result", dead_player: deadPlayerId || null });
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
// winner : camp vainqueur envoyé par le serveur
const WINNER_TITLES = { good: "Victoire des Villageois", evil: "Victoire des Démons" };

// achievements : succès débloqués par la partie (joueur connecté)
function triggerGameOver(winner, details, achievements = []) {
    gameIsOver = true;
    document.getElementById('gameover-title').textContent = WINNER_TITLES[winner] || "Fin de la partie";
    document.getElementById('gameover-desc').textContent = details;

    // Victoire ou défaite du joueur, si son rôle est connu
    const outcomeEl = document.getElementById('gameover-outcome');
    const card = document.getElementById('gameover-card');
    if (resolveRoleKey(gameState.roleInfo?.name)) {
        const playerWon = (winner === "evil") === isEvilRole();
        outcomeEl.textContent = playerWon ? "Votre camp l'emporte !" : "Votre camp a perdu…";
        outcomeEl.dataset.outcome = playerWon ? 'win' : 'loss';
        outcomeEl.classList.remove('hidden');
        card.dataset.tone = playerWon ? 'gold' : 'blood';
    }

    showUnlockedAchievements(achievements);
    offerAccountAfterGame(true); // invité : s'inscrire pour garder la partie
    gameFinished = true;
    refreshRatingOffer(); // joueur connecté : évaluer les agents
    openModal('modal-gameover');
}

// La partie a planté côté serveur : même fenêtre que la fin de partie, avec un autre message
function showGameInterrupted(text) {
    gameIsOver = true;
    document.getElementById('gameover-title').textContent = "Partie interrompue";
    document.getElementById('gameover-desc').textContent = text || "Une erreur a interrompu la partie.";
    document.getElementById('gameover-outcome').classList.add('hidden');
    document.getElementById('gameover-card').dataset.tone = 'blood';
    showUnlockedAchievements([]);
    offerAccountAfterGame(false); // une partie interrompue n'est jamais enregistrée
    gameFinished = false;         // ni évaluée
    refreshRatingOffer();
    openModal('modal-gameover');
}

// ================= ÉVALUATION DES AGENTS IA (fin de partie) =================
// Joueur connecté dont la partie, terminée par une victoire ou une défaite, est rattachée au compte ;
// une seule fois par partie. Règles côté serveur : backend/server/ratings.py.
const RATING_COMMENT_MAX = 300;
let gameFinished = false; // partie terminée normalement (pas interrompue)
let agentsRated = false;

function canRateAgents() {
    return gameFinished && !agentsRated && canReport();
}

function refreshRatingOffer() {
    document.getElementById('gameover-rate').classList.toggle('hidden', !canRateAgents());
}

function ratingAgents() {
    return (gameState.players || []).filter(p => p.id !== playerId);
}

function openRatingModal() {
    if (!canRateAgents()) return;
    document.getElementById('rating-agents').innerHTML = ratingAgents().map(agent => {
        const id = escapeHtml(agent.id);
        const name = escapeHtml(agent.name);
        // Étoiles : boutons radio de 5 à 1 affichés de droite à gauche (le survol colore les précédentes)
        const stars = [5, 4, 3, 2, 1].map(score => `
            <input type="radio" id="rating-${id}-${score}" name="rating-${id}" value="${score}" class="sr-only">
            <label for="rating-${id}-${score}" title="${score} sur 5">★<span class="sr-only">${score} sur 5</span></label>
        `).join('');
        return `
            <fieldset class="rating-agent" data-agent="${id}">
                <legend class="font-display text-lg text-gold">${name}</legend>
                <div class="rating-stars" role="radiogroup" aria-label="Note de ${name}">${stars}</div>
                <textarea rows="2" maxlength="${RATING_COMMENT_MAX}" class="report-comment w-full mt-2"
                    aria-label="Commentaire sur ${name} (facultatif)" placeholder="Commentaire (facultatif)"></textarea>
            </fieldset>
        `;
    }).join('');
    setFormError('rating-error', null);
    document.getElementById('rating-submit').disabled = false;
    document.getElementById('rating-form').classList.remove('hidden');
    document.getElementById('rating-thanks').classList.add('hidden');
    closeModal('modal-gameover');
    openModal('modal-rating');
}

// Retour à l'écran de fin, sans rien envoyer
function closeRatingModal() {
    closeModal('modal-rating');
    if (gameIsOver) {
        refreshRatingOffer();
        openModal('modal-gameover');
    }
}

function submitRatings() {
    const ratings = [...document.querySelectorAll('#rating-agents .rating-agent')].flatMap(box => {
        const checked = box.querySelector('input:checked');
        const comment = box.querySelector('textarea').value.trim();
        return checked ? [{ agent_id: box.dataset.agent, score: Number(checked.value), comment: comment || null }] : [];
    });
    if (!ratings.length) return setFormError('rating-error', "Donnez une note à au moins un personnage.");
    if (!sendAction("rate_agents", { ratings })) {
        return setFormError('rating-error', "Connexion perdue : l'évaluation n'a pas été envoyée.");
    }
    setFormError('rating-error', null);
    document.getElementById('rating-submit').disabled = true; // en attente de la réponse du serveur
}

// Réponse du serveur : « Merci » et proposition d'une nouvelle partie, ou motif du refus
function handleRatingResult(error) {
    if (error) {
        setFormError('rating-error', error);
        document.getElementById('rating-submit').disabled = false;
        return;
    }
    agentsRated = true;
    document.getElementById('rating-form').classList.add('hidden');
    document.getElementById('rating-thanks').classList.remove('hidden');
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

// Retour à l'accueil (page rechargée : le front repart d'un état vierge).
// Joueur connecté : l'accueil le renvoie vers son tableau de bord.
function leaveGame() {
    gameIsOver = true; // pas de fenêtre « Connexion perdue » pendant le rechargement
    location.href = '/';
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

// ================= CODEX =================
function openCodexModal() {
    openModal('modal-codex');
}

function closeCodexModal() {
    closeModal('modal-codex');
}

const CODEX_TABS = ['roles', 'rules', 'data'];

function switchCodexTab(tabName) {
    CODEX_TABS.forEach(tab => {
        document.getElementById(`codex-tab-${tab}`).classList.toggle('hidden', tab !== tabName);
        document.getElementById(`codex-tab-btn-${tab}`).classList.toggle('is-active', tab === tabName);
    });
}
