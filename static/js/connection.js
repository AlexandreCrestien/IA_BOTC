/* ==========================================================
   connection.js — connexion WebSocket, écran d'accueil, messages du serveur
   ========================================================== */
'use strict';

// Code de fermeture envoyé par le serveur quand il refuse la connexion (motif dans event.reason)
const CLOSE_REFUSED = 4001;
// Pseudo autorisé : lettres (accents compris), chiffres, - _ ' ’ ; 20 caractères au plus.
// Même règle côté serveur (backend/accounts/pseudo.py, PSEUDO_PATTERN).
const PSEUDO_PATTERN = /^[\p{L}\p{N}_'’-]{1,20}$/u;

// ================= CONNEXION =================
// pseudo : imposé (joueur connecté, reprise d'une partie) ; sinon, celui saisi sur l'accueil (invité)
function joinGame(pseudo = null) {
    // Une connexion est déjà en cours ou ouverte : on ignore le double clic
    if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) return;

    const input = document.getElementById('welcome-player-id');
    // NFC : un « é » saisi en deux caractères (e + accent) devient un seul, comme le serveur l'attend
    playerId = (pseudo ?? input.value).trim().normalize('NFC');
    if (!playerId) {
        showWelcomeError("Veuillez entrer un pseudo.");
        input.focus();
        return;
    }
    if (!PSEUDO_PATTERN.test(playerId)) {
        showWelcomeError("Votre pseudo ne peut contenir que des lettres, des chiffres, des tirets, « _ » et des apostrophes (20 caractères au plus).");
        input.focus();
        return;
    }

    showWelcomeError(null);
    setJoinButtonLoading(true);

    ws = new WebSocket(`${SERVER_WS_URL}/${encodeURIComponent(playerId)}`);
    let opened = false;
    let entered = false; // écran de jeu affiché

    ws.onopen = () => {
        opened = true;
    };

    ws.onmessage = (event) => {
        // On n'entre dans le jeu qu'au premier message du serveur : une connexion refusée
        // (acceptée puis aussitôt refermée) ne fait donc pas clignoter l'écran de jeu.
        if (!entered) {
            entered = true;
            enterGameScreen();
        }
        let data;
        try {
            data = JSON.parse(event.data);
        } catch (e) {
            console.error("Message WebSocket illisible :", e);
            return;
        }
        handleServerMessage(data);
    };

    ws.onclose = (event) => {
        setJoinButtonLoading(false);
        if (event.code === CLOSE_REFUSED) {
            // Refus du serveur (pseudo invalide, partie d'un autre joueur) : motif affiché sur l'accueil
            showWelcomeError(event.reason || "Le serveur a refusé la connexion.");
            return;
        }
        if (!entered) {
            // Échec dès la connexion : le joueur est encore sur l'écran d'accueil
            showWelcomeError(opened
                ? "Le serveur a fermé la connexion. Réessayez."
                : "Impossible de joindre le serveur. Vérifiez qu'il est bien lancé, puis réessayez.");
            return;
        }
        updateConnectionBadge(false);
        showDisconnectedModal();
        appendSystemMessage("Connexion fermée par le serveur.");
    };

    ws.onerror = (error) => {
        console.error("Erreur WebSocket :", error);
        if (opened) appendSystemMessage("Erreur de connexion réseau.");
    };
}

function enterGameScreen() {
    setJoinButtonLoading(false);
    document.getElementById('screen-welcome').classList.add('hidden');
    document.getElementById('screen-game').classList.remove('hidden');
    updateConnectionBadge(true);
    appendSystemMessage("Connexion établie avec le serveur.", 'public');
}

// Message d'erreur de l'écran d'accueil (null pour l'effacer) : sous le formulaire invité,
// ou dans l'encadré du joueur connecté qui rejoint sa partie
function showWelcomeError(text) {
    const accountBox = document.getElementById('welcome-account');
    const el = document.getElementById(accountBox.classList.contains('hidden') ? 'welcome-error' : 'welcome-account-error');
    el.textContent = text || '';
    el.classList.toggle('hidden', !text);
}

