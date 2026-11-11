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
    // Active/désactive le bouton de validation de l'encadré d'action.
    refreshActionSelection();
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
        case "action_request":
            handleActionRequest(data); // Remplit l'encadré d'action de la sidebar droite
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

    // Une action demandée pour une autre phase n'a plus lieu d'être.
    if (pendingAction && newState.phase && newState.phase.toLowerCase() !== pendingAction.kind) {
        pendingAction = null;
        actionSelection = [];
    }
    
    // 1. Mise à jour du numéro du tour
    const dayEl = document.getElementById('game-day');
    if (dayEl) dayEl.innerText = gameState.day;

    // 2. Gestion de la phase, de son icône et de ses classes de couleur
    const phaseElement = document.getElementById('game-phase');
    const phaseIconContainer = document.getElementById('phase-icon-container');

    // Dictionnaire des configurations visuelles par phase (clés unifiées en minuscules)
    const phaseConfig = {
        'nuit': {
            label: 'Nuit',
            textColor: 'text-[var(--night)]',
            svg: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-moon size-5"><path d="M20.985 12.486a9 9 0 1 1-9.473-9.472c.405-.022.617.46.402.803a6 6 0 0 0 8.268 8.268c.344-.215.825-.004.803.401"></path></svg>`
        },
        'vote': {
            label: 'Vote',
            textColor: 'text-[var(--blood)]',
            svg: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-scale size-5"><path d="M12 3v18"></path><path d="m19 8 3 8a5 5 0 0 1-6 0zV7"></path><path d="M3 7h1a17 17 0 0 0 8-2 17 17 0 0 0 8 2h1"></path><path d="m5 8 3 8a5 5 0 0 1-6 0zV7"></path><path d="M7 21h10"></path></svg>`
        },
        'discussion': {
            label: 'Jour',
            textColor: 'text-[var(--day)]',
            svg: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-sun size-5"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2"></path><path d="M12 20v2"></path><path d="m4.93 4.93 1.41 1.41"></path><path d="m17.66 17.66 1.41 1.41"></path><path d="M2 12h2"></path><path d="M20 12h2"></path><path d="m6.34 17.66-1.41 1.41"></path><path d="m19.07 4.93-1.41 1.41"></path></svg>`
        }
    };

    // Récupération de la configuration active (par défaut 'nuit' si inconnu)
    const currentPhaseKey = gameState.phase ? gameState.phase.toLowerCase() : 'nuit';
    const config = phaseConfig[currentPhaseKey] || phaseConfig['nuit'];

    // Application du texte et des classes de couleur
    if (phaseElement) {
        phaseElement.innerText = config.label;
        phaseElement.className = `font-display text-lg leading-none uppercase ${config.textColor}`;
    }

    if (phaseIconContainer) {
        // Application propre de la bordure grise du thème et de la couleur textuelle pour le SVG
        phaseIconContainer.className = `panel flex size-9 items-center justify-center rounded-full border border-border bg-card shrink-0 ${config.textColor}`;
        phaseIconContainer.innerHTML = config.svg;
    }

    // 3. Mise à jour du nombre de vivants
    const aliveEl = document.getElementById('alive-count');
    if (aliveEl) aliveEl.innerText = gameState.aliveCount;

    // Annonces contextuelles
    if (newState.announcement && typeof setAnnouncement === 'function') {
        setAnnouncement(newState.announcement);
    } else if (newState.phase === 'nuit' && typeof setAnnouncement === 'function') {
        setAnnouncement("La nuit tombe... Les pouvoirs sont en cours d'invocation.");
    } else if (newState.phase === 'vote' && typeof setAnnouncement === 'function') {
        setAnnouncement("Phase de vote : réflexion et choix des joueurs en cours...");
    }

    // Attention : si renderRoundTable() recrée le HTML de zéro, il faut qu'il utilise le gameState à jour,
    // sinon commente cette ligne si la table ronde est déjà gérée par le code ci-dessus.
    // renderRoundTable(); 
    
    if (typeof renderPlayersList === 'function') renderPlayersList();
    if (typeof renderActionPanel === 'function') renderActionPanel();
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

// ================= ENCADRÉ DYNAMIQUE DES ACTIONS DE PHASE =================
// Le serveur envoie ce qu'il faut afficher via un message "action_request" :
//   { type: "action_request", kind: "discussion" | "vote" | "nuit",
//     candidates: [playerId, ...], max_targets: 1 | 2,
//     min_targets?: n, role?: "imp" | "Diablotin" | ... }
// Seul le texte (titre, consigne, bouton) est défini côté client, selon la phase et le rôle.

let pendingAction = null;   // { kind, candidates, maxTargets, minTargets, role } ou null
let actionSelection = [];   // ids sélectionnés
const NO_TARGET = "__none__"; // option "Personne" du vote

const ACTION_ICONS = {
    discussion: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="size-4"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M22 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>`,
    vote: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="size-4"><path d="M12 3v18"></path><path d="m19 8 3 8a5 5 0 0 1-6 0zV7"></path><path d="M3 7h1a17 17 0 0 0 8-2 17 17 0 0 0 8 2h1"></path><path d="m5 8 3 8a5 5 0 0 1-6 0zV7"></path><path d="M7 21h10"></path></svg>`,
    nuit: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="size-4"><path d="M20.985 12.486a9 9 0 1 1-9.473-9.472c.405-.022.617.46.402.803a6 6 0 0 0 8.268 8.268c.344-.215.825-.004.803.401"></path></svg>`,
    check: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="option-check size-4"><path d="M20 6 9 17l-5-5"></path></svg>`
};

// Textes de la nuit selon le rôle (clé = name_EN du catalogue backend)
const NIGHT_ROLE_TEXTS = {
    imp:       { label: "Diablotin",    prompt: "Qui sera votre victime cette nuit ?" },
    poisoner:  { label: "Empoisonneur", prompt: "Qui empoisonnerez-vous jusqu'à la fin de la prochaine journée ?" },
    monk:      { label: "Moine",        prompt: "Qui protégerez-vous des griffes du Diablotin cette nuit ?" },
    psychic:   { label: "Voyante",      prompt: "Quels sont les deux joueurs que vous souhaitez sonder ?" },
    butler:    { label: "Majordome",    prompt: "Qui choisissez-vous comme Maître ? Vous ne pourrez voter que s'il vote aussi." }
};

// Accepte indifféremment "imp", "Diablotin", "diablotin"...
function resolveRoleKey(role) {
    if (!role) return null;
    const norm = s => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
    const wanted = norm(role);
    return Object.keys(NIGHT_ROLE_TEXTS).find(
        key => key === wanted || norm(NIGHT_ROLE_TEXTS[key].label) === wanted
    ) || null;
}

function getActionTexts(action) {
    if (action.kind === "discussion") {
        return {
            title: "Conversation privée",
            prompt: "Avec qui souhaitez-vous vous entretenir en privé ?",
            submit: "Lancer la discussion privée"
        };
    }
    if (action.kind === "vote") {
        return {
            title: "Vote",
            prompt: "Qui doit monter sur l'échafaud ?",
            submit: "Sceller mon vote"
        };
    }
    const roleKey = resolveRoleKey(action.role || gameState.roleInfo?.name);
    const roleTexts = roleKey ? NIGHT_ROLE_TEXTS[roleKey] : null;
    return {
        title: roleTexts ? `Pouvoir : ${roleTexts.label}` : "Action de nuit",
        prompt: roleTexts ? roleTexts.prompt : "Choisissez la cible de votre pouvoir.",
        submit: "Transmettre au Maître du Jeu"
    };
}

function getPlayerName(id) {
    const player = (gameState.players || []).find(p => p.id === id);
    return player ? player.name : id;
}

function handleActionRequest(data) {
    const kind = data.kind;
    if (!["discussion", "vote", "nuit"].includes(kind)) {
        console.warn("action_request : kind inconnu", data);
        return;
    }
    // Le vote est toujours à choix unique.
    const maxTargets = kind === "vote" ? 1 : Math.max(1, data.max_targets || 1);
    // Nuit : par défaut il faut choisir exactement le nombre de cibles du pouvoir.
    // Discussion / vote : une seule sélection suffit.
    const defaultMin = kind === "nuit" ? maxTargets : 1;

    let candidates = data.candidates || [];
    // Garde-fous, même si le serveur envoie une liste trop large :
    //  - discussion : on peut parler à tout le monde (morts compris), sauf à soi-même ;
    //  - vote : on ne peut voter ni contre soi-même, ni contre un mort.
    if (kind === "discussion") {
        candidates = candidates.filter(id => id !== playerId);
    } else if (kind === "vote") {
        candidates = candidates.filter(id => {
            if (id === playerId) return false;
            const player = (gameState.players || []).find(p => p.id === id);
            return !player || player.alive !== false;
        });
    }

    pendingAction = {
        kind,
        candidates,
        maxTargets,
        minTargets: Math.min(maxTargets, data.min_targets || defaultMin),
        role: data.role || null
    };
    actionSelection = [];
    renderActionPanel();
}

function clearPendingAction() {
    pendingAction = null;
    actionSelection = [];
    renderActionPanel();
}

function renderActionPanel() {
    const zone = document.getElementById('action-zone');
    const panel = document.getElementById('dynamic-action-panel');
    if (!zone || !panel) return;

    // Aucune action en cours : l'encadré disparaît complètement.
    if (!pendingAction) {
        zone.classList.add('hidden');
        panel.innerHTML = '';
        return;
    }

    const { kind, candidates, maxTargets } = pendingAction;
    const texts = getActionTexts(pendingAction);

    const options = candidates.map(id => ({
        id,
        label: escapeHtml(getPlayerName(id)) + (id === playerId ? ' <span class="opacity-60">(vous)</span>' : '')
    }));
    if (kind === "vote") {
        options.push({ id: NO_TARGET, label: '<span class="italic">Personne</span>' });
    }

    panel.dataset.phase = kind;
    panel.innerHTML = `
        <h3 class="action-title font-display text-lg flex items-center gap-2 mb-2 shrink-0">
            ${ACTION_ICONS[kind]}
            <span>${escapeHtml(texts.title)}</span>
        </h3>
        <p class="font-serif text-sm italic text-[var(--foreground)] opacity-90 mb-2 shrink-0">${escapeHtml(texts.prompt)}</p>
        ${maxTargets > 1 ? `<p id="action-counter" class="text-xs opacity-60 mb-1 shrink-0"></p>` : ''}
        <div class="flex flex-col gap-1 min-h-0 overflow-y-auto pr-1">
            ${options.map(o => `
                <button type="button" class="option-btn" data-id="${escapeHtml(o.id)}" aria-pressed="false">
                    <span class="truncate">${o.label}</span>
                    ${ACTION_ICONS.check}
                </button>
            `).join('')}
        </div>
        <button type="button" id="action-submit" onclick="submitPendingAction()"
            class="action-submit mt-3 w-full shrink-0 rounded-md py-2 font-serif text-base font-semibold tracking-wide">
            ${escapeHtml(texts.submit)}
        </button>
    `;

    panel.querySelectorAll('.option-btn').forEach(btn => {
        btn.addEventListener('click', () => toggleActionTarget(btn.dataset.id));
    });

    zone.classList.remove('hidden');
    refreshActionSelection();
}

function toggleActionTarget(id) {
    if (!pendingAction) return;
    const max = pendingAction.maxTargets;

    if (actionSelection.includes(id)) {
        actionSelection = actionSelection.filter(t => t !== id);
    } else if (max === 1) {
        actionSelection = [id];
    } else if (actionSelection.length < max) {
        actionSelection = [...actionSelection, id];
    }
    refreshActionSelection();
}

// Met à jour l'état visuel sans reconstruire le HTML (préserve le scroll de la liste).
function refreshActionSelection() {
    if (!pendingAction) return;
    const { maxTargets, minTargets } = pendingAction;
    const isFull = maxTargets > 1 && actionSelection.length >= maxTargets;

    document.querySelectorAll('#dynamic-action-panel .option-btn').forEach(btn => {
        const selected = actionSelection.includes(btn.dataset.id);
        btn.setAttribute('aria-pressed', String(selected));
        // En multi-sélection, une fois le maximum atteint, on grise les autres options.
        btn.disabled = isFull && !selected;
    });

    const counter = document.getElementById('action-counter');
    if (counter) {
        counter.innerText = `${actionSelection.length}/${maxTargets} joueur(s) sélectionné(s)`;
    }

    const submit = document.getElementById('action-submit');
    if (submit) {
        const connected = ws && ws.readyState === WebSocket.OPEN;
        submit.disabled = actionSelection.length < minTargets || !connected;
    }
}

function submitPendingAction() {
    if (!pendingAction || actionSelection.length < pendingAction.minTargets) return;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        appendSystemMessage("Connexion perdue : votre choix n'a pas été envoyé.");
        return;
    }

    const targets = [...actionSelection];
    const names = targets.map(getPlayerName).join(', ');

    if (pendingAction.kind === "discussion") {
        ws.send(JSON.stringify({ action: "request_whisper", payload: { targets } }));
        appendSystemMessage(`Proposition de discussion privée envoyée à : ${names}.`);
    } else if (pendingAction.kind === "vote") {
        const targetId = targets[0] === NO_TARGET ? null : targets[0];
        ws.send(JSON.stringify({ action: "submit_vote", payload: { target_id: targetId } }));
        appendSystemMessage(`Vote enregistré pour : ${targetId ? getPlayerName(targetId) : 'Personne'}.`);
    } else if (pendingAction.kind === "nuit") {
        ws.send(JSON.stringify({ action: "submit_night_action", payload: { targets } }));
        appendSystemMessage(`Action nocturne confiée au Maître du Jeu : ${names}.`);
    }

    clearPendingAction();
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
function setAnnouncement(text) {
    const announcementEl = document.getElementById('game-announcement');
    if (!announcementEl) return;

    // 1. Mettre à jour le texte
    announcementEl.innerText = `${text}`;

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

function escapeHtml(text) {
    if (!text) return '';
    return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
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