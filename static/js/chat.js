/* ==========================================================
   chat.js — sidebar gauche : onglets, canaux, messages, historiques
   ========================================================== */
'use strict';

let activeLeftTab = 'chat';
let hasUnreadPublic = false;
const channelTitles = { public: "Place publique" }; // channel_id -> titre affiché

// ================= ONGLETS (Chat / Nuits / Votes) =================
function switchLeftTab(tabName) {
    activeLeftTab = tabName;
    document.querySelectorAll('.left-tab').forEach(btn => {
        const isActive = btn.dataset.tab === tabName;
        btn.classList.toggle('is-active', isActive);
        btn.setAttribute('aria-selected', String(isActive));
        document.getElementById(`tab-content-${btn.dataset.tab}`).classList.toggle('hidden', !isActive);
    });
    refreshUnreadBadges();
}

// ================= NOUVEAUX MESSAGES SUR LA PLACE PUBLIQUE =================
// Le joueur voit la place publique s'il est sur l'onglet Chat ET sur le canal public.
function isViewingPublic() {
    return activeLeftTab === 'chat' && gameState.currentChannel === 'public';
}

// Pastille sur "Place publique" si le joueur est dans un autre canal,
// pastille à côté de "Chat" s'il est sur un autre onglet (les deux peuvent coexister).
function refreshUnreadBadges() {
    if (isViewingPublic()) hasUnreadPublic = false;
    document.getElementById('unread-public').hidden = !(hasUnreadPublic && gameState.currentChannel !== 'public');
    document.getElementById('unread-chat-tab').hidden = !(hasUnreadPublic && activeLeftTab !== 'chat');
}

// ================= MESSAGES =================
function sendChatMessage() {
    const input = document.getElementById('chat-input');
    const content = input.value.trim();
    if (!content) return;
    if (sendAction("send_chat", { channel_id: gameState.currentChannel, content })) {
        input.value = "";
    }
}

function receiveChatMessage(channelId, sender, content) {
    if (!gameState.messages[channelId]) gameState.messages[channelId] = [];
    gameState.messages[channelId].push({ sender, content, time: currentTime() });
    if (channelId === gameState.currentChannel) renderChatMessages();

    // Nouveau message public (hors messages du joueur lui-même) pendant qu'il regarde ailleurs
    if (channelId === 'public' && sender !== playerId && !isViewingPublic()) {
        hasUnreadPublic = true;
        refreshUnreadBadges();
    }
}

// Message système (italique doré) : enregistré dans le canal pour survivre aux re-rendus.
// Par défaut, il va dans le canal affiché.
function appendSystemMessage(text, channelId = gameState.currentChannel) {
    if (!gameState.messages[channelId]) gameState.messages[channelId] = [];
    gameState.messages[channelId].push({ system: true, content: text });
    if (channelId === gameState.currentChannel) renderChatMessages();
}

function renderSystemLine(text) {
    return `
        <div class="ornament animate-rise px-2 text-center my-2">
            <p class="max-w-[85%] mx-auto font-serif text-sm italic text-gold">${escapeHtml(text)}</p>
        </div>
    `;
}

function renderChatMessage(m) {
    return `
        <div class="flex animate-rise flex-col items-start my-3">
            <div class="mb-0.5 flex items-baseline gap-2 px-1 text-[11px]">
                <span class="font-semibold opacity-80">${escapeHtml(m.sender)}</span>
                ${m.time ? `<span class="opacity-50">${m.time}</span>` : ''}
            </div>
            <p class="chat-bubble break-words rounded-lg rounded-tl-sm px-3 py-2 text-sm leading-relaxed">${escapeHtml(m.content)}</p>
        </div>
    `;
}

