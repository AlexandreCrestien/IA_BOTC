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
        showDisconnectedModal();
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
        badge.className = "px-2.5 py-0.5 rounded-full text-xs font-semibold bg-green-900/50 text-green-400 border border-green-700 whitespace-nowrap";
        badge.innerText = "Connecté";
    } else {
        badge.className = "px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-900/50 text-red-400 border border-red-700 whitespace-nowrap";
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
            showAgentWhisperModal(data.agent_id, data.agent_name, data.message);
            break;
        case "game_over":
            triggerGameOver(data.winner, data.details);
            break;
        case "private_channel_opened":
            // members inclut le joueur humain : on ne garde que ses interlocuteurs pour le titre de l'onglet
            handlePrivateChannelOpened(data.channel_id, data.text, (data.members || []).filter(m => m !== playerId));
            break;
        case "vote_result":
            showVoteResultModal(data.turn, data.executed, data.votes); // historique (+ modale si le joueur est exécuté)
            showVoteResultInPanel(data.executed, data.votes || []);
            break;
        case "night_result":
            showNightResultModal(data.turn, data.dead_player); // data.turn et data.dead_player
            break;
        case "night_info":
            // allies (facultatif) : révélation des alliés du camp du mal, la première nuit : [{ id, role }]
            if (Array.isArray(data.allies)) revealAllies(data.allies);
            if (pendingAction?.kind === "nuit" && pendingAction.stage === "waiting") {
                // Réponse à l'action de nuit du joueur : affichée dans l'encadré plutôt qu'en modale
                recordNightInfo(data.turn, data.info);
                showNightResultInPanel(data.info);
            } else {
                showNightInfoModal(data.turn, data.info); // Information spécifique reçue la nuit selon le rôle
            }
            break;
        case "night_action_ack":
            // Simple confirmation de l'action de nuit (rôles sans information en retour)
            showNightResultInPanel(data.text || "Le Maître du Jeu a bien reçu votre choix.");
            break;
        case "error":
            appendSystemMessage(data.data || "Erreur du serveur.");
            // L'action a été refusée : le joueur peut corriger son choix
            if (pendingAction?.stage === "waiting") {
                pendingAction.stage = "choosing";
                renderActionPanel();
            }
            break;
        case "action_request":
            handleActionRequest(data); // Remplit l'encadré d'action de la sidebar droite
            break;
        default:
            console.log("Message non géré :", data);
    }
}

// ================= CHAT & ONGLETS LATÉRAUX =================
// ================= NOUVEAUX MESSAGES SUR LA PLACE PUBLIQUE =================
let activeLeftTab = 'chat';
let hasUnreadPublic = false;

// Le joueur voit la place publique s'il est sur l'onglet Chat ET sur le canal public.
function isViewingPublic() {
    return activeLeftTab === 'chat' && gameState.currentChannel === 'public';
}

// Badge sur "Place publique" si le joueur est dans un autre canal,
// badge à côté de "Chat" s'il est sur un autre onglet (les deux peuvent coexister).
function refreshUnreadBadges() {
    if (isViewingPublic()) hasUnreadPublic = false;
    const onPublicBtn = document.getElementById('unread-public');
    const onChatTab = document.getElementById('unread-chat-tab');
    if (onPublicBtn) onPublicBtn.hidden = !(hasUnreadPublic && gameState.currentChannel !== 'public');
    if (onChatTab) onChatTab.hidden = !(hasUnreadPublic && activeLeftTab !== 'chat');
}

