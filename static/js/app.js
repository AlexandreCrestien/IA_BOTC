// ================= STATE GLOBAL DE L'APPLICATION =================
let ws = null;
let playerId = "";
let currentWhisperAgentId = null; // Stocke l'agent qui demande un entretien
let gameState = {
    day: 1,
    phase: "day", // "day", "night", "vote"
    aliveCount: 0,
    players: [], // { id, name, alive: true, role: null, suspicion: "", lastVote: null }
    messages: { public: [] }, // channel_id -> [messages]
    currentChannel: "public",
    announcement: "En attente du début de la partie...",
    roleInfo: { name: "En attente...", description: "La partie va démarrer." }
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
        badge.className = "px-3 py-1 rounded-full text-xs font-semibold bg-green-900/50 text-green-400 border border-green-700 whitespace-nowrap";
        badge.innerText = "Connecté";
    } else {
        badge.className = "px-3 py-1 rounded-full text-xs font-semibold bg-red-900/50 text-red-400 border border-red-700 whitespace-nowrap";
        badge.innerText = "Déconnecté";
    }
}

// ================= GESTION DES MESSAGES SERVEUR =================
function handleServerMessage(data) {
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
            triggerAgentWhisper(data.agent_id, data.agent_name, data.message);
            break;
        case "game_over":
            triggerGameOver(data.winner, data.details);
            break;
        case "private_channel_opened":
            handlePrivateChannelOpened(data.channel_id, data.text);
            break;
        default:
            console.log("Message non géré :", data);
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

    // On envoie au serveur. C'est le message reçu du serveur qui l'affichera proprement.
    ws.send(JSON.stringify(packet));

    // On vide simplement l'input
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
        <div class="mb-1.5">
            <span class="text-clock-gold font-bold">[${m.sender}]</span>: ${escapeHtml(m.content)}
        </div>
    `).join('') || '<div class="text-gray-500 italic text-center">Aucun message dans ce canal...</div>';
    box.scrollTop = box.scrollHeight;
}

function appendSystemMessage(text) {
    const box = document.getElementById('chat-messages');
    box.innerHTML += `<div class="text-yellow-500/80 italic">⚙️ ${text}</div>`;
    box.scrollTop = box.scrollHeight;
}

function handlePrivateChannelOpened(channelId, text, members = []) {
    appendSystemMessage(text);
    
    // 1. Initialiser le stockage des messages pour ce salon s'il n'existe pas
    if (!gameState.messages[channelId]) {
        gameState.messages[channelId] = [];
    }

    // 2. Créer l'onglet dans la barre de chat s'il n'existe pas encore
    const channelsContainer = document.getElementById('chat-channels');
    if (channelsContainer && !document.getElementById(`tab-${channelId}`)) {
        const tabTitle = members.length > 0 ? `🔒 ${members.join(', ')}` : `🔒 Privé`;
        
        const tabButton = document.createElement('button');
        tabButton.id = `tab-${channelId}`;
        tabButton.className = "channel-btn bg-clock-panel text-gray-400 hover:text-white px-3 py-1.5 rounded-lg font-medium border border-clock-border whitespace-nowrap text-xs transition-colors";
        tabButton.innerText = tabTitle;
        tabButton.onclick = () => switchChannel(channelId);
        
        channelsContainer.appendChild(tabButton);
    }
    
    // 3. Basculer automatiquement sur ce nouveau canal privé
    switchChannel(channelId);
}

function switchChannel(channelId) {
    gameState.currentChannel = channelId;
    
    // Mettre à jour l'apparence de tous les boutons de salons
    const allButtons = document.querySelectorAll('#chat-channels button');
    allButtons.forEach(btn => {
        // On vérifie si c'est le bouton actif en comparant son ID (ex: "tab-public" ou "tab-whisper_...")
        const isPublicBtnActive = (channelId === 'public' && btn.getAttribute('onclick')?.includes("'public'"));
        const isPrivateBtnActive = (btn.id === `tab-${channelId}`);
        
        if (isPublicBtnActive || isPrivateBtnActive) {
            btn.classList.remove('text-gray-400', 'bg-clock-panel');
            btn.classList.add('text-clock-gold', 'bg-clock-accent', 'border-clock-gold');
        } else {
            btn.classList.add('text-gray-400', 'bg-clock-panel');
            btn.classList.remove('text-clock-gold', 'bg-clock-accent', 'border-clock-gold');
        }
    });

    // Rafraîchir l'affichage des messages dans la boîte de chat
    renderChatMessages();
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
        table.innerHTML = `<div class="text-center text-gray-500 text-sm italic">En attente des joueurs...</div>`;
        return;
    }

    const radius = 130; // Rayon du cercle en pixels
    const centerX = table.offsetWidth / 2 || 192;
    const centerY = table.offsetHeight / 2 || 192;

    let html = '';
    players.forEach((p, index) => {
        const angle = (index / players.length) * 2 * Math.PI - Math.PI / 2;
        const x = centerX + radius * Math.cos(angle) - 36; // Centrage avatar
        const y = centerY + radius * Math.sin(angle) - 36;

        const statusColor = p.alive ? 'border-green-600 bg-clock-panel' : 'border-red-900 bg-red-950/40 opacity-70';
        
        html += `
            <div class="absolute w-20 h-20 rounded-full border-2 ${statusColor} flex flex-col items-center justify-center p-1 text-center shadow-lg transition-all duration-300 cursor-pointer hover:scale-105"
                 style="left: ${x}px; top: ${y}px;" title="${p.name} (${p.alive ? 'Vivant' : 'Mort'})">
                <span class="text-xs font-bold truncate w-full text-gray-200 px-1">${p.name}</span>
                <span class="text-xs ${p.alive ? 'text-green-400 font-semibold' : 'text-red-500 font-semibold'}">${p.alive ? 'Vivant' : 'Mort'}</span>
            </div>
        `;
    });

    table.innerHTML = html;
}

function renderPlayersList() {
    const list = document.getElementById('players-notes-list');
    const players = gameState.players || [];
    
    list.innerHTML = players.map(p => `
        <div class="bg-clock-dark border border-clock-border p-2.5 rounded-xl space-y-2">
            <div class="flex justify-between items-center text-sm">
                <span class="font-bold ${p.alive ? 'text-gray-200' : 'text-gray-500 line-through'}">${p.name}</span>
                <span class="text-xs px-2 py-0.5 rounded font-medium ${p.alive ? 'bg-green-900/40 text-green-400' : 'bg-red-900/40 text-red-400'}">
                    ${p.alive ? 'Vivant' : 'Mort'}
                </span>
            </div>
            ${!p.alive ? `<div class="text-xs text-gray-400">Dernier vote : ${p.lastVote !== null ? p.lastVote : 'Non utilisé'}</div>` : ''}
            <div class="flex items-center">
                <select onchange="updateSuspicion('${p.id}', this.value)" class="w-full bg-clock-panel border border-clock-border text-xs rounded px-2 py-1.5 text-gray-300 focus:outline-none focus:border-clock-gold">
                    <option value="">-- Rôle soupçonné --</option>
                    
                    <optgroup label="Camps">
                        <option value="Townsfolk" ${p.suspicion === 'Townsfolk' ? 'selected' : ''}>Villageois (gentil)</option>
                        <option value="Demon" ${p.suspicion === 'Demon' ? 'selected' : ''}>Démon (méchant)</option>
                    </optgroup>

                    <optgroup label="Rôles">
                        <option value="diablotin" ${p.suspicion === 'diablotin' ? 'selected' : ''}>Diablotin (Démon)</option>
                        <option value="empoisonneur" ${p.suspicion === 'empoisonneur' ? 'selected' : ''}>Empoisonneur (Démon - Sbire)</option>
                        <option value="voyante" ${p.suspicion === 'voyante' ? 'selected' : ''}>Voyante (Villageois)</option>
                        <option value="moine" ${p.suspicion === 'moine' ? 'selected' : ''}>Moine (Villageois)</option>
                        <option value="detective" ${p.suspicion === 'detective' ? 'selected' : ''}>Détective (Villageois)</option>
                        <option value="majordome" ${p.suspicion === 'majordome' ? 'selected' : ''}>Majordome (Villageois - Étranger)</option>
                    </optgroup>
                </select>
            </div>
        </div>
    `).join('') || '<div class="text-gray-500 text-sm italic">Aucun joueur inscrit.</div>';
}

function renderActionPanel() {
    const panel = document.getElementById('dynamic-action-panel');
    const phase = gameState.phase;

    if (phase === 'day') {
        const otherPlayers = (gameState.players || []).filter(p => p.id !== playerId);
        panel.innerHTML = `
            <div class="text-gray-300 text-sm">Phase de discussion. Choisissez jusqu'à 2 agents pour une conversation privée.</div>
            <div class="space-y-2 mt-2">
                <div class="text-xs text-clock-gold font-semibold">Cible principale :</div>
                <select id="whisper-target-1" class="w-full bg-clock-dark border border-clock-border rounded p-2 text-xs text-gray-200 focus:outline-none focus:border-clock-gold">
                    <option value="">-- Choisir un 1er agent --</option>
                    ${otherPlayers.map(p => `<option value="${p.id}">${p.name}</option>`).join('')}
                </select>

                <div class="text-xs text-clock-gold font-semibold">Cible secondaire (optionnelle) :</div>
                <select id="whisper-target-2" class="w-full bg-clock-dark border border-clock-border rounded p-2 text-xs text-gray-200 focus:outline-none focus:border-clock-gold">
                    <option value="">-- Aucune (1 seul agent) --</option>
                    ${otherPlayers.map(p => `<option value="${p.id}">${p.name}</option>`).join('')}
                </select>

                <button onclick="requestWhisper()" class="w-full bg-clock-gold/20 hover:bg-clock-gold/30 text-clock-gold border border-clock-gold/50 py-2 rounded-lg text-xs font-semibold transition uppercase tracking-wider">
                    Proposer un chuchotement
                </button>
            </div>
        `;
    } else if (phase === 'vote') {
        panel.innerHTML = `
            <div class="text-blue-400 text-sm font-semibold">Phase de Vote & Exécution</div>
            <div class="text-gray-300 text-xs">Indiquez votre choix d'exécution pour le village :</div>
            <select id="vote-target-select" class="w-full bg-clock-dark border border-clock-border rounded p-2 text-sm text-gray-200 focus:outline-none focus:border-clock-gold">
                <option value="">Ne voter pour personne</option>
                ${(gameState.players || []).filter(p => p.alive).map(p => `<option value="${p.id}">${p.name}</option>`).join('')}
            </select>
            <button onclick="submitVote()" class="w-full bg-clock-red hover:bg-red-800 text-white py-2 rounded-lg text-xs font-semibold transition uppercase tracking-wider">
                Confirmer mon vote
            </button>
        `;
    } else if (phase === 'night') {
        panel.innerHTML = `
            <div class="text-purple-400 text-sm font-semibold">Phase Nocturne</div>
            <div class="text-gray-300 text-xs">Le village endormi... Sélectionnez vos cibles de nuit :</div>
            <select id="night-target-select" class="w-full bg-clock-dark border border-clock-border rounded p-2 text-sm text-gray-200 focus:outline-none focus:border-clock-gold">
                <option value="">Aucune cible</option>
                ${(gameState.players || []).map(p => `<option value="${p.id}">${p.name}</option>`).join('')}
            </select>
            <button onclick="submitNightAction()" class="w-full bg-purple-900/40 hover:bg-purple-900/60 text-purple-300 border border-purple-700 py-2 rounded-lg text-xs font-semibold transition uppercase tracking-wider">
                Valider l'action nocturne
            </button>
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

// Demande initiée par le joueur vers un agent
function requestWhisper() {
    const target1 = document.getElementById('whisper-target-1').value;
    const target2 = document.getElementById('whisper-target-2').value;

    if (!target1) {
        alert("Veuillez sélectionner au moins un premier agent.");
        return;
    }

    if (target1 === target2) {
        alert("Vous ne pouvez pas sélectionner deux fois le même agent.");
        return;
    }

    const targets = [target1];
    if (target2) {
        targets.push(target2);
    }

    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            action: "request_whisper",
            payload: { targets: targets }
        }));
        
        // Masquer/réinitialiser le panneau de sélection (ou afficher un message de confirmation dans le panneau)
        const panel = document.getElementById('dynamic-action-panel');
        panel.innerHTML = `<div class="text-green-400 text-xs italic text-center py-2">✓ Proposition de discussion privée transmise. Ouverture du salon.</div>`;
    }
}