function renderChatMessages() {
    const box = document.getElementById('chat-messages');
    const channelId = gameState.currentChannel;

    // En-tête selon le canal actif
    let html = channelId === 'public'
        ? renderSystemLine("Canal public initialisé…")
        : renderSystemLine(`Début de la discussion privée avec ${channelTitles[channelId] || 'cette conversation'}.`);

    const msgs = gameState.messages[channelId] || [];
    html += msgs.length
        ? msgs.map(m => m.system ? renderSystemLine(m.content) : renderChatMessage(m)).join('')
        : `<div class="italic text-center py-4 text-xs opacity-60">Aucun message dans ce canal...</div>`;

    box.innerHTML = html;
    box.scrollTop = box.scrollHeight;
}

// ================= CANAUX =================
function handlePrivateChannelOpened(channelId, text, members = []) {
    if (!gameState.messages[channelId]) gameState.messages[channelId] = [];
    if (text) appendSystemMessage(text, channelId);

    if (!channelTitles[channelId]) {
        channelTitles[channelId] = members.length ? members.join(', ') : 'Privé';

        const item = document.createElement('li');
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'channel-btn';
        button.dataset.action = 'switch-channel';
        button.dataset.channel = channelId;
        button.textContent = channelTitles[channelId];
        item.appendChild(button);
        document.getElementById('chat-channels').appendChild(item);
    }

    switchChannel(channelId);
}

function switchChannel(channelId) {
    gameState.currentChannel = channelId;
    document.getElementById('active-channel-title').textContent = channelTitles[channelId] || channelId;

    document.querySelectorAll('.channel-btn').forEach(btn => {
        const isActive = btn.dataset.channel === channelId;
        btn.classList.toggle('is-active', isActive);
        btn.setAttribute('aria-current', isActive ? 'true' : 'false');
    });

    renderChatMessages();
    refreshUnreadBadges();
}

// ================= HISTORIQUES (onglets Votes et Nuits) =================
function renderVoteHistory() {
    const container = document.getElementById('tab-content-votes');
    const history = gameState.vote_history;

    if (!history.length) {
        container.innerHTML = `<div class="text-center py-8 text-sm italic font-serif opacity-70">Aucun vote enregistré pour le moment.</div>`;
        return;
    }

    // Regroupement par tour, du plus récent au plus ancien
    const turns = {};
    history.forEach(record => {
        if (!turns[record.turn]) turns[record.turn] = { votes: [], executed: record.executed };
        turns[record.turn].votes.push(record);
    });

    container.innerHTML = '<div class="p-1 space-y-3">' + Object.keys(turns).sort((a, b) => b - a).map(turn => {
        const { votes, executed } = turns[turn];
        const executionText = executed ? `${getPlayerName(executed)} exécuté` : "Aucune exécution";
        return `
            <div class="space-y-2">
                ${renderSystemLine(`Tour ${turn} — ${executionText}`)}
                <div class="space-y-1.5 pl-2">
                    ${votes.map(v => `
                        <div class="panel p-2.5 rounded-lg text-xs">
                            <span class="font-semibold">${escapeHtml(getPlayerName(v.voter))}</span>
                            <span class="ml-1.5 opacity-70">a voté pour</span>
                            <span class="font-semibold text-gold ml-1">${v.target ? escapeHtml(getPlayerName(v.target)) : "Personne"}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }).join('') + '</div>';
}

function renderNightInfoHistory() {
    const container = document.getElementById('tab-content-night');
    const history = gameState.night_info_history;

    if (!history.length) {
        container.innerHTML = `<div class="text-center py-8 text-sm italic font-serif opacity-70">Aucun événement nocturne pour le moment.</div>`;
        return;
    }

    container.innerHTML = '<div class="p-1 space-y-3">' + history.map(item => {
        const isResult = item.type === "result";
        return `
            <div class="panel night-history-item ${isResult ? 'is-result' : ''} rounded-lg p-3 text-sm">
                <div class="night-history-turn font-serif font-bold italic mb-1">Tour ${escapeHtml(item.turn)}</div>
                <p class="font-sans leading-relaxed">${escapeHtml(item.info || '')}</p>
            </div>
        `;
    }).join('') + '</div>';
}