function switchLeftTab(tabName) {
    activeLeftTab = tabName;
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
    refreshUnreadBadges();
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

    // Nouveau message public (hors messages du joueur lui-même) pendant qu'il regarde ailleurs
    if (channelId === 'public' && sender !== playerId && !isViewingPublic()) {
        hasUnreadPublic = true;
        refreshUnreadBadges();
    }
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
    refreshUnreadBadges();
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
    // (une action déjà envoyée reste affichée en attente de sa réponse)
    if (pendingAction && pendingAction.stage === "choosing" && newState.phase && newState.phase.toLowerCase() !== pendingAction.kind) {
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
        phaseIconContainer.className = `panel flex size-8 items-center justify-center rounded-full border border-border bg-card shrink-0 ${config.textColor}`;
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

    // Lueur d'ambiance de la zone centrale selon la phase
    const centerStage = document.getElementById('center-stage');
    if (centerStage && gameState.phase) centerStage.dataset.phase = gameState.phase.toLowerCase();

    renderRoundTable();
    
    if (typeof renderPlayersList === 'function') renderPlayersList();
    if (typeof renderActionPanel === 'function') renderActionPanel();
}

// Place les joueurs autour de la table (le Grimoire central est statique dans le HTML).
function renderRoundTable() {
    const seats = document.getElementById('round-table-seats');
    if (!seats) return;
    const players = gameState.players || [];

    if (players.length === 0) {
        seats.innerHTML = `
            <p class="absolute inset-x-0 bottom-[3%] text-center text-sm italic opacity-60">En attente des joueurs...</p>
        `;
        return;
    }

    seats.innerHTML = players.map((p, index) => {
        // Positions en % du carré : la table reste correcte quelle que soit sa taille.
        const angle = (index / players.length) * 2 * Math.PI - Math.PI / 2;
        // Rayon 39 % = bord extérieur de la table (inset-[11%]) : le centre de la bulle est posé sur le cercle.
        const left = 50 + 39 * Math.cos(angle);
        const top = 50 + 39 * Math.sin(angle);
        const isMe = p.id === playerId;
        const isAlive = p.alive !== false;
        const initial = escapeHtml((p.name || '?').trim().charAt(0).toUpperCase());
        const label = escapeHtml(p.name) + (isMe ? ' (vous)' : '') + (isAlive ? '' : ' (mort)');

        return `
            <!-- Le siège est centré sur la bulle ; le nom est accroché en dessous sans décaler la bulle. -->
            <div class="seat ${isMe ? 'is-me' : ''} ${isAlive ? '' : 'is-dead'} pointer-events-auto absolute -translate-x-1/2 -translate-y-1/2"
                 style="left: ${left}%; top: ${top}%;" title="${label}">
                <div class="seat-avatar flex size-12 sm:size-14 items-center justify-center rounded-full font-display text-lg">${initial}</div>
                <span class="seat-name absolute left-1/2 top-full mt-1 w-32 sm:w-36 -translate-x-1/2 line-clamp-2 text-center leading-tight px-1 text-xs sm:text-sm font-medium">${label}</span>
            </div>
        `;
    }).join('');
}

// Soupçons notés par le joueur, stockés à part pour survivre aux "game_state" du serveur.
const suspicions = {}; // playerId -> valeur du select

// Options de la liste "Je soupçonne…". `role` = nom du rôle (FR) pour l'exclusion du rôle du joueur.
const SUSPICION_OPTIONS = {
    camps: [
        { value: "Townsfolk", label: "Villageois (gentil)" },
        { value: "Demon",     label: "Démon (méchant)" }
    ],
    roles: [
        { value: "diablotin",    label: "Diablotin (Démon)",                 role: "Diablotin",    evil: true },
        { value: "empoisonneur", label: "Empoisonneur (Démon - Sbire)",      role: "Empoisonneur", evil: true },
        { value: "voyante",      label: "Voyante (Villageois)",              role: "Voyante" },
        { value: "moine",        label: "Moine (Villageois)",                role: "Moine" },
        { value: "detective",    label: "Détective (Villageois)",            role: "Détective" },
        { value: "majordome",    label: "Majordome (Villageois - Outsider)", role: "Majordome" }
    ]
};

function normalizeText(s) {
    return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
}

// Allié connu (rôles maléfiques uniquement) : { id, role } ou undefined
function getAlly(id) {
    return (gameState.allies || []).find(a => a.id === id);
}

// Rôle maléfique du joueur humain (Diablotin ou Empoisonneur)
function isEvilRole() {
    return ["imp", "poisoner"].includes(resolveRoleKey(gameState.roleInfo?.name));
}

// Le joueur est du camp du mal et ses alliés lui ont été révélés (première nuit) :
// il sait alors que tous les autres joueurs sont du camp du bien.
function knowsEvilTeam() {
    return isEvilRole() && Array.isArray(gameState.allies);
}

// Camp du mal, avant la révélation : les soupçons sont verrouillés.
function awaitsAllyReveal() {
    return isEvilRole() && !Array.isArray(gameState.allies);
}

function revealAllies(allies) {
    gameState.allies = allies;
    renderPlayersList();
}

function renderSuspicionSelect(p) {
    // On retire le rôle du joueur humain : il sait qu'aucun autre joueur ne l'a.
    const myRole = normalizeText(gameState.roleInfo?.name);
    const current = suspicions[p.id] || "";
    const opt = o => `<option value="${o.value}" ${current === o.value ? 'selected' : ''}>${o.label}</option>`;
    const label = `aria-label="Rôle soupçonné pour ${escapeHtml(p.name)}"`;

    // Camp du mal, alliés pas encore révélés : liste désactivée jusqu'à la première nuit.
    if (awaitsAllyReveal()) {
        return `
            <select class="suspicion-select" disabled ${label} title="Vos alliés vous seront révélés lors de la première nuit.">
                <option selected>Révélé lors de la première nuit…</option>
            </select>
        `;
    }

    // Camp du mal : les non-alliés sont forcément du bien → seulement les rôles du bien, pas de camps.
    if (knowsEvilTeam()) {
        const goodRoles = SUSPICION_OPTIONS.roles.filter(o => !o.evil);
        return `
            <select class="suspicion-select" data-player-id="${escapeHtml(p.id)}" ${label}>
                <option value="" ${current === '' ? 'selected' : ''}>Je soupçonne que ce joueur est…</option>
                <optgroup label="Villageois - rôle inconnu">${goodRoles.map(opt).join('')}</optgroup>
            </select>
        `;
    }

    const roles = SUSPICION_OPTIONS.roles.filter(o => normalizeText(o.role) !== myRole);
    return `
        <select class="suspicion-select" data-player-id="${escapeHtml(p.id)}" ${label}>
            <option value="" ${current === '' ? 'selected' : ''}>Je soupçonne que ce joueur est…</option>
            <optgroup label="Camps">${SUSPICION_OPTIONS.camps.map(opt).join('')}</optgroup>
            <optgroup label="Rôles">${roles.map(opt).join('')}</optgroup>
        </select>
    `;
}

// Remplace la liste de soupçons sur la carte d'un allié : son rôle est connu.
function renderAllyTag(ally) {
    const roleKey = resolveRoleKey(ally.role);
    const roleLabel = roleKey ? NIGHT_ROLE_TEXTS[roleKey].label : (ally.role || "rôle inconnu");
    return `
        <div class="ally-tag flex items-center gap-2 rounded-md px-2 py-1 text-xs">
            <span>Votre allié · <strong class="font-semibold">${escapeHtml(roleLabel)}</strong></span>
        </div>
    `;
}

function renderPlayersList() {
    const list = document.getElementById('players-notes-list');
    if (!list) return;
    const allPlayers = gameState.players || [];

    // Compteur sur tout le village (joueur humain compris)
    const counter = document.getElementById('players-count');
    if (counter) {
        const alive = allPlayers.filter(p => p.alive !== false).length;
        counter.innerText = allPlayers.length ? `${alive} vivant·e·s · ${allPlayers.length - alive} mort·e·s` : '';
    }

    // Le joueur humain n'a pas d'encadré ; les alliés connus sont affichés en premier.
    const others = allPlayers
        .filter(p => p.id !== playerId)
        .sort((a, b) => Number(!!getAlly(b.id)) - Number(!!getAlly(a.id)));

    if (!others.length) {
        list.innerHTML = '<div class="text-sm italic opacity-60">Aucun convive pour le moment.</div>';
        return;
    }

    list.innerHTML = others.map(p => {
        const isAlive = p.alive !== false;
        const initial = escapeHtml((p.name || '?').trim().charAt(0).toUpperCase());
        const ally = getAlly(p.id);
        return `
            <article class="player-card ${isAlive ? '' : 'is-dead'} ${ally ? 'is-ally' : ''} rounded-lg px-3 py-3 flex items-center gap-3 shrink-0">
                <!-- Avatar : initiale en attendant les images -->
                <div class="player-avatar size-10 shrink-0 rounded-full flex items-center justify-center font-display text-base">${initial}</div>
                <div class="min-w-0 flex-1 flex flex-col gap-2">
                    <!-- Ligne 1 : nom + statut -->
                    <div class="flex items-center gap-2 min-w-0">
                        <span class="player-name font-sans text-sm font-semibold leading-tight truncate ${isAlive ? '' : 'line-through'}">${escapeHtml(p.name)}</span>
                        ${isAlive
                            ? `<span class="status-alive ml-auto shrink-0 flex items-center gap-1 text-xs">Vivant</span>`
                            : `<span class="status-dead ml-auto shrink-0 flex items-center gap-1 text-xs" title="Dernier vote : ${p.has_vote ? 'disponible' : 'utilisé'}"> Mort<span class="opacity-70">· vote ${p.has_vote ? 'dispo' : 'utilisé'}</span></span>`}
                    </div>
                    <!-- Ligne 2 : soupçon (ou allié connu) -->
                    ${ally ? renderAllyTag(ally) : renderSuspicionSelect(p)}
                </div>
            </article>
        `;
    }).join('');

    list.querySelectorAll('.suspicion-select').forEach(select => {
        select.addEventListener('change', () => updateSuspicion(select.dataset.playerId, select.value));
    });
}

// ================= ENCADRÉ DYNAMIQUE DES ACTIONS DE PHASE =================
// Le serveur envoie ce qu'il faut afficher via un message "action_request" :
//   { type: "action_request", kind: "discussion" | "vote" | "nuit",
//     candidates: [playerId, ...], max_targets: 1 | 2,
//     min_targets?: n, role?: "imp" | "Diablotin" | ... }
// Seul le texte (titre, consigne, bouton) est défini côté client, selon la phase et le rôle.

let pendingAction = null;   // { kind, candidates, maxTargets, minTargets, role, stage: "choosing" | "waiting" } ou null
let actionSelection = [];   // ids sélectionnés
const NO_TARGET = "__none__"; // option "Personne" du vote

// Résultat affiché dans l'encadré (vote ou réponse de nuit). Il reste affiché jusqu'à ce que
// le joueur le ferme ; une nouvelle action ne peut le remplacer qu'après RESULT_MIN_DISPLAY_MS.
let actionResult = null;    // { kind: "vote" | "nuit", shownAt, ...données }
let deferredActionRequest = null;
let deferredActionTimer = null;
const RESULT_MIN_DISPLAY_MS = 12000;

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
    // Un résultat est affiché depuis trop peu de temps : on laisse le joueur le lire.
    if (actionResult) {
        const remaining = RESULT_MIN_DISPLAY_MS - (Date.now() - actionResult.shownAt);
        if (remaining > 0) {
            deferredActionRequest = data;
            clearTimeout(deferredActionTimer);
            deferredActionTimer = setTimeout(applyDeferredActionRequest, remaining);
            return;
        }
        actionResult = null;
    }

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
        role: data.role || null,
        stage: "choosing"
    };
    actionSelection = [];
    renderActionPanel();
}

