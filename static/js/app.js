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
    roleInfo: { name: "En attente...", description: "La partie va démarrer." },
    vote_history: [],
    night_info_history: []
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
        case "vote_result":
            showVoteResultModal(data.turn, data.executed, data.votes);
            break;
        case "night_result":
            showNightResultModal(data.turn, data.dead_player); // data.turn et data.dead_player
            break;
        case "night_info":
            showNightInfoModal(data.turn, data.info); // Information spécifique reçue la nuit selon le rôle
            break;
        default:
            console.log("Message non géré :", data);
    }
}

// ================= CHAT & ONGLETS LATÉRAUX =================
function switchLeftTab(tabName) {
    ['chat', 'night', 'votes'].forEach(t => {
        const content = document.getElementById(`tab-content-${t}`);
        const btn = document.getElementById(`tab-btn-${t}`);
        
        if (content) content.classList.add('hidden');
        if (btn) {
            // Style de l'onglet inactif (ajusté selon la charte)
            btn.className = "flex-1 py-3 font-medium text-muted-foreground hover:text-foreground transition border-b-2 border-transparent";
        }
    });

    const activeContent = document.getElementById(`tab-content-${tabName}`);
    const activeBtn = document.getElementById(`tab-btn-${tabName}`);

    if (activeContent) activeContent.classList.remove('hidden');
    if (activeBtn) {
        // Style de l'onglet ACTIF : texte doré permanent et bordure dorée
        activeBtn.className = "flex-1 py-3 font-semibold text-gold border-b-2 border-[var(--gold)] transition";
    }
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
    if (!box) return;

    let html = '';

    // 1. En-tête conditionnel selon le canal actif
    if (gameState.currentChannel === 'public') {
        html = `
            <div class="ornament animate-rise px-2 text-center my-2">
                <p class="max-w-[85%] mx-auto font-serif text-sm italic text-gold">Canal public initialisé...</p>
            </div>
            <div class="ornament animate-rise px-2 text-center my-2">
                <p class="max-w-[85%] mx-auto font-serif text-sm italic text-gold">Connexion établie avec le serveur.</p>
            </div>
        `;
    } else {
        // Récupère le nom du canal affiché dans le header pour un message sur mesure
        const channelTitle = document.getElementById('active-channel-title')?.textContent || 'cette conversation';
        html = `
            <div class="ornament animate-rise px-2 text-center my-2">
                <p class="max-w-[85%] mx-auto font-serif text-sm italic text-gold">Début de la discussion privée avec ${channelTitle}.</p>
            </div>
        `;
    }

    // 2. Récupération des messages du canal courant
    const msgs = gameState.messages[gameState.currentChannel] || [];

    if (msgs.length === 0) {
        html += `<div class="text-gray-500 italic text-center py-4 text-xs">Aucun message dans ce canal...</div>`;
    } else {
        // 3. Boucle sur les messages des joueurs
        html += msgs.map(m => `
            <div class="flex animate-rise flex-col items-start my-3">
                <div class="mb-0.5 flex items-baseline gap-2 px-1 text-[11px]">
                    <span class="font-semibold text-foreground/80">${escapeHtml(m.sender)}</span>
                    <span class="text-muted-foreground">${m.time || '13:20'}</span>
                </div>
                <p class="break-words rounded-lg px-3 py-2 text-s leading-relaxed rounded-tl-sm border border-[var(--border)] bg-[var(--card)] text-foreground">
                    ${escapeHtml(m.content)}
                </p>
            </div>
        `).join('');
    }

    // 4. Injection dans le conteneur et défilement automatique
    box.innerHTML = html;
    box.scrollTop = box.scrollHeight;
}

function appendSystemMessage(text) {
    const box = document.getElementById('chat-messages');
    if (!box) return;

    // Création de l'élément avec le style ornemental Lovable
    const msgDiv = document.createElement('div');
    msgDiv.className = "ornament animate-rise px-2 text-center my-2";
    msgDiv.innerHTML = `
        <p class="max-w-[85%] mx-auto font-serif text-sm italic text-gold">
            ${escapeHtml(text)}
        </p>
    `;

    // Ajout dans la boîte de chat
    box.appendChild(msgDiv);
    box.scrollTop = box.scrollHeight;
}

