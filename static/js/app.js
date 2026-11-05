// ================= STATE GLOBAL DE L'APPLICATION =================
let ws = null;
let playerId = "";
let gameState = {
    day: 1,
    phase: "day", // "day", "night", "vote"
    aliveCount: 0,
    players: [], // { id, name, alive: true, role: null, suspicion: "", lastVote: null }
    messages: { public: [] }, // channel_id -> [messages]
    currentChannel: "public",
    announcement: "En attente du début de la partie...",
    roleInfo: { name: "En attente...", description: "Le Grimoire va s'ouvrir." }
};

// ================= INITIALISATION & CONNEXION =================
function joinGame() {
    const input = document.getElementById('welcome-player-id');
    playerId = input.value.trim();
    if (!playerId) {
        alert("Veuillez entrer un identifiant valide.");
        return;
    }

    const wsUrl = `ws://127.0.0.1:8000/ws/${playerId}`;
    ws = new WebSocket(wsUrl);

    ws.onopen = function() {
        console.log("WebSocket connectée.");
        // Masquer l'écran d'accueil et afficher l'interface de jeu
        document.getElementById('screen-welcome').classList.add('hidden');
        document.getElementById('screen-game').classList.remove('hidden');
        updateConnectionBadge(true);
        appendSystemMessage("Connexion établie avec le serveur.");
    };

    ws.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            handleServerMessage(data);
        } catch (e) {
            console.error("Erreur de parsing JSON WebSocket :", e);
        }
    };

    ws.onclose = function() {
        updateConnectionBadge(false);
        appendSystemMessage("Connexion fermée par le serveur.");
    };

    ws.onerror = function(error) {
        console.error("Erreur WebSocket :", error);
        appendSystemMessage("Erreur de connexion réseau.");
    };
}

function updateConnectionBadge(isConnected) {
    const badge = document.getElementById('connection-status');
    if (isConnected) {
        badge.className = "px-3 py-1 rounded-full text-xs font-semibold bg-green-900/50 text-green-400 border border-green-700";
        badge.innerText = "Connecté";
    } else {
        badge.className = "px-3 py-1 rounded-full text-xs font-semibold bg-red-900/50 text-red-400 border border-red-700";
        badge.innerText = "Déconnecté";
    }
}

// ================= GESTION DES MESSAGES SERVEUR =================
function handleServerMessage(data) {
    // Le serveur envoie différents types de paquets (ex: state_update, chat, role_assigned, etc.)
    switch (data.type) {
        case "chat":
            receiveChatMessage(data.channel_id || "public", data.sender, data.content);
            break;
        case "game_state":
            updateGameState(data.state);
            break;
        case "role_assigned":
            assignRole(data.role_name, data.description);
            break;
        case "announcement":
            setAnnouncement(data.text);
            break;
        case "agent_whisper_request":
            triggerAgentWhisper(data.agent_name);
            break;
        case "game_over":
            triggerGameOver(data.winner, data.details);
            break;
        default:
            console.message("Message non géré :", data);
    }
}

// ================= CHAT & ONGLETS LATÉRAUX =================
function switchLeftTab(tabName) {
    ['chat', 'night', 'votes'].forEach(t => {
        document.getElementById(`tab-content-${t}`).classList.add('hidden');
        document.getElementById(`tab-btn-${t}`).className = "flex-1 py-3 font-medium text-gray-400 hover:text-gray-200 transition";
    });
    document.getElementById(`tab-content-${tabName}`).classList.remove('hidden');
    document.getElementById(`tab-btn-${tabName}`).className = "flex-1 py-3 font-semibold text-clock-gold border-b-2 border-clock-gold transition";
}

function switchChannel(channelId) {
    gameState.currentChannel = channelId;
    renderChatMessages();
}

function sendChatMessage() {
    const input = document.getElementById('chat-input');
    const content = input.value.trim();
    if (!content || !ws || ws.readyState !== WebSocket.OPEN) return;

    const packet = {
        action: "send_chat",
        payload: {
            channel_id: gameState.currentChannel,
            content: content
        }
    };

    ws.send(JSON.stringify(packet));

    // Affichage local immédiat
    if (!gameState.messages[gameState.currentChannel]) {
        gameState.messages[gameState.currentChannel] = [];
    }
    gameState.messages[gameState.currentChannel].push({ sender: "Moi", content: content });
    renderChatMessages();
    input.value = "";
}