function applyDeferredActionRequest() {
    clearTimeout(deferredActionTimer);
    const data = deferredActionRequest;
    deferredActionRequest = null;
    if (!data) return;
    actionResult = null;
    handleActionRequest(data);
}

// Bouton "Fermer" d'un résultat : affiche tout de suite l'action suivante si elle attendait.
function closeActionResult() {
    actionResult = null;
    if (deferredActionRequest) applyDeferredActionRequest();
    else renderActionPanel();
}

function showVoteResultInPanel(executedId, votes) {
    if (pendingAction?.kind === "vote") pendingAction = null;
    actionSelection = [];
    actionResult = { kind: "vote", executedId, votes, shownAt: Date.now() };
    renderActionPanel();
}

function showNightResultInPanel(text) {
    if (pendingAction?.kind === "nuit") pendingAction = null;
    actionSelection = [];
    actionResult = { kind: "nuit", text, shownAt: Date.now() };
    renderActionPanel();
}

// Même enregistrement que showNightInfoModal, sans ouvrir la modale.
function recordNightInfo(turn, info) {
    if (!gameState.night_info_history) gameState.night_info_history = [];
    gameState.night_info_history.push({ turn, type: "role_info", info });
    if (typeof renderNightInfoHistory === 'function') renderNightInfoHistory();
}