function handlePrivateChannelOpened(channelId, text, members = []) {
    appendSystemMessage(text);
    
    if (!gameState.messages[channelId]) {
        gameState.messages[channelId] = [];
    }

    const channelsContainer = document.getElementById('chat-channels');
    if (channelsContainer && !document.getElementById(`tab-${channelId}`)) {
        const tabTitle = members.length > 0 ? `${members.join(', ')}` : `Privé`;
        
        const tabButton = document.createElement('button');
        tabButton.id = `tab-${channelId}`;
        // Design harmonisé : flex, bordure dorée subtile, texte discret, sans fond violet par défaut
        tabButton.className = "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-muted-foreground hover:text-foreground hover:bg-white/5 border border-gold/30 transition-colors shrink-0";
        tabButton.innerText = tabTitle;
        tabButton.onclick = () => switchChannel(channelId);
        
        channelsContainer.appendChild(tabButton);
    }
    
    switchChannel(channelId);
}

function switchChannel(channelId) {
    gameState.currentChannel = channelId;

    // 1. Mise à jour du titre affiché dans l'en-tête actif
    let channelName = "Place publique";
    if (channelId !== 'public') {
        const targetBtn = document.getElementById(`tab-${channelId}`);
        channelName = targetBtn ? targetBtn.innerText.trim() : channelId;
    }

    const titleElement = document.getElementById('active-channel-title');
    if (titleElement) {
        titleElement.textContent = channelName;
    }

    // 2. Gestion des états actifs / inactifs des boutons
    const allButtons = document.querySelectorAll('nav[aria-label="Canaux"] button');
    
    allButtons.forEach(btn => {
        // Vérifie si c'est le bouton actif (public ou autre canal)
        const isTargetBtn = (btn.id === `tab-${channelId}`) || (channelId === 'public' && (btn.id === 'tab-public' || btn.getAttribute('onclick')?.includes("'public'")));

        if (isTargetBtn) {
            // ACTIF : Fond violet/actif (adapte selon tes classes, ici on enlève le transparent)
            btn.className = "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm channel-btn transition-colors bg-secondary/80 text-foreground border border-[var(--gold)]";
        } else {
            // INACTIF : Transparent et discret
            btn.className = "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-muted-foreground hover:text-foreground hover:bg-white/5 bg-transparent channel-btn transition-colors border border-transparent";
        }
    });

    // 3. Rendu des messages du canal sélectionné
    renderChatMessages();
}

function renderVoteHistory() {
    const container = document.getElementById('tab-content-votes');
    if (!container) return;

    if (!gameState.vote_history || gameState.vote_history.length === 0) {
        container.innerHTML = `
            <div class="text-center text-muted-foreground py-8 text-xs italic font-serif">
                Aucun vote enregistré pour le moment.
            </div>
        `;
        return;
    }

    const turnsMap = {};
    gameState.vote_history.forEach(record => {
        if (!turnsMap[record.turn]) {
            turnsMap[record.turn] = { votes: [], executed: record.executed };
        }
        turnsMap[record.turn].votes.push(record);
    });

    let html = '<div class="p-1 space-y-3">';
    
    Object.keys(turnsMap).sort((a, b) => b - a).forEach(turn => {
        const data = turnsMap[turn];
        const executionText = data.executed ? `${data.executed} exécuté` : "Aucune exécution";

        // Ornement pour le titre du tour de vote
        html += `
            <div class="space-y-2">
                <div class="ornament animate-rise px-2 text-center my-3">
                    <p class="max-w-[85%] mx-auto font-serif text-sm italic text-gold">
                        Tour ${turn} — ${executionText}
                    </p>
                </div>
                <div class="space-y-1.5 pl-2 border-border/70">
        `;

        data.votes.forEach(v => {
            const targetText = v.target ? v.target : "Vote blanc";
            html += `
                <div class="panel p-2.5 rounded-lg border border-border bg-secondary/40 text-xs flex justify-between items-center">
                    <div>
                        <span class="font-semibold text-foreground">${escapeHtml(v.voter)}</span>
                        <span class="text-muted-foreground ml-1.5">a voté pour</span>
                        <span class="font-semibold text-gold ml-1">${escapeHtml(targetText)}</span>
                    </div>
                </div>
            `;
        });

        html += `
                </div>
            </div>
        `;
    });

    html += '</div>';
    container.innerHTML = html;
}