function receiveChatMessage(channelId, sender, content) {
    if (!gameState.messages[channelId]) {
        gameState.messages[channelId] = [];
    }
    gameState.messages[channelId].push({ sender: sender, content: content });
    renderChatMessages();
}

function renderChatMessages() {
    const box = document.getElementById('chat-messages');
    const msgs = gameState.messages[gameState.currentChannel] || [];
    box.innerHTML = msgs.map(m => `
        <div class="mb-1">
            <span class="text-clock-gold">[${m.sender}]</span>: ${escapeHtml(m.content)}
        </div>
    `).join('') || '<div class="text-gray-500 italic text-center">Aucun message dans ce canal...</div>';
    box.scrollTop = box.scrollHeight;
}

function appendSystemMessage(text) {
    const box = document.getElementById('chat-messages');
    box.innerHTML += `<div class="text-yellow-500/80 italic">⚙️ ${text}</div>`;
    box.scrollTop = box.scrollHeight;
}

// ================= TABLE RONDE & ÉTAT DU JEU =================
function updateGameState(newState) {
    gameState = { ...gameState, ...newState };
    
    // MAJ Header
    document.getElementById('game-day').innerText = gameState.day;
    document.getElementById('game-phase').innerText = gameState.phase === 'night' ? 'Nuit' : (gameState.phase === 'vote' ? 'Vote' : 'Jour');
    document.getElementById('alive-count').innerText = gameState.aliveCount;

    renderRoundTable();
    renderPlayersList();
    renderActionPanel();
}

function renderRoundTable() {
    const table = document.getElementById('round-table');
    const players = gameState.players || [];
    if (players.length === 0) {
        table.innerHTML = `<div class="text-center text-gray-500 text-xs italic">En attente des joueurs...</div>`;
        return;
    }

    const radius = 130; // Rayon du cercle en pixels
    const centerX = table.offsetWidth / 2 || 180;
    const centerY = table.offsetHeight / 2 || 180;

    let html = '';
    players.forEach((p, index) => {
        const angle = (index / players.length) * 2 * Math.PI - Math.PI / 2;
        const x = centerX + radius * Math.cos(angle) - 30; // 30 = demi taille avatar
        const y = centerY + radius * Math.sin(angle) - 30;

        const statusColor = p.alive ? 'border-green-600 bg-clock-panel' : 'border-red-900 bg-red-950/40 opacity-70';
        
        html += `
            <div class="absolute w-16 h-16 rounded-full border-2 ${statusColor} flex flex-col items-center justify-center p-1 text-center shadow-lg transition-all duration-300 cursor-pointer hover:scale-105"
                 style="left: ${x}px; top: ${y}px;" title="${p.name} (${p.alive ? 'Vivant' : 'Mort'})">
                <span class="text-[10px] font-bold truncate w-full text-gray-200">${p.name}</span>
                <span class="text-[9px] ${p.alive ? 'text-green-400' : 'text-red-500'}">${p.alive ? 'Vivant' : 'Mort'}</span>
            </div>
        `;
    });

    table.innerHTML = html;
}

function renderPlayersList() {
    const list = document.getElementById('players-notes-list');
    const players = gameState.players || [];
    
    list.innerHTML = players.map(p => `
        <div class="bg-clock-dark border border-clock-border p-2 rounded-xl space-y-1.5">
            <div class="flex justify-between items-center text-xs">
                <span class="font-bold ${p.alive ? 'text-gray-200' : 'text-gray-500 line-through'}">${p.name}</span>
                <span class="text-[10px] px-1.5 py-0.5 rounded ${p.alive ? 'bg-green-900/40 text-green-400' : 'bg-red-900/40 text-red-400'}">
                    ${p.alive ? 'Vivant' : 'Mort'}
                </span>
            </div>
            ${!p.alive ? `<div class="text-[10px] text-gray-500">Dernier vote : ${p.lastVote !== null ? p.lastVote : 'Non utilisé'}</div>` : ''}
            <div class="flex items-center space-x-1">
                <select onchange="updateSuspicion('${p.id}', this.value)" class="w-full bg-clock-panel border border-clock-border text-[10px] rounded px-1 py-1 text-gray-300 focus:outline-none">
                    <option value="">-- Soupçon / Rôle --</option>
                    <option value="Townsfolk" ${p.suspicion === 'Townsfolk' ? 'selected' : ''}>Villageois (Bien)</option>
                    <option value="Outsider" ${p.suspicion === 'Outsider' ? 'selected' : ''}>Étranger</option>
                    <option value="Minion" ${p.suspicion === 'Minion' ? 'selected' : ''}>Sous-fifre (Mal)</option>
                    <option value="Demon" ${p.suspicion === 'Demon' ? 'selected' : ''}>Démon (Mal)</option>
                </select>
            </div>
        </div>
    `).join('') || '<div class="text-gray-500 text-xs italic">Aucun joueur inscrit.</div>';
}