const RESULT_CLOSE_BUTTON = `
    <button type="button" onclick="closeActionResult()"
        class="mt-3 w-full shrink-0 flex items-center justify-center gap-2 rounded-md py-1.5 text-sm opacity-70 hover:opacity-100 transition-opacity">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="size-4"><path d="M18 6 6 18"></path><path d="m6 6 12 12"></path></svg>
        Fermer
    </button>`;

function renderVoteResult(result) {
    const isDead = id => (gameState.players || []).find(p => p.id === id)?.alive === false;

    // Verdict : seul le total de voix de la personne exécutée est indiqué.
    let verdict;
    if (result.executedId) {
        const n = result.votes.filter(v => v.target === result.executedId).length;
        verdict = `<p class="result-verdict mb-3 rounded-md px-3 py-2 text-sm">
            <span class="font-semibold">${escapeHtml(getPlayerName(result.executedId))}</span>
            est exécuté·e avec <span class="font-semibold text-gold">${n} voix</span>.
        </p>`;
    } else {
        verdict = `<p class="mb-3 text-sm opacity-75">Aucune majorité : personne n'est exécuté aujourd'hui.</p>`;
    }

    // Un bulletin par votant : "votant → cible" (ou "Personne").
    // Un votant déjà mort a utilisé son vote fantôme : on le signale.
    const ballots = result.votes.map(v => {
        const target = v.target
            ? `<span class="font-semibold ${v.target === result.executedId ? 'text-blood-bright' : 'text-gold'}">${escapeHtml(getPlayerName(v.target))}</span>`
            : `<span class="italic opacity-60">Personne</span>`;
        return `
            <li class="ballot flex items-center gap-2 rounded-md px-3 py-1.5 text-sm">
                <span class="truncate">${escapeHtml(getPlayerName(v.voter))}${isDead(v.voter) ? ' <span class="text-xs opacity-60">(vote fantôme)</span>' : ''}</span>
                <span class="truncate ml-auto text-right">${target}</span>
            </li>
        `;
    }).join('');

    return `
        <h3 class="action-title font-display text-lg flex items-center gap-2 mb-2 shrink-0">
            ${ACTION_ICONS.vote}<span>Résultats du vote</span>
        </h3>
        ${verdict}
        <ul class="flex flex-col gap-1 min-h-0 overflow-y-auto pr-1">
            ${ballots || '<li class="text-sm italic opacity-60">Aucun vote enregistré.</li>'}
        </ul>
        ${RESULT_CLOSE_BUTTON}
    `;
}