// Rendu de l'historique des infos et événements de la nuit
function renderNightInfoHistory() {
    const container = document.getElementById('tab-content-night');
    if (!container) return;

    if (!gameState.night_info_history || !Array.isArray(gameState.night_info_history) || gameState.night_info_history.length === 0) {
        container.innerHTML = `
            <div class="text-center text-muted-foreground py-8 text-sm italic font-serif">
                Aucun événement nocturne pour le moment.
            </div>
        `;
        return;
    }

    let html = '<div class="p-1 space-y-3">';
    
    gameState.night_info_history.forEach(item => {
        const isResult = item.type === "result";
        // Utilisation de bordures et teintes cohérentes avec le design system
        const borderColor = isResult ? "border-red-500/30" : "border-border";
        const titleColor = isResult ? "text-red-400" : "text-gold";
        const bgStyle = isResult ? "bg-red-950/10" : "bg-secondary/50";

        html += `
            <div class="panel rounded-lg border ${borderColor} ${bgStyle} p-3 text-s">
                <div class="flex items-center justify-between mb-1">
                    <span class="${titleColor} font-serif font-bold italic">Tour ${item.turn}</span>
                </div>
                <p class="text-foreground/90 font-sans leading-relaxed">${escapeHtml(item.info || item.text || '')}</p>
            </div>
        `;
    });

    html += '</div>';
    container.innerHTML = html;
}

// ================= TABLE RONDE & ÉTAT DU JEU =================
function updateGameState(newState) {
    gameState = { ...gameState, ...newState };
    
    document.getElementById('game-day').innerText = gameState.day;
    document.getElementById('game-phase').innerText = gameState.phase === 'nuit' ? 'Nuit' : (gameState.phase === 'vote' ? 'Vote' : 'Discussion');
    document.getElementById('alive-count').innerText = gameState.aliveCount;

    // Mise à jour contextuelle de l'annonce si le serveur ne donne pas d'annonce explicite dans le paquet
    if (newState.announcement) {
        setAnnouncement(newState.announcement);
    } else if (newState.phase === 'night') {
        setAnnouncement("La nuit tombe... Reposez-vous pendant que les autres joueurs vaquent à leurs occupations.");
    } else if (newState.phase === 'vote') {
        setAnnouncement("Phase de vote : réflexion et choix des joueurs en cours...");
    }

    renderRoundTable();
    renderPlayersList();
    renderActionPanel();
}

