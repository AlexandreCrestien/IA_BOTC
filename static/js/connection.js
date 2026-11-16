/* ==========================================================
   connection.js — connexion WebSocket, écran d'accueil, messages du serveur
   ========================================================== */
'use strict';

// ================= CONNEXION =================
function joinGame() {
    // Une connexion est déjà en cours ou ouverte : on ignore le double clic
    if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) return;

    const input = document.getElementById('welcome-player-id');
    playerId = input.value.trim();
    if (!playerId) {
        showWelcomeError("Veuillez entrer un pseudo.");
        input.focus();
        return;
    }

    showWelcomeError(null);
    setJoinButtonLoading(true);

    ws = new WebSocket(`${SERVER_WS_URL}/${playerId}`);
    let opened = false;

    ws.onopen = () => {
        opened = true;
        document.getElementById('screen-welcome').classList.add('hidden');
        document.getElementById('screen-game').classList.remove('hidden');
        updateConnectionBadge(true);
        appendSystemMessage("Connexion établie avec le serveur.", 'public');
    };

    ws.onmessage = (event) => {
        let data;
        try {
            data = JSON.parse(event.data);
        } catch (e) {
            console.error("Message WebSocket illisible :", e);
            return;
        }
        handleServerMessage(data);
    };

    ws.onclose = () => {
        setJoinButtonLoading(false);
        if (!opened) {
            // Échec dès la connexion : le joueur est encore sur l'écran d'accueil
            showWelcomeError("Impossible de joindre le serveur. Vérifiez qu'il est bien lancé, puis réessayez.");
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

// Message d'erreur sous le bouton de l'écran d'accueil (null pour l'effacer)
function showWelcomeError(text) {
    const el = document.getElementById('welcome-error');
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
        case "chat":
            receiveChatMessage(data.channel_id || "public", data.sender, data.content);
            break;
        case "game_state":
            updateGameState(data.state);
            break;
        case "phase_update":
            // Changement de phase seul (ex. vote déclenché par un joueur)
            updateGameState({ phase: data.phase, ...(data.announcement ? { announcement: data.announcement } : {}) });
            break;
        case "role_assigned":
            assignRole(data.role_name, data.description);
            break;
        case "announcement":
            setAnnouncement(data.text);
            break;
        case "action_request":
            handleActionRequest(data); // Remplit l'encadré d'action de la sidebar droite
            break;
        case "agent_whisper_request":
            showAgentWhisperModal(data.agent_id, data.agent_name, data.message);
            break;
        case "private_channel_opened":
            // members inclut le joueur humain : on ne garde que ses interlocuteurs pour le titre de l'onglet
            handlePrivateChannelOpened(data.channel_id, data.text, (data.members || []).filter(m => m !== playerId));
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
            addNightHistory(data.turn, "role_info", data.info);
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
            triggerGameOver(data.winner, data.details);
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
