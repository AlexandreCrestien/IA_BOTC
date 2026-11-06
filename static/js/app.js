// ================= ÉTAT DE L'APPLICATION =================
// Le serveur envoie : "state", "event", "request", "game_over", "error".
// Le navigateur envoie : start_game, send_chat, create_channel, night_action, vote, pass.
let ws = null;
let pseudo = "";
let ui = freshState();

function freshState() {
    return {
        turn: 1,
        phase: "nuit",
        players: [],
        me: null,
        roleShown: false,
        channels: { public: { label: "Public", messages: [] } },
        channelOrder: ["public"],
        currentChannel: "public",
        currentPrivate: null,   // id du salon privé en cours
        nightLog: [],
        voteLog: [],
        request: null,           // demande en attente du moteur
        notes: {},               // soupçons notés par le joueur (local)
    };
}

const PHASE_LABELS = { nuit: "Nuit", discussion: "Discussion", vote: "Vote" };

// ================= CONNEXION =================
function joinGame() {
    const input = document.getElementById("welcome-player-id");
    pseudo = input.value.trim();
    if (!pseudo) {
        alert("Choisis un pseudo.");
        return;
    }
    const host = location.host || "127.0.0.1:8000";
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${protocol}://${host}/ws/${encodeURIComponent(pseudo)}`);

    ws.onopen = () => {
        document.getElementById("screen-welcome").classList.add("hidden");
        document.getElementById("screen-game").classList.remove("hidden");
        updateConnectionBadge(true);
        startGame();
    };
    ws.onmessage = (event) => {
        let data;
        try {
            data = JSON.parse(event.data);
        } catch (e) {
            console.error("Message serveur illisible :", event.data);
            return;
        }
        handleServerMessage(data);
    };
    ws.onclose = () => {
        updateConnectionBadge(false);
        appendSystem("public", "Connexion fermée par le serveur. Recharge la page pour rejouer.");
    };
    ws.onerror = (error) => console.error("Erreur WebSocket :", error);
}

function send(action, payload = {}) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ action, payload }));
}

function startGame() {
    ui = freshState();
    document.getElementById("modal-gameover").classList.add("hidden");
    setAnnouncement("Préparation de la partie : les rôles sont distribués...");
    renderAll();
    send("start_game");
}

function updateConnectionBadge(isConnected) {
    const badge = document.getElementById("connection-status");
    badge.className = isConnected
        ? "px-3 py-1 rounded-full text-xs font-semibold bg-green-900/50 text-green-400 border border-green-700 whitespace-nowrap z-10"
        : "px-3 py-1 rounded-full text-xs font-semibold bg-red-900/50 text-red-400 border border-red-700 whitespace-nowrap z-10";
    badge.innerText = isConnected ? "Connecté" : "Déconnecté";
}

// ================= MESSAGES DU SERVEUR =================
function handleServerMessage(message) {
    switch (message.type) {
        case "state":
            onState(message.data);
            break;
        case "event":
            onEvent(message.data);
            break;
        case "request":
            onRequest(message.data);
            break;
        case "game_over":
            onGameOver(message.data);
            break;
        case "error":
            showToast(typeof message.data === "string" ? message.data : JSON.stringify(message.data));
            break;
        default:
            console.warn("Message non géré :", message);
    }
}

function onState(data) {
    ui.turn = data.turn;
    ui.phase = data.phase;
    ui.players = data.players;
    ui.me = data.me;
    if (!ui.roleShown && ui.me) {
        ui.roleShown = true;
        showRole();
    }
    renderAll();
}

function onEvent(e) {
    if (e.channel === "personal") {
        ui.nightLog.push(e);
        setAnnouncement(e.content);
        showToast(e.content, "info");
        renderNightLog();
        return;
    }

    if (e.channel === "private") {
        const id = privateChannelFor(e);
        ui.channels[id].messages.push({ sender: e.is_me ? "Moi" : e.author, content: e.content, me: e.is_me });
        if (!e.is_me && ui.currentChannel !== id) markUnread(id);
        renderChannels();
        renderChat();
        return;
    }

    // Salon public
    if (e.is_game_master) {
        appendSystem("public", e.content);
        setAnnouncement(e.content);
        if (e.kind === "vote" || (e.phase === "vote" && (e.kind === "death" || e.kind === "announcement"))) {
            ui.voteLog.push(e);
            renderVoteLog();
        }
    } else {
        ui.channels.public.messages.push({ sender: e.is_me ? "Moi" : e.author, content: e.content, me: e.is_me });
        if (ui.currentChannel !== "public") markUnread("public");
        renderChat();
    }
}