function renderRoundTable() {
    const table = document.getElementById('round-table');
    const players = gameState.players || [];
    
    // Bouton Grimoire central
    const grimoireBtnHtml = `
        <button onclick="openGrimoireModal()" class="z-10 group bg-clock-dark/90 hover:bg-clock-gold/20 border-2 border-clock-gold/60 hover:border-clock-gold text-clock-gold p-5 rounded-full shadow-2xl transition-all duration-300 transform hover:scale-110 flex flex-col items-center justify-center">
            <span class="text-4xl group-hover:rotate-12 transition-transform duration-300">📖</span>
            <span class="text-xs font-mono uppercase tracking-widest mt-1 font-bold">Grimoire</span>
        </button>
    `;

    if (players.length === 0) {
        table.innerHTML = `
            ${grimoireBtnHtml}
            <div class="absolute text-center text-gray-500 text-xs italic pointer-events-none mt-32">
                En attente des joueurs...
            </div>
        `;
        return;
    }

    // 💡 Rayon augmenté à 200px pour décaler les cercles vers l'extérieur 
    // (le conteneur faisant ~420px, un rayon de 200 place le centre des cercles pile sur le trait de la table)
    const radius = 200; 
    const centerX = table.offsetWidth / 2 || 210;
    const centerY = table.offsetHeight / 2 || 210;

    let html = grimoireBtnHtml;

    players.forEach((p, index) => {
        const angle = (index / players.length) * 2 * Math.PI - Math.PI / 2;
        
        // Offset à 56px (moitié de la taille de l'avatar w-28 = 112px)
        const x = centerX + radius * Math.cos(angle) - 56;
        const y = centerY + radius * Math.sin(angle) - 56;

        const statusColor = p.alive 
            ? 'border-green-500/80 bg-clock-panel shadow-green-950/40' 
            : 'border-red-900 bg-red-950/50 opacity-70 shadow-red-950/40';
        
        html += `
            <div class="absolute w-28 h-28 rounded-full border-2 ${statusColor} flex flex-col items-center justify-center p-2.5 text-center shadow-2xl transition-all duration-300 cursor-pointer hover:scale-110 z-10"
                 style="left: ${x}px; top: ${y}px;" title="${p.name} (${p.alive ? 'Vivant' : 'Mort'})">
                <span class="text-xs font-bold truncate w-full text-gray-200 px-1">${p.name}</span>
                <span class="text-[11px] ${p.alive ? 'text-green-400 font-semibold' : 'text-red-400 font-semibold'}">${p.alive ? 'Vivant' : 'Mort'}</span>
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
            ${!p.alive ? `<div class="text-xs text-gray-400">Dernier vote : ${p.has_vote ? 'Disponible' : 'Utilisé'}</div>` : ''}
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
                        <option value="majordome" ${p.suspicion === 'majordome' ? 'selected' : ''}>Majordome (Villageois - Outsider)</option>
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


// ================= BANDEAU D'ANNONCE & EFFET VISIBLE =================
let announcementTimer = null;

function setAnnouncement(text) {
    const announcementEl = document.getElementById('game-announcement');
    if (!announcementEl) return;

    // 1. Mettre à jour le texte
    announcementEl.innerText = `Annonce : ${text}`;

    // 2. Détecter si c'est un état d'attente / chargement
    const lowerText = text.toLowerCase();
    const isWaitingState = lowerText.includes("attente") || 
                           lowerText.includes("cours") || 
                           lowerText.includes("patienter") || 
                           lowerText.includes("réflexion") ||
                           lowerText.includes("endort");

    // Nettoyer un éventuel timer précédent
    if (announcementTimer) {
        clearTimeout(announcementTimer);
        announcementTimer = null;
    }

    // 3. Appliquer l'effet visuel sans toucher au positionnement
    if (isWaitingState) {
        // Effet lumineux pulsé (sans bounce pour ne pas décaler l'affichage)
        announcementEl.className = "bg-clock-accent border border-yellow-500 px-4 py-1.5 rounded-lg text-sm text-yellow-300 truncate italic max-w-md text-center font-bold animate-pulse shadow-[0_0_12px_rgba(234,179,8,0.5)] transition-all duration-300";

        // Retirer l'effet au bout de 3 secondes
        announcementTimer = setTimeout(() => {
            announcementEl.className = "bg-clock-accent border border-clock-border px-4 py-1.5 rounded-lg text-sm text-clock-gold truncate italic max-w-md text-center transition-all duration-300";
        }, 3000);

    } else {
        // Style classique d'origine
        announcementEl.className = "bg-clock-accent border border-clock-border px-4 py-1.5 rounded-lg text-sm text-clock-gold truncate italic max-w-md text-center transition-all duration-300";
    }
}

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
        
        const panel = document.getElementById('dynamic-action-panel');
        panel.innerHTML = `<div class="text-green-400 text-xs italic text-center py-2">✓ Proposition de discussion privée transmise. Ouverture du salon.</div>`;
    }
}

let currentWhisperAgent = null;

function showAgentWhisperModal(agentId) {
    currentWhisperAgent = agentId;
    const modal = document.getElementById('modal-agent-whisper');
    const textEl = document.getElementById('agent-whisper-text');
    const actionsEl = modal.querySelector('.flex');

    if (textEl) {
        textEl.innerText = `${agentId} souhaite s'entretenir discrètement avec vous dans l'ombre.`;
    }

    if (actionsEl) {
        actionsEl.innerHTML = `
            <button onclick="acceptAgentWhisper()" class="flex-1 bg-green-900/50 text-green-300 border border-green-700 py-2 rounded-xl text-xs font-semibold">Accepter</button>
            <button onclick="refuseAgentWhisper()" class="flex-1 bg-gray-800 text-gray-400 py-2 rounded-xl text-xs">Ignorer</button>
        `;
    }

    if (modal) modal.classList.remove('hidden');
}

function refuseAgentWhisper() {
    const modal = document.getElementById('modal-agent-whisper');
    const textEl = document.getElementById('agent-whisper-text');
    const actionsEl = modal.querySelector('.flex');

    if (textEl) {
        textEl.innerText = `Vous avez refusé l'entretien avec ${currentWhisperAgent || 'l\'agent'}. Que souhaitez-vous faire ?`;
    }

    if (actionsEl) {
        actionsEl.innerHTML = `
            <button onclick="closeAgentWhisperModalOnly()" class="flex-1 bg-clock-dark border border-clock-border text-gray-300 py-2 rounded-xl text-xs hover:border-clock-gold">Lancer une discussion</button>
            <button onclick="triggerVotePhaseFromModal()" class="flex-1 bg-clock-red text-white py-2 rounded-xl text-xs font-bold uppercase">Lancer le vote</button>
        `;
    }

    if (ws && ws.readyState === WebSocket.OPEN && currentWhisperAgent) {
        ws.send(JSON.stringify({
            action: "respond_whisper_invitation",
            payload: { target_agent_id: currentWhisperAgent, accepted: false }
        }));
    }
}

function closeAgentWhisperModalOnly() {
    const modal = document.getElementById('modal-agent-whisper');
    if (modal) modal.classList.add('hidden');
    currentWhisperAgent = null;
}

function triggerVotePhaseFromModal() {
    const modal = document.getElementById('modal-agent-whisper');
    if (modal) modal.classList.add('hidden');
    
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            action: "trigger_vote_phase",
            payload: {}
        }));
    }

    currentWhisperAgent = null;
}

function acceptAgentWhisper() {
    const modal = document.getElementById('modal-agent-whisper');
    if (modal) modal.classList.add('hidden');

    const agentId = currentWhisperAgent || "tobIAs";

    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            action: "respond_whisper_invitation",
            payload: { target_agent_id: agentId, accepted: true }
        }));
    }

    handleServerMessage({
        type: "chat",
        channel_id: "public",
        sender: "Grimoire",
        content: `Un entretien privé a débuté entre vous et ${agentId}.`
    });

    const channelId = "whisper_human_" + agentId;
    if (typeof handlePrivateChannelOpened === 'function') {
        handlePrivateChannelOpened(channelId, `Salon privé ouvert avec ${agentId}`, [agentId]);
    }

    currentWhisperAgent = null;
}

function showVoteResultModal(turnNumber, executedPlayer, votesArray) {
    const modal = document.getElementById('modal-vote-result');
    const headerEl = document.getElementById('vote-result-header');
    const listEl = document.getElementById('vote-result-list');
    const deathNoticeEl = document.getElementById('vote-death-notice');

    if (!modal || !headerEl || !listEl) return;

    const currentUsername = typeof playerId !== 'undefined' ? playerId : null;

    if (deathNoticeEl) {
        if (executedPlayer && executedPlayer === currentUsername) {
            deathNoticeEl.classList.remove('hidden');
        } else {
            deathNoticeEl.classList.add('hidden');
        }
    }

    if (typeof gameState !== 'undefined') {
        if (!gameState.vote_history) gameState.vote_history = [];

        votesArray.forEach(v => {
            gameState.vote_history.push({
                turn: turnNumber,
                voter: v.voter,
                target: v.target,
                executed: executedPlayer
            });
        });

        if (typeof renderVoteHistory === 'function') {
            renderVoteHistory();
        }
    }

    const executionText = executedPlayer ? `${executedPlayer} exécuté` : "pas d'exécution";
    headerEl.innerText = `JOUR ${turnNumber} - ${executionText}`;

    let html = '';
    if (!votesArray || votesArray.length === 0) {
        html = `<li class="text-gray-500 italic">Aucun vote enregistré.</li>`;
    } else {
        votesArray.forEach(v => {
            const targetText = v.target ? v.target : "vote blanc";
            html += `
                <li class="text-gray-300">
                    - <span class="font-semibold text-white">${v.voter}</span> : ${targetText}
                </li>
            `;
        });
    }
    listEl.innerHTML = html;

    modal.classList.remove('hidden');
}

function closeVoteResultModal() {
    const modal = document.getElementById('modal-vote-result');
    if (modal) modal.classList.add('hidden');
}

// Modale résultat de la nuit (mise à jour avec intégration dans l'historique de nuit)
function showNightResultModal(turnNumber, deadPlayerName) {
    const modal = document.getElementById('modal-night-result');
    const messageEl = document.getElementById('night-result-message');
    const deathNoticeEl = document.getElementById('night-death-notice');

    if (!modal || !messageEl) return;

    const currentUsername = typeof playerId !== 'undefined' ? playerId : null;
    let nightLogText = "";

    if (deadPlayerName) {
        if (deadPlayerName === currentUsername) {
            messageEl.innerHTML = `L'obscurité a frappé cette nuit...`;
            if (deathNoticeEl) deathNoticeEl.classList.remove('hidden');
        } else {
            messageEl.innerHTML = `Les ténèbres ont frappé...<br><br><span class="text-red-400 font-bold text-sm">${deadPlayerName}</span> est mort cette nuit.`;
            if (deathNoticeEl) deathNoticeEl.classList.add('hidden');
        }
        nightLogText = `${deadPlayerName} est mort cette nuit.`;
    } else {
        messageEl.innerHTML = `Les esprits ont protégé le village...<br><br><span class="text-green-400 font-bold text-sm">Personne n'est mort</span> cette nuit !`;
        if (deathNoticeEl) deathNoticeEl.classList.add('hidden');
        nightLogText = "Personne n'est mort cette nuit.";
    }

    // Enregistrer automatiquement le résultat de nuit dans l'historique global de nuit
    if (typeof gameState !== 'undefined') {
        if (!gameState.night_info_history) gameState.night_info_history = [];
        
        gameState.night_info_history.push({
            turn: turnNumber || gameState.day,
            type: "result",
            info: nightLogText
        });

        if (typeof renderNightInfoHistory === 'function') {
            renderNightInfoHistory();
        }
    }

    modal.classList.remove('hidden');
}