function renderNightResult(result) {
    return `
        <h3 class="action-title font-display text-lg flex items-center gap-2 mb-2 shrink-0">
            ${ACTION_ICONS.nuit}<span>Réponse du Maître du Jeu</span>
        </h3>
        <div class="min-h-0 overflow-y-auto pr-1">
            <p class="font-serif text-base italic leading-snug">${escapeHtml(result.text)}</p>
        </div>
        ${RESULT_CLOSE_BUTTON}
    `;
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

    // Un résultat à lire passe avant tout le reste.
    if (actionResult) {
        panel.dataset.phase = actionResult.kind;
        panel.innerHTML = actionResult.kind === "vote" ? renderVoteResult(actionResult) : renderNightResult(actionResult);
        zone.classList.remove('hidden');
        return;
    }

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
            class="action-submit mt-3 w-full shrink-0 rounded-md py-2 font-serif text-base font-semibold tracking-wide flex items-center justify-center min-h-10">
            ${pendingAction.stage === "waiting"
                ? `<span class="action-spinner" aria-hidden="true"></span><span class="sr-only">En attente de la réponse du serveur…</span>`
                : escapeHtml(texts.submit)}
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
    const waiting = pendingAction.stage === "waiting";

    document.querySelectorAll('#dynamic-action-panel .option-btn').forEach(btn => {
        const selected = actionSelection.includes(btn.dataset.id);
        btn.setAttribute('aria-pressed', String(selected));
        // En multi-sélection, une fois le maximum atteint, on grise les autres options.
        btn.disabled = waiting || (isFull && !selected);
    });

    const counter = document.getElementById('action-counter');
    if (counter) {
        counter.innerText = `${actionSelection.length}/${maxTargets} joueur(s) sélectionné(s)`;
    }

    const submit = document.getElementById('action-submit');
    if (submit) {
        const connected = ws && ws.readyState === WebSocket.OPEN;
        submit.disabled = waiting || actionSelection.length < minTargets || !connected;
        submit.classList.toggle('is-waiting', waiting);
    }
}