function privateChannelFor(e) {
    // Un salon par conversation : même jour et mêmes participants.
    const others = e.participants.filter(n => !ui.me || n !== ui.me.name);
    const id = `private-${e.turn}-${others.join("-")}`;
    if (!ui.channels[id]) {
        ui.channels[id] = { label: `Privé (jour ${e.turn}) : ${others.join(", ")}`, messages: [] };
        ui.channelOrder.push(id);
        ui.currentPrivate = id;
        if (!e.is_me) setAnnouncement(`${e.author} veut te parler en privé.`);
    }
    return id;
}

function onRequest(request) {
    ui.request = request;
    if (request.kind === "public_message") switchChannel("public");
    if (request.kind === "private_message" && ui.currentPrivate) switchChannel(ui.currentPrivate);
    if (request.kind === "night" || request.kind === "vote") {
        switchLeftTab("chat");
        switchChannel("public");
    }
    renderActionPanel();
    renderChatInput();
}

function onGameOver(data) {
    ui.request = null;
    renderActionPanel();
    renderChatInput();
    document.getElementById("gameover-title").innerText = data.human_won ? "Victoire !" : "Défaite...";
    document.getElementById("gameover-desc").innerText = `Camp gagnant : ${data.winner}`;
    document.getElementById("gameover-roles").innerHTML = data.roles.map(r => `
        <div class="flex justify-between text-sm border-b border-clock-border py-1">
            <span class="${r.alive ? "text-gray-200" : "text-gray-500 line-through"}">${escapeHtml(r.name)}${r.is_me ? " (toi)" : ""}</span>
            <span class="text-clock-gold">${escapeHtml(r.role)}</span>
        </div>`).join("");
    document.getElementById("modal-gameover").classList.remove("hidden");
}

// ================= ACTIONS DU JOUEUR =================
function answerWithChoice() {
    const req = ui.request;
    if (!req) return;
    const checked = [...document.querySelectorAll("#dynamic-action-panel input[name=choice]:checked")].map(i => i.value);

    if (req.kind === "night") {
        if (checked.length !== req.count) {
            showToast(`Choisis exactement ${req.count} joueur(s).`);
            return;
        }
        send("night_action", { targets: checked });
    } else if (req.kind === "private_partners") {
        if (checked.length < 1 || checked.length > 2) {
            showToast("Choisis 1 ou 2 joueurs.");
            return;
        }
        send("create_channel", { target_ids: checked });
    } else if (req.kind === "vote") {
        const select = document.getElementById("vote-target-select");
        send("vote", { target_id: select && select.value ? select.value : null });
    }
    clearRequest();
}

function passRequest() {
    if (!ui.request) return;
    send("pass");
    clearRequest();
}

function clearRequest() {
    ui.request = null;
    renderActionPanel();
    renderChatInput();
}

function sendChatMessage() {
    const input = document.getElementById("chat-input");
    const content = input.value.trim();
    const req = ui.request;
    if (!content || !req) return;
    if (req.kind === "public_message") {
        send("send_chat", { channel_id: "public", content });
    } else if (req.kind === "private_message") {
        send("send_chat", { channel_id: "private", content });
    } else {
        return;
    }
    input.value = "";
    clearRequest();
}

function limitChoices(input) {
    const req = ui.request;
    if (!req || !req.count) return;
    const checked = document.querySelectorAll("#dynamic-action-panel input[name=choice]:checked");
    if (checked.length > req.count) input.checked = false;
}

function updateSuspicion(playerId, value) {
    ui.notes[playerId] = value;
}

