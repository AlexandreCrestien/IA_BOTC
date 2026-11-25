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
        // Réponse donnée dans le canal attendu : le bandeau de saisie disparaît
        if (turnPrompt && turnPrompt.channelId === gameState.currentChannel) hideTurnPrompt();
    }
}

// ================= SAISIE ATTENDUE PAR LE MOTEUR (bandeau au-dessus du chat) =================
// Message public ou message privé : facultatifs, le joueur peut passer.
let turnPrompt = null; // { kind, channelId } ou null

const TURN_PROMPT_SKIP_LABELS = {
    public_message: "Passer",
    private_message: "Terminer la discussion"
};

function showTurnPrompt(request) {
    turnPrompt = { kind: request.kind, channelId: request.channel_id || 'public' };
    setAnnouncement(request.text);

    // On amène le joueur là où il doit écrire
    switchLeftTab('chat');
    if (channelTitles[turnPrompt.channelId]) switchChannel(turnPrompt.channelId);

    document.getElementById('turn-prompt-text').textContent = request.text;
    document.getElementById('turn-prompt-skip').textContent = TURN_PROMPT_SKIP_LABELS[request.kind] || "Passer";
    document.getElementById('turn-prompt').classList.remove('hidden');
    document.getElementById('chat-input').focus();
}

function hideTurnPrompt() {
    turnPrompt = null;
    document.getElementById('turn-prompt').classList.add('hidden');
}

function skipTurnPrompt() {
    if (!turnPrompt) return;
    sendAction("skip_turn", { kind: turnPrompt.kind });
    hideTurnPrompt();
}