function submitPendingAction() {
    if (!pendingAction || pendingAction.stage !== "choosing" || actionSelection.length < pendingAction.minTargets) return;
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

    if (pendingAction.kind === "discussion") {
        // Le serveur répond par "private_channel_opened", qui ouvre le salon dans la sidebar gauche.
        clearPendingAction();
    } else {
        // Vote / nuit : loader dans le bouton jusqu'à la réponse du serveur.
        pendingAction.stage = "waiting";
        renderActionPanel();
    }
}

// ================= INTERACTIONS & MODALES =================
function assignRole(name, description) {
    gameState.roleInfo = { name, description };
    gameState.allies = null; // inconnus tant que la première nuit ne les a pas révélés
    renderPlayersList(); // retire le rôle du joueur des listes de soupçons (ou les verrouille si rôle maléfique)
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

    const changed = announcementEl.innerText.trim() !== String(text).trim();

    // 1. Mettre à jour le texte (le title permet de lire une annonce tronquée au survol)
    announcementEl.innerText = `${text}`;
    announcementEl.title = `${text}`;

    // 2. Effet doré si l'annonce a réellement changé (on relance l'animation si elle est en cours)
    if (changed) {
        announcementEl.classList.remove('announce-flash');
        void announcementEl.offsetWidth; // force le reflow pour redémarrer l'animation
        announcementEl.classList.add('announce-flash');
    }
}

let currentWhisperAgent = null;

function showAgentWhisperModal(agentId, agentName, message) {
    currentWhisperAgent = agentId;
    const modal = document.getElementById('modal-agent-whisper');
    const textEl = document.getElementById('agent-whisper-text');
    const actionsEl = document.getElementById('agent-whisper-actions');
    const name = agentName || getPlayerName(agentId);

    if (textEl) {
        textEl.innerText = message || `${name} souhaite s'entretenir discrètement avec vous dans l'ombre.`;
    }

    if (actionsEl) {
        actionsEl.innerHTML = `
            <button onclick="acceptAgentWhisper()" class="btn-seal flex-1">Accepter</button>
            <button onclick="refuseAgentWhisper()" class="btn-ghost flex-1">Ignorer</button>
        `;
    }

    if (modal) modal.classList.remove('hidden');
}