// ================= AFFICHAGE =================
function renderAll() {
    renderHeader();
    renderRoundTable();
    renderPlayersList();
    renderRole();
    renderChannels();
    renderChat();
    renderNightLog();
    renderVoteLog();
    renderActionPanel();
    renderChatInput();
}

function renderHeader() {
    document.getElementById("game-day").innerText = ui.turn;
    document.getElementById("game-phase").innerText = PHASE_LABELS[ui.phase] || ui.phase;
    document.getElementById("alive-count").innerText = ui.players.filter(p => p.alive).length || "--";
}

function renderRole() {
    if (!ui.me) return;
    document.getElementById("player-role-name").innerText = `${ui.me.role} (${ui.me.team})`;
    document.getElementById("player-role-desc").innerText = ui.me.description;
    document.getElementById("player-role-desc").title = ui.me.description;
}

function showRole() {
    document.getElementById("modal-role-title").innerText = ui.me.role;
    document.getElementById("modal-role-description").innerText =
        `${ui.me.description}\n\nCamp : ${ui.me.team} (côté ${ui.me.alignment}).`;
    document.getElementById("modal-role-reveal").classList.remove("hidden");
}

function closeRoleRevealModal() {
    document.getElementById("modal-role-reveal").classList.add("hidden");
}

function renderRoundTable() {
    const table = document.getElementById("round-table");
    const players = ui.players;
    if (players.length === 0) {
        table.innerHTML = `<div class="text-center text-gray-500 text-sm italic">En attente des joueurs...</div>`;
        return;
    }
    const radius = 130;
    const centerX = table.offsetWidth / 2 || 192;
    const centerY = table.offsetHeight / 2 || 192;
    table.innerHTML = players.map((p, index) => {
        const angle = (index / players.length) * 2 * Math.PI - Math.PI / 2;
        const x = centerX + radius * Math.cos(angle) - 40;
        const y = centerY + radius * Math.sin(angle) - 40;
        const status = p.alive ? "border-green-600 bg-clock-panel" : "border-red-900 bg-red-950/40 opacity-70";
        const meRing = p.is_me ? "ring-2 ring-clock-gold" : "";
        return `
            <div class="absolute w-20 h-20 rounded-full border-2 ${status} ${meRing} flex flex-col items-center justify-center p-1 text-center shadow-lg"
                 style="left: ${x}px; top: ${y}px;" title="${escapeHtml(p.name)} (${p.alive ? "vivant" : "mort"})">
                <span class="text-xs font-bold truncate w-full text-gray-200 px-1">${escapeHtml(p.name)}</span>
                <span class="text-xs ${p.alive ? "text-green-400" : "text-red-500"} font-semibold">${p.alive ? "Vivant" : "Mort"}</span>
                ${p.is_me ? `<span class="text-[10px] text-clock-gold">toi</span>` : ""}
            </div>`;
    }).join("");
}

function renderPlayersList() {
    const list = document.getElementById("players-notes-list");
    const options = [["", "-- Soupçon --"], ["bien", "Plutôt bien"], ["mal", "Plutôt mal"], ["demon", "Démon ?"], ["sbire", "Sbire ?"]];
    list.innerHTML = ui.players.map(p => `
        <div class="bg-clock-dark border border-clock-border p-2.5 rounded-xl space-y-2">
            <div class="flex justify-between items-center text-sm">
                <span class="font-bold ${p.alive ? "text-gray-200" : "text-gray-500 line-through"}">${escapeHtml(p.name)}${p.is_me ? " (toi)" : ""}</span>
                <span class="text-xs px-2 py-0.5 rounded font-medium ${p.alive ? "bg-green-900/40 text-green-400" : "bg-red-900/40 text-red-400"}">
                    ${p.alive ? "Vivant" : (p.can_vote ? "Mort (vote fantôme)" : "Mort")}
                </span>
            </div>
            ${p.is_me ? "" : `
            <select onchange="updateSuspicion('${escapeAttr(p.id)}', this.value)" class="w-full bg-clock-panel border border-clock-border text-xs rounded px-2 py-1.5 text-gray-300 focus:outline-none focus:border-clock-gold">
                ${options.map(([v, l]) => `<option value="${v}" ${ui.notes[p.id] === v ? "selected" : ""}>${l}</option>`).join("")}
            </select>`}
        </div>`).join("") || `<div class="text-gray-500 text-sm italic">Aucun joueur.</div>`;
}