function closeNightResultModal() {
    const modal = document.getElementById('modal-night-result');
    if (modal) {
        modal.classList.add('hidden');
    }
}

// Modale d'information nocturne (spécifique au rôle)
function showNightInfoModal(turnNumber, infoText) {
    const modal = document.getElementById('modal-night-info');
    const contentEl = document.getElementById('night-info-content');

    if (!modal || !contentEl) return;

    contentEl.innerHTML = `
        <span class="text-clock-gold font-bold block mb-2">Tour ${turnNumber}</span>
        <p class="text-gray-200">${infoText}</p>
    `;

    // Enregistrer l'information de rôle dans l'historique global de nuit
    if (typeof gameState !== 'undefined') {
        if (!gameState.night_info_history) gameState.night_info_history = [];
        
        gameState.night_info_history.push({
            turn: turnNumber,
            type: "role_info",
            info: infoText
        });

        if (typeof renderNightInfoHistory === 'function') {
            renderNightInfoHistory();
        }
    }

    modal.classList.remove('hidden');
}

function closeNightInfoModal() {
    const modal = document.getElementById('modal-night-info');
    if (modal) modal.classList.add('hidden');
}

// Assurer la visibilité globale pour les onclick du HTML
window.closeVoteResultModal = closeVoteResultModal;
window.closeNightResultModal = closeNightResultModal;
window.closeNightInfoModal = closeNightInfoModal;