function refuseAgentWhisper() {
    const modal = document.getElementById('modal-agent-whisper');
    const textEl = document.getElementById('agent-whisper-text');
    const actionsEl = document.getElementById('agent-whisper-actions');

    if (textEl) {
        textEl.innerText = `Vous avez refusé l'entretien avec ${currentWhisperAgent ? getPlayerName(currentWhisperAgent) : 'l\'agent'}. Que souhaitez-vous faire ?`;
    }

    if (actionsEl) {
        actionsEl.innerHTML = `
            <button onclick="closeAgentWhisperModalOnly()" class="btn-ghost flex-1">Lancer une discussion</button>
            <button onclick="triggerVotePhaseFromModal()" class="btn-seal btn-blood flex-1">Lancer le vote</button>
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

    if (!modal || !headerEl) return;

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
    headerEl.innerText = `Jour ${turnNumber} — ${executionText}`;

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
    if (listEl) listEl.innerHTML = html;

    // Les résultats s'affichent dans l'encadré d'action ; la modale ne s'ouvre
    // que si le joueur lui-même est exécuté (message important à ne pas manquer).
    if (executedPlayer && executedPlayer === currentUsername) {
        modal.classList.remove('hidden');
    }
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
            messageEl.innerHTML = `L'obscurité a frappé cette nuit…`;
            if (deathNoticeEl) deathNoticeEl.classList.remove('hidden');
        } else {
            messageEl.innerHTML = `Les ténèbres ont frappé…<br><span class="modal-highlight-blood">${escapeHtml(getPlayerName(deadPlayerName))}</span> est mort·e cette nuit.`;
            if (deathNoticeEl) deathNoticeEl.classList.add('hidden');
        }
        nightLogText = `${deadPlayerName} est mort cette nuit.`;
    } else {
        messageEl.innerHTML = `Les esprits ont protégé le village…<br><span class="modal-highlight-good">Personne n'est mort</span> cette nuit !`;
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
        <span class="modal-kicker block mb-2">Tour ${escapeHtml(String(turnNumber ?? ''))}</span>
        <p class="font-serif text-base italic leading-relaxed">${escapeHtml(infoText)}</p>
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
    gameIsOver = true;
    document.getElementById('gameover-title').innerText = `Victoire des ${winner}`;
    document.getElementById('gameover-desc').innerText = details;

    // Victoire ou défaite du joueur, si son rôle est connu
    const outcomeEl = document.getElementById('gameover-outcome');
    const card = document.getElementById('gameover-card');
    if (outcomeEl && card && gameState.roleInfo?.name && resolveRoleKey(gameState.roleInfo.name)) {
        const evilWon = /d[ée]mon|mal|sbire/i.test(String(winner));
        const playerWon = evilWon === isEvilRole();
        outcomeEl.innerText = playerWon ? "Votre camp l'emporte !" : "Votre camp a perdu…";
        outcomeEl.classList.remove('hidden');
        card.dataset.tone = playerWon ? 'gold' : 'blood';
        outcomeEl.style.color = playerWon ? 'var(--gold)' : 'oklch(0.66 0.22 25)';
    }

    document.getElementById('modal-gameover').classList.remove('hidden');
}

// ================= CONNEXION PERDUE =================
let gameIsOver = false;

function showDisconnectedModal() {
    const gameVisible = !document.getElementById('screen-game')?.classList.contains('hidden');
    if (!gameVisible || gameIsOver) return; // pas pendant l'accueil ni après la fin de partie
    document.getElementById('modal-disconnected')?.classList.remove('hidden');
}

function closeDisconnectedModal() {
    document.getElementById('modal-disconnected')?.classList.add('hidden');
}

function updateSuspicion(targetId, value) {
    if (value) suspicions[targetId] = value;
    else delete suspicions[targetId];
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
    const showRoles = tabName === 'roles';
    document.getElementById('grimoire-tab-roles')?.classList.toggle('hidden', !showRoles);
    document.getElementById('grimoire-tab-rules')?.classList.toggle('hidden', showRoles);
    document.getElementById('grimoire-tab-btn-roles')?.classList.toggle('is-active', showRoles);
    document.getElementById('grimoire-tab-btn-rules')?.classList.toggle('is-active', !showRoles);
}

// Échap ferme le Grimoire
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeGrimoireModal();
});

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