function renderChannels() {
    const box = document.getElementById("chat-channels");
    box.innerHTML = ui.channelOrder.map(id => {
        const ch = ui.channels[id];
        const active = id === ui.currentChannel;
        const unread = ch.unread ? " •" : "";
        return `<button onclick="switchChannel('${escapeAttr(id)}')" class="px-3 py-1.5 rounded-lg font-medium border border-clock-border whitespace-nowrap text-xs ${active ? "bg-clock-accent text-clock-gold" : "text-gray-400"}">${escapeHtml(ch.label)}${unread}</button>`;
    }).join("");
}

function switchChannel(id) {
    if (!ui.channels[id]) return;
    ui.currentChannel = id;
    ui.channels[id].unread = false;
    renderChannels();
    renderChat();
}

function markUnread(id) {
    ui.channels[id].unread = true;
}

function renderChat() {
    const box = document.getElementById("chat-messages");
    const msgs = ui.channels[ui.currentChannel].messages;
    box.innerHTML = msgs.map(m => m.system
        ? `<div class="text-yellow-500/80 italic">⚙️ ${escapeHtml(m.content)}</div>`
        : `<div class="mb-1.5"><span class="${m.me ? "text-green-400" : "text-clock-gold"} font-bold">[${escapeHtml(m.sender)}]</span> ${escapeHtml(m.content)}</div>`
    ).join("") || `<div class="text-gray-500 italic text-center">Aucun message dans ce salon...</div>`;
    box.scrollTop = box.scrollHeight;
}

function appendSystem(channelId, text) {
    ui.channels[channelId].messages.push({ system: true, content: text });
    if (ui.currentChannel === channelId) renderChat();
}

function renderChatInput() {
    const input = document.getElementById("chat-input");
    const button = document.getElementById("chat-send");
    const kind = ui.request && ui.request.kind;
    const canWrite = kind === "public_message" || kind === "private_message";
    input.disabled = !canWrite;
    button.disabled = !canWrite;
    input.placeholder = kind === "public_message" ? "Ton message public..."
        : kind === "private_message" ? "Ton message privé..."
        : "Attends ton tour pour écrire...";
    button.classList.toggle("opacity-40", !canWrite);
    if (canWrite) input.focus({ preventScroll: true });  // ne pas faire défiler la page
}

function renderNightLog() {
    const box = document.getElementById("tab-content-night");
    box.innerHTML = ui.nightLog.map(e => `
        <div class="bg-clock-dark border border-clock-border rounded-lg p-2">
            <div class="text-xs text-gray-500">${PHASE_LABELS[e.phase] || e.phase} ${e.turn}</div>
            <div class="text-purple-300">${escapeHtml(e.content)}</div>
        </div>`).join("") || `<div class="text-gray-500 italic">Aucune information nocturne pour l'instant.</div>`;
}

function renderVoteLog() {
    const box = document.getElementById("tab-content-votes");
    box.innerHTML = ui.voteLog.map(e => `
        <div class="bg-clock-dark border border-clock-border rounded-lg p-2">
            <div class="text-xs text-gray-500">Jour ${e.turn}</div>
            <div class="text-blue-300">${escapeHtml(e.content)}</div>
        </div>`).join("") || `<div class="text-gray-500 italic">Aucun vote pour l'instant.</div>`;
}

