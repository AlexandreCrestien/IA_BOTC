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
    'open-codex':     () => openCodexModal(),
    'close-codex':    () => closeCodexModal(),
    'codex-tab':      el => switchCodexTab(el.dataset.tab),
    'close-role-reveal': () => closeRoleRevealModal(),
    'accept-whisper':    () => answerAgentWhisper(true),
    'refuse-whisper':    () => answerAgentWhisper(false),
    'close-vote-result': () => closeVoteResultModal(),
    'close-night-result':() => closeNightResultModal(),
    'close-night-info':  () => closeNightInfoModal(),
    'close-disconnected':() => closeDisconnectedModal(),
    'ask-abandon':       () => { toggleGameMenu(false); openModal('modal-abandon'); },
    'cancel-abandon':    () => closeModal('modal-abandon'),
    'confirm-abandon':   () => confirmAbandon(),
    'skip-turn':         () => skipTurnPrompt(),
    'skip-private':      () => skipPrivateDiscussion(),
    'reload':            () => location.reload(),
    // Comptes (account.js)
    'welcome-tab':       el => switchWelcomeTab(el.dataset.tab),
    'resume-guest-game': () => resumeGuestGame(),
    'toggle-menu':       () => toggleGameMenu(),
    'close-menu':        () => toggleGameMenu(false),
    'logout':            () => logout(),
    'open-account':      el => openAccountModal(el.dataset.mode),
    'close-account':     () => closeAccountModal(),
    'switch-account-mode': () => switchAccountMode(),
    'new-game':          () => startNewGame()
};

document.addEventListener('click', (event) => {
    // Clic en dehors du menu de la partie : il se referme
    if (!event.target.closest('#game-menu, #menu-btn')) toggleGameMenu(false);
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

// Formulaires : rejoindre la partie (invité), se connecter, s'inscrire, envoyer un message
document.getElementById('welcome-form').addEventListener('submit', (event) => {
    event.preventDefault();
    joinGame();
});

document.getElementById('login-form').addEventListener('submit', (event) => {
    event.preventDefault();
    submitWelcomeAccount('login');
});

document.getElementById('register-form').addEventListener('submit', (event) => {
    event.preventDefault();
    submitWelcomeAccount('register');
});

document.getElementById('forgot-form').addEventListener('submit', (event) => {
    event.preventDefault();
    submitForgotPassword();
});

document.getElementById('account-form').addEventListener('submit', (event) => {
    event.preventDefault();
    submitGameAccount();
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

// Échap ferme le Codex, le menu, la fenêtre de compte et la confirmation d'abandon
document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
        closeCodexModal();
        toggleGameMenu(false);
        closeAccountModal();
        closeModal('modal-abandon');
    }
});

// Accueil : joueur connecté (tableau de bord, ou sa partie), ou partie d'invité à reprendre
initWelcome();