function triggerGameOver(winner, details) {
    document.getElementById('gameover-title').innerText = `Victoire des ${winner}`;
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

// ================= GESTION DU GRIMOIRE =================
function openGrimoireModal() {
    const modal = document.getElementById('modal-grimoire');
    if (modal) modal.classList.remove('hidden');
}

function closeGrimoireModal() {
    const modal = document.getElementById('modal-grimoire');
    if (modal) modal.classList.add('hidden');
}

function switchGrimoireTab(tabName) {
    const rolesSection = document.getElementById('grimoire-tab-roles');
    const rulesSection = document.getElementById('grimoire-tab-rules');
    const btnRoles = document.getElementById('grimoire-tab-btn-roles');
    const btnRules = document.getElementById('grimoire-tab-btn-rules');

    if (tabName === 'roles') {
        rolesSection.classList.remove('hidden');
        rulesSection.classList.add('hidden');
        btnRoles.className = "flex-1 py-2 font-bold text-clock-gold border-b-2 border-clock-gold transition";
        btnRules.className = "flex-1 py-2 font-medium text-gray-400 hover:text-gray-200 transition";
    } else {
        rolesSection.classList.add('hidden');
        rulesSection.classList.remove('hidden');
        btnRules.className = "flex-1 py-2 font-bold text-clock-gold border-b-2 border-clock-gold transition";
        btnRoles.className = "flex-1 py-2 font-medium text-gray-400 hover:text-gray-200 transition";
    }
}

// Visibilité globale pour le HTML
window.openGrimoireModal = openGrimoireModal;
window.closeGrimoireModal = closeGrimoireModal;
window.switchGrimoireTab = switchGrimoireTab;

// ================= FERMETURE DES MODALES AU CLIC SUR LE FOND (BACKDROP) =================
document.addEventListener('click', function(event) {
    if (event.target.id === 'screen-welcome' || event.target.closest('#screen-welcome')) {
        return;
    }

    if (event.target.classList.contains('fixed') && event.target.classList.contains('inset-0')) {
        event.target.classList.add('hidden');
    }
});