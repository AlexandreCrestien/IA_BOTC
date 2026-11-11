/* ==========================================================
   main.js — branchement des événements (chargé en dernier)
   Plus aucun gestionnaire inline dans le HTML : les boutons portent un
   attribut data-action, traité ici par un seul écouteur délégué
   (il couvre aussi les éléments générés dynamiquement).
   ========================================================== */
'use strict';

// data-action → fonction (el = élément qui porte l'attribut)
const CLICK_ACTIONS = {
    'switch-tab':        el => switchLeftTab(el.dataset.tab),
    'switch-channel':    el => switchChannel(el.dataset.channel),
    'toggle-target':     el => toggleActionTarget(el.dataset.id),
    'submit-action':     () => submitPendingAction(),
    'close-result':      () => closeActionResult(),
    'open-grimoire':     () => openGrimoireModal(),
    'close-grimoire':    () => closeGrimoireModal(),
    'grimoire-tab':      el => switchGrimoireTab(el.dataset.tab),
    'close-role-reveal': () => closeRoleRevealModal(),
    'accept-whisper':    () => acceptAgentWhisper(),
    'refuse-whisper':    () => refuseAgentWhisper(),
    'whisper-discuss':   () => closeAgentWhisperModalOnly(),
    'whisper-vote':      () => triggerVotePhaseFromModal(),
    'close-vote-result': () => closeVoteResultModal(),
    'close-night-result':() => closeNightResultModal(),
    'close-night-info':  () => closeNightInfoModal(),
    'close-disconnected':() => closeDisconnectedModal(),
    'reload':            () => location.reload()
};

document.addEventListener('click', (event) => {
    const el = event.target.closest('[data-action]');
    if (!el || el.disabled) return;
    // Voile d'une modale : seul un clic sur le voile lui-même la ferme (pas sur la carte)
    if (el.hasAttribute('data-backdrop') && event.target !== el) return;
    const handler = CLICK_ACTIONS[el.dataset.action];
    if (handler) handler(el);
});

// Liste "Je soupçonne…" des convives
document.addEventListener('change', (event) => {
    const select = event.target.closest('.suspicion-select');
    if (select?.dataset.playerId) updateSuspicion(select.dataset.playerId, select.value);
});

// Formulaires : rejoindre la partie, envoyer un message
document.getElementById('welcome-form').addEventListener('submit', (event) => {
    event.preventDefault();
    joinGame();
});

document.getElementById('chat-form').addEventListener('submit', (event) => {
    event.preventDefault();
    sendChatMessage();
});

// Entrée envoie le message, Maj+Entrée fait un retour à la ligne
// (isComposing : pas d'envoi pendant la saisie d'un accent avec une touche morte)
document.getElementById('chat-input').addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        sendChatMessage();
    }
});

// Échap ferme le Grimoire
document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeGrimoireModal();
});
