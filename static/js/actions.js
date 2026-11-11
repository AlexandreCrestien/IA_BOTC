/* ==========================================================
   actions.js — sidebar droite : encadré dynamique des actions de phase
   (choix de jour / vote / nuit, attente de la réponse, résultats)

   Le serveur envoie ce qu'il faut afficher via un message "action_request" :
     { type: "action_request", kind: "discussion" | "vote" | "nuit",
       candidates: [playerId, ...], max_targets: 1 | 2,
       min_targets?: n, role?: "imp" | "Diablotin" | ... }
   Seul le texte (titre, consigne, bouton) est défini côté client, selon la phase et le rôle.
   ========================================================== */
'use strict';

// Icône du titre selon le type d'action
const ACTION_ICON_BY_KIND = { discussion: 'users', vote: 'scale', nuit: 'moon' };

let pendingAction = null;   // { kind, candidates, maxTargets, minTargets, role, stage: "choosing" | "waiting" } ou null
let actionSelection = [];   // ids sélectionnés
const NO_TARGET = "__none__"; // option "Personne" du vote

// Résultat affiché dans l'encadré (vote ou réponse de nuit). Il reste affiché jusqu'à ce que
// le joueur le ferme ; une nouvelle action ne peut le remplacer qu'après RESULT_MIN_DISPLAY_MS.
let actionResult = null;    // { kind: "vote" | "nuit", shownAt, ...données }
let deferredActionRequest = null;
let deferredActionTimer = null;
const RESULT_MIN_DISPLAY_MS = 12000;

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

const RESULT_CLOSE_BUTTON = `
    <button type="button" data-action="close-result"
        class="mt-3 w-full shrink-0 flex items-center justify-center gap-2 rounded-md py-1.5 text-sm opacity-70 hover:opacity-100 transition-opacity">
        ${icon('close')}
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
            ${icon(ACTION_ICON_BY_KIND.vote)}<span>Résultats du vote</span>
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
            ${icon(ACTION_ICON_BY_KIND.nuit)}<span>Réponse du Maître du Jeu</span>
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
            ${icon(ACTION_ICON_BY_KIND[kind])}
            <span>${escapeHtml(texts.title)}</span>
        </h3>
        <p class="font-serif text-sm italic opacity-90 mb-2 shrink-0">${escapeHtml(texts.prompt)}</p>
        ${maxTargets > 1 ? `<p id="action-counter" class="text-xs opacity-60 mb-1 shrink-0"></p>` : ''}
        <div class="flex flex-col gap-1 min-h-0 overflow-y-auto pr-1">
            ${options.map(o => `
                <button type="button" class="option-btn" data-action="toggle-target" data-id="${escapeHtml(o.id)}" aria-pressed="false">
                    <span class="truncate">${o.label}</span>
                    ${icon('check', 'option-check size-4')}
                </button>
            `).join('')}
        </div>
        <button type="button" id="action-submit" data-action="submit-action"
            class="action-submit mt-3 w-full shrink-0 rounded-md py-2 font-serif text-base font-semibold tracking-wide flex items-center justify-center min-h-10">
            ${pendingAction.stage === "waiting"
                ? `<span class="action-spinner" aria-hidden="true"></span><span class="sr-only">En attente de la réponse du serveur…</span>`
                : escapeHtml(texts.submit)}
        </button>
    `;

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
        counter.textContent = `${actionSelection.length}/${maxTargets} joueur(s) sélectionné(s)`;
    }

    const submit = document.getElementById('action-submit');
    if (submit) {
        submit.disabled = waiting || actionSelection.length < minTargets || !isWsOpen();
        submit.classList.toggle('is-waiting', waiting);
    }
}

function submitPendingAction() {
    if (!pendingAction || pendingAction.stage !== "choosing" || actionSelection.length < pendingAction.minTargets) return;
    if (!isWsOpen()) {
        appendSystemMessage("Connexion perdue : votre choix n'a pas été envoyé.");
        return;
    }

    const targets = [...actionSelection];
    const names = targets.map(getPlayerName).join(', ');

    if (pendingAction.kind === "discussion") {
        sendAction("request_whisper", { targets });
        appendSystemMessage(`Proposition de discussion privée envoyée à : ${names}.`);
    } else if (pendingAction.kind === "vote") {
        const targetId = targets[0] === NO_TARGET ? null : targets[0];
        sendAction("submit_vote", { target_id: targetId });
        appendSystemMessage(`Vote enregistré pour : ${targetId ? getPlayerName(targetId) : 'Personne'}.`);
    } else if (pendingAction.kind === "nuit") {
        sendAction("submit_night_action", { targets });
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