function renderActionPanel() {
    const panel = document.getElementById('dynamic-action-panel');
    const phase = gameState.phase;

    if (phase === 'day') {
        panel.innerHTML = `
            <div class="text-gray-300 text-[11px]">Phase de discussion. Choisissez des agents pour une conversation privée ou discutez dans le chat public.</div>
            <button onclick="openPrivateChatModal()" class="w-full bg-clock-gold/20 hover:bg-clock-gold/30 text-clock-gold border border-clock-gold/50 py-1.5 rounded-lg text-xs font-semibold transition mt-1">
                Proposer un chuchotement
            </button>
        `;
    } else if (phase === 'vote') {
        panel.innerHTML = `
            <div class="text-blue-400 text-[11px] font-semibold">Phase de Vote & Exécution</div>
            <div class="text-gray-400 text-[10px]">Indiquez votre choix d'exécution pour le village :</div>
            <select id="vote-target-select" class="w-full bg-clock-dark border border-clock-border rounded p-1 text-xs text-gray-200">
                <option value="">Ne voter pour personne</option>
                ${(gameState.players || []).filter(p => p.alive).map(p => `<option value="${p.id}">${p.name}</option>`).join('')}
            </select>
            <button onclick="submitVote()" class="w-full bg-clock-red hover:bg-red-800 text-white py-1.5 rounded-lg text-xs font-semibold transition">
                Confirmer mon vote
            </button>
        `;
    } else if (phase === 'night') {
        panel.innerHTML = `
            <div class="text-purple-400 text-[11px] font-semibold">Phase Nocturne</div>
            <div class="text-gray-400 text-[10px]">Le village endormi... Votre capacité secrète s'active.</div>
        `;
    }
}

// ================= INTERACTIONS & MODALES =================
function assignRole(name, description) {
    gameState.roleInfo = { name, description };
    document.getElementById('player-role-name').innerText = name;
    document.getElementById('player-role-desc').innerText = description;
    
    document.getElementById('modal-role-title').innerText = name;
    document.getElementById('modal-role-description').innerText = description;
    document.getElementById('modal-role-reveal').classList.remove('hidden');
}

function closeRoleRevealModal() {
    document.getElementById('modal-role-reveal').classList.add('hidden');
}

function setAnnouncement(text) {
    document.getElementById('game-announcement').innerText = `Annonce : ${text}`;
}

function triggerAgentWhisper(agentName) {
    document.getElementById('agent-whisper-text').innerText = `${agentName} souhaite s'entretenir discrètement avec vous.`;
    document.getElementById('modal-agent-whisper').classList.remove('hidden');
}

function acceptAgentWhisper() {
    document.getElementById('modal-agent-whisper').classList.add('hidden');
    // Logique d'ouverture de canal privé avec l'agent
}

function closeAgentWhisper() {
    document.getElementById('modal-agent-whisper').classList.add('hidden');
}

function triggerGameOver(winner, details) {
    document.getElementById('gameover-title').innerText = `Victoire : ${winner}`;
    document.getElementById('gameover-desc').innerText = details;
    document.getElementById('modal-gameover').classList.remove('hidden');
}

function updateSuspicion(playerId, roleType) {
    const player = (gameState.players || []).find(p => p.id === playerId);
    if (player) {
        player.suspicion = roleType;
    }
}

function submitVote() {
    const select = document.getElementById('vote-target-select');
    const targetId = select ? select.value : null;
    
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            action: "submit_vote",
            payload: { target_id: targetId }
        }));
        appendSystemMessage(`Vote enregistré pour : ${targetId ? targetId : 'Personne'}`);
    }
}

function escapeHtml(text) {
    if (!text) return '';
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}