function renderActionPanel() {
    const panel = document.getElementById("dynamic-action-panel");
    const req = ui.request;
    if (!req) {
        panel.innerHTML = `
            <div class="flex items-center space-x-2 text-gray-400 text-sm">
                <span class="animate-pulse">⏳</span>
                <span>Les autres joueurs réfléchissent...</span>
            </div>`;
        return;
    }

    const prompt = `<div class="text-gray-200 text-sm">${escapeHtml(req.prompt)}</div>`;
    const passBtn = (label) => req.can_pass
        ? `<button onclick="passRequest()" class="w-full bg-gray-800 hover:bg-gray-700 text-gray-300 py-2 rounded-lg text-xs font-semibold uppercase tracking-wider">${label}</button>`
        : "";
    const okBtn = (label, color = "bg-clock-red hover:bg-red-800") =>
        `<button onclick="answerWithChoice()" class="w-full ${color} text-white py-2 rounded-lg text-xs font-semibold uppercase tracking-wider">${label}</button>`;
    const checkboxes = () => req.options.map(o => `
        <label class="flex items-center space-x-2 text-sm text-gray-300 cursor-pointer">
            <input type="checkbox" name="choice" value="${escapeAttr(o.id)}" onchange="limitChoices(this)" class="accent-yellow-600">
            <span>${escapeHtml(o.name)}</span>
        </label>`).join("");

    if (req.kind === "night") {
        panel.innerHTML = `<div class="text-purple-400 text-sm font-semibold">🌙 Ton action de nuit</div>${prompt}
            <div class="space-y-1">${checkboxes()}</div>${okBtn("Valider")}${passBtn("Choix au hasard")}`;
    } else if (req.kind === "public_message") {
        panel.innerHTML = `<div class="text-blue-400 text-sm font-semibold">💬 Discussion publique</div>${prompt}
            <div class="text-xs text-gray-500">Écris dans le chat à gauche.</div>${passBtn("Je ne dis rien")}`;
    } else if (req.kind === "private_partners") {
        panel.innerHTML = `<div class="text-clock-gold text-sm font-semibold">🤫 Conversation privée</div>${prompt}
            <div class="space-y-1">${checkboxes()}</div>${okBtn("Ouvrir la conversation", "bg-clock-gold/80 hover:bg-clock-gold text-clock-dark")}${passBtn("Passer")}`;
    } else if (req.kind === "private_message") {
        panel.innerHTML = `<div class="text-clock-gold text-sm font-semibold">🤫 Conversation privée</div>${prompt}
            <div class="text-xs text-gray-500">Écris dans le chat à gauche.</div>${passBtn("Terminer la conversation")}`;
    } else if (req.kind === "vote") {
        panel.innerHTML = `<div class="text-red-400 text-sm font-semibold">⚖️ Vote</div>${prompt}
            <select id="vote-target-select" class="w-full bg-clock-dark border border-clock-border rounded p-2 text-sm text-gray-200 focus:outline-none focus:border-clock-gold">
                <option value="">Personne</option>
                ${req.options.map(o => `<option value="${escapeAttr(o.id)}">${escapeHtml(o.name)}</option>`).join("")}
            </select>${okBtn("Confirmer mon vote")}`;
    }
}

function switchLeftTab(tabName) {
    ["chat", "night", "votes"].forEach(t => {
        document.getElementById(`tab-content-${t}`).classList.add("hidden");
        document.getElementById(`tab-btn-${t}`).className = "flex-1 py-3 font-medium text-gray-400 hover:text-gray-200 transition";
    });
    document.getElementById(`tab-content-${tabName}`).classList.remove("hidden");
    document.getElementById(`tab-btn-${tabName}`).className = "flex-1 py-3 font-semibold text-clock-gold border-b-2 border-clock-gold transition";
}

function setAnnouncement(text) {
    const box = document.getElementById("game-announcement");
    box.innerText = text;
    box.title = text;
}

let toastTimer = null;
function showToast(text, level = "error") {
    const toast = document.getElementById("toast");
    toast.innerText = text;
    toast.className = `fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-xl text-sm shadow-xl max-w-lg text-center ${
        level === "error" ? "bg-red-900 text-red-100 border border-red-700" : "bg-purple-900 text-purple-100 border border-purple-700"}`;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.add("hidden"), 6000);
}

function escapeHtml(text) {
    if (text === null || text === undefined) return "";
    return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function escapeAttr(text) {
    return escapeHtml(text).replace(/\\/g, "\\\\");
}