function setJoinButtonLoading(loading) {
    const btn = document.getElementById('welcome-join-btn');
    btn.disabled = loading;
    btn.textContent = loading ? "Connexion…" : "Rejoindre la partie";
}

function updateConnectionBadge(isConnected) {
    const badge = document.getElementById('connection-status');
    badge.dataset.state = isConnected ? 'online' : 'offline';
    badge.textContent = isConnected ? "Connecté" : "Déconnecté";
    // Active/désactive le bouton de validation de l'encadré d'action
    refreshActionSelection();
}

// ================= MESSAGES DU SERVEUR =================
function handleServerMessage(data) {
    switch (data.type) {
        case "connected":
            break; // accusé de connexion : l'écran de jeu est affiché par ws.onmessage
        case "guest_session":
            guestToken = data.guest_token; // jamais affiché : envoyé seulement avec une inscription ou une connexion
            break;
        case "chat":
            receiveChatMessage(data.channel_id || "public", data.sender, data.content, data.message_id, data.reported);
            break;
        case "rating_result":
            handleRatingResult(data.error);
            break;
        case "report_result":
            handleReportResult(data.message_id, data.error);
            break;
        case "game_state":
            updateGameState(data.state);
            break;
        case "role_assigned":
            assignRole(data.role_name, data.description);
            // Reconnexion d'un joueur du camp du mal : ses alliés déjà révélés
            if (Array.isArray(data.allies)) revealAllies(data.allies);
            break;
        case "history":
            restoreHistories(data.nights, data.votes); // reconnexion : onglets Nuits et Votes
            break;
        case "input_request":
            showTurnPrompt(data); // message public ou privé attendu (facultatif)
            break;
        case "announcement":
            setAnnouncement(data.text);
            break;
        case "action_request":
            hideTurnPrompt(); // une nouvelle étape commence : plus de saisie attendue
            handleActionRequest(data); // Remplit l'encadré d'action de la sidebar droite
            break;
        case "agent_whisper_request":
            showAgentWhisperModal(data.agent_id);
            break;
        case "private_channel_opened":
            // members inclut le joueur humain : on ne garde que ses interlocuteurs pour le titre de l'onglet
            // focus false : salon rouvert après une reconnexion, sans s'y placer
            handlePrivateChannelOpened(data.channel_id, data.text, (data.members || []).filter(m => m !== playerId),
                data.focus !== false);
            break;
        case "vote_result":
            addVoteHistory(data.turn, data.executed, data.votes);
            showVoteResultInPanel(data.executed, data.votes || []);
            if (data.executed && data.executed === playerId) showExecutionModal(data.turn);
            break;
        case "night_result":
            showNightResultModal(data.turn, data.dead_player);
            break;
        case "night_info":
            // allies (facultatif) : révélation des alliés du camp du mal, la première nuit : [{ id, role }]
            if (Array.isArray(data.allies)) revealAllies(data.allies);
            addNightHistory({ turn: data.turn, type: "role_info", info: data.info });
            if (pendingAction?.kind === "nuit" && pendingAction.stage === "waiting") {
                // Réponse à l'action de nuit du joueur : affichée dans l'encadré plutôt qu'en modale
                showNightResultInPanel(data.info);
            } else {
                showNightInfoModal(data.turn, data.info);
            }
            break;
        case "night_action_ack":
            // Simple confirmation de l'action de nuit (rôles sans information en retour)
            showNightResultInPanel(data.text || "Le Maître du Jeu a bien reçu votre choix.");
            break;
        case "game_over":
            triggerGameOver(data.winner, data.details, data.achievements || []);
            break;
        case "game_abandoned":
            leaveGame(); // retour à l'accueil, où le joueur peut lancer une nouvelle partie
            break;
        case "game_interrupted":
            showGameInterrupted(data.text);
            break;
        case "error":
            appendSystemMessage(data.data || "Erreur du serveur.");
            // L'action a été refusée : le joueur peut corriger son choix
            if (pendingAction?.stage === "waiting") {
                pendingAction.stage = "choosing";
                renderActionPanel();
            }
            break;
        default:
            console.log("Message non géré :", data);
    }
}