// Réception d'une proposition de chuchotement venant d'un agent
function triggerAgentWhisper(agentId, agentName, message) {
    currentWhisperAgentId = agentId;
    const textEl = document.getElementById('agent-whisper-text');
    textEl.innerHTML = `<strong>${agentName || agentId}</strong> souhaite s'entretenir discrètement avec vous.<br><em class="text-xs text-gray-400">"${message || ''}"</em>`;
    document.getElementById('modal-agent-whisper').classList.remove('hidden');
}

// L'humain accepte la proposition de l'agent
function acceptAgentWhisper() {
    document.getElementById('modal-agent-whisper').classList.add('hidden');
    
    if (ws && ws.readyState === WebSocket.OPEN && currentWhisperAgentId) {
        ws.send(JSON.stringify({
            action: "respond_whisper_invitation",
            payload: {
                target_agent_id: currentWhisperAgentId,
                accepted: true
            }
        }));
        appendSystemMessage(`Vous avez accepté l'entretien avec ${currentWhisperAgentId}.`);
        // Basculer vers un onglet ou créer un canal privé si besoin
        switchChannel(currentWhisperAgentId);
    }
    currentWhisperAgentId = null;
}

// L'humain refuse la proposition de l'agent
function closeAgentWhisper() {
    document.getElementById('modal-agent-whisper').classList.add('hidden');
    
    if (ws && ws.readyState === WebSocket.OPEN && currentWhisperAgentId) {
        ws.send(JSON.stringify({
            action: "respond_whisper_invitation",
            payload: {
                target_agent_id: currentWhisperAgentId,
                accepted: false
            }
        }));
        appendSystemMessage(`Vous avez refusé l'entretien.`);
    }
    currentWhisperAgentId = null;
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

function submitNightAction() {
    const select = document.getElementById('night-target-select');
    const targetId = select ? select.value : null;
    const targets = targetId ? [targetId] : [];

    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            action: "submit_night_action",
            payload: { targets: targets }
        }));
        appendSystemMessage(`Action nocturne validée (${targets.length} cible(s)).`);
    }
}

function escapeHtml(text) {
    if (!text) return '';
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}