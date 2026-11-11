/* ==========================================================
   players.js — sidebar droite : liste des convives, soupçons, alliés
   ========================================================== */
'use strict';

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

// Allié connu (rôles maléfiques uniquement) : { id, role } ou undefined
function getAlly(id) {
    return (gameState.allies || []).find(a => a.id === id);
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
    const allPlayers = gameState.players || [];

    // Compteur sur tout le village (joueur humain compris)
    const counter = document.getElementById('players-count');
    const alive = allPlayers.filter(p => p.alive !== false).length;
    counter.textContent = allPlayers.length ? `${alive} vivant·e·s · ${allPlayers.length - alive} mort·e·s` : '';

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
                            : `<span class="status-dead ml-auto shrink-0 flex items-center gap-1 text-xs" title="Dernier vote : ${p.has_vote ? 'disponible' : 'utilisé'}">Mort <span class="opacity-70">· vote ${p.has_vote ? 'dispo' : 'utilisé'}</span></span>`}
                    </div>
                    <!-- Ligne 2 : soupçon (ou allié connu) -->
                    ${ally ? renderAllyTag(ally) : renderSuspicionSelect(p)}
                </div>
            </article>
        `;
    }).join('');
}

function updateSuspicion(targetId, value) {
    if (value) suspicions[targetId] = value;
    else delete suspicions[targetId];
}