// messageId : message d'un agent IA, que le joueur connecté peut signaler ; reported : déjà signalé (reconnexion)
function receiveChatMessage(channelId, sender, content, messageId = null, reported = false) {
    if (!gameState.messages[channelId]) gameState.messages[channelId] = [];
    gameState.messages[channelId].push({ sender, content, time: currentTime(), message_id: messageId, reported });
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
        <div class="chat-message flex animate-rise flex-col items-start my-3">
            <div class="mb-0.5 flex items-baseline gap-2 px-1 text-[11px]">
                <span class="font-semibold opacity-80">${escapeHtml(getPlayerName(m.sender))}</span>
                ${m.time ? `<span class="opacity-50">${m.time}</span>` : ''}
                ${renderReportButton(m)}
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
function handlePrivateChannelOpened(channelId, text, members = [], focus = true) {
    if (!gameState.messages[channelId]) gameState.messages[channelId] = [];
    if (text) appendSystemMessage(text, channelId);

    if (!channelTitles[channelId]) {
        channelTitles[channelId] = members.length ? members.map(getPlayerName).join(', ') : 'Privé';

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

    if (focus) switchChannel(channelId);
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
// Reconnexion : le serveur renvoie les deux historiques complets (sans rouvrir de modale)
function restoreHistories(nights, votes) {
    gameState.night_info_history = Array.isArray(nights) ? nights : [];
    gameState.vote_history = Array.isArray(votes) ? votes : [];
    renderNightInfoHistory();
    renderVoteHistory();
}

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
                            ${v.unavailable ? '<span class="ml-1 opacity-60">(IA indisponible)</span>' : ''}
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
                <p class="font-sans leading-relaxed">${escapeHtml(isResult ? nightDeathText(item.dead_player) : (item.info || ''))}</p>
            </div>
        `;
    }).join('') + '</div>';
}

// ================= SIGNALEMENT D'UN MESSAGE D'IA =================
// Réservé aux joueurs connectés dont la partie est rattachée au compte (rien n'est collecté sur les invités).
// Mêmes catégories côté serveur : backend/server/reports.py (REPORT_CATEGORIES).
const REPORT_CATEGORIES = {
    knowledge: "Révèle une information qu'il ne devrait pas connaître",
    rules: "Incohérent ou contraire aux règles",
    character: "Sort de son personnage",
    inappropriate: "Contenu inapproprié",
    other: "Autre"
};
const REPORT_COMMENT_MAX = 200;       // commentaire facultatif
const REPORT_OTHER_COMMENT_MAX = 500; // « Autre » : commentaire obligatoire
const FLAG_ICON = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="size-3" aria-hidden="true"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"></path><line x1="4" x2="4" y1="22" y2="15"></line></svg>';

let reportingMessageId = null;
let gameNotLinked = false; // connecté en cours de partie, mais la partie n'a pas pu être rattachée au compte

function canReport() {
    return Boolean(currentUser) && !gameNotLinked;
}

function renderReportButton(m) {
    if (!m.message_id || !canReport()) return '';
    if (m.reported) return `<span class="report-done">${FLAG_ICON} Signalé</span>`;
    return `<button type="button" class="report-btn" data-action="open-report" data-message="${escapeHtml(m.message_id)}"
                aria-label="Signaler ce message de ${escapeHtml(getPlayerName(m.sender))}" title="Signaler ce message">${FLAG_ICON}</button>`;
}

function findChatMessage(messageId) {
    for (const messages of Object.values(gameState.messages)) {
        const found = messages.find(m => m.message_id === messageId);
        if (found) return found;
    }
    return null;
}

function openReportModal(messageId) {
    const message = findChatMessage(messageId);
    if (!message || message.reported || !canReport()) return;
    reportingMessageId = messageId;
    document.getElementById('report-quote').textContent = `${getPlayerName(message.sender)} : « ${message.content} »`;
    document.getElementById('report-categories').innerHTML = Object.entries(REPORT_CATEGORIES).map(([key, label]) => `
        <label class="report-category">
            <input type="radio" name="report-category" value="${key}">
            <span>${escapeHtml(label)}</span>
        </label>
    `).join('');
    document.getElementById('report-comment').value = '';
    setFormError('report-error', null);
    document.getElementById('report-submit').disabled = false;
    updateReportComment();
    openModal('modal-report');
    document.querySelector('#report-categories input').focus();
}

function closeReportModal() {
    reportingMessageId = null;
    closeModal('modal-report');
}

function selectedReportCategory() {
    return document.querySelector('#report-categories input:checked')?.value || null;
}

// « Autre » : commentaire obligatoire et plus long ; sinon facultatif et court
function updateReportComment() {
    const other = selectedReportCategory() === 'other';
    const max = other ? REPORT_OTHER_COMMENT_MAX : REPORT_COMMENT_MAX;
    const comment = document.getElementById('report-comment');
    comment.maxLength = max;
    if (comment.value.length > max) comment.value = comment.value.slice(0, max);
    comment.required = other;
    document.getElementById('report-comment-label').textContent = other
        ? "Décrivez le problème (obligatoire)" : "Commentaire (facultatif)";
    document.getElementById('report-count').textContent = `${comment.value.length} / ${max}`;
}

function submitReport() {
    const category = selectedReportCategory();
    const comment = document.getElementById('report-comment').value.trim();
    if (!category) return setFormError('report-error', "Choisissez le problème.");
    if (category === 'other' && !comment) return setFormError('report-error', "Décrivez le problème en quelques mots.");
    const payload = { message_id: reportingMessageId, category, comment: comment || null };
    if (!sendAction("report_message", payload)) {
        return setFormError('report-error', "Connexion perdue : le signalement n'a pas été envoyé.");
    }
    setFormError('report-error', null);
    document.getElementById('report-submit').disabled = true; // en attente de la réponse du serveur
}

// Réponse du serveur : message marqué « Signalé », ou motif du refus
function handleReportResult(messageId, error) {
    if (error) {
        if (reportingMessageId === messageId) {
            setFormError('report-error', error);
            document.getElementById('report-submit').disabled = false;
        } else {
            appendSystemMessage(error);
        }
        return;
    }
    const message = findChatMessage(messageId);
    if (message) message.reported = true;
    if (reportingMessageId === messageId) closeReportModal();
    renderChatMessages();
    appendSystemMessage("Merci : votre signalement a été transmis à l'équipe.");
}
