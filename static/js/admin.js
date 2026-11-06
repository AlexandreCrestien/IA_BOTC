const ADMIN_API_URL = "/admin/debug/all-states";

// État global pour garder les données en mémoire lors des clics sur les onglets
let currentAdminData = null;
let selectedAgentId = null;

// Vérifier au chargement si un token est déjà stocké
window.addEventListener('DOMContentLoaded', () => {
    const savedToken = localStorage.getItem('botc_admin_token');
    if (savedToken) {
        document.getElementById('admin-token-input').value = savedToken;
        fetchAdminData();
    }
});

async function login() {
    const token = document.getElementById('admin-token-input').value.trim();
    if (!token) return;

    localStorage.setItem('botc_admin_token', token);
    await fetchAdminData();
}

function logout() {
    localStorage.removeItem('botc_admin_token');
    document.getElementById('login-section').classList.remove('hidden');
    document.getElementById('dashboard-section').classList.add('hidden');
    document.getElementById('auth-controls').classList.add('hidden');
}

async function fetchAdminData() {
    const token = localStorage.getItem('botc_admin_token');
    const errorEl = document.getElementById('login-error');

    try {
        const response = await fetch(ADMIN_API_URL, {
            headers: { "x-admin-token": token }
        });

        if (!response.ok) {
            throw new Error("Jeton invalide ou accès refusé");
        }

        const data = await response.json();
        
        errorEl.classList.add('hidden');
        document.getElementById('login-section').classList.add('hidden');
        document.getElementById('dashboard-section').classList.remove('hidden');
        document.getElementById('auth-controls').classList.remove('hidden');

        renderDashboard(data);

    } catch (err) {
        console.error(err);
        errorEl.classList.remove('hidden');
        localStorage.removeItem('botc_admin_token');
    }
}

function renderDashboard(data) {
    currentAdminData = data; // Sauvegarde des données en cache

    const agents = data.agents || data.players || [];
    document.getElementById('stat-agents-count').innerText = agents.length;
    document.getElementById('stat-turn-phase').innerText = `Tour ${data.turn || 1} (${data.phase || 'Nuit/Jour'})`;
    document.getElementById('stat-channels-count').innerText = (data.channels || []).length;

    // 1. Historique public
    const publicContainer = document.getElementById('public-history-container');
    const publicHistory = data.public_history || data.history || [];
    if (publicHistory.length === 0) {
        publicContainer.innerHTML = `<span class="italic text-gray-500 text-xs">Aucun message enregistré dans l'historique public.</span>`;
    } else {
        publicContainer.innerHTML = publicHistory.map(item => `
            <div class="border-b border-clock-border/30 pb-2 mb-2 text-xs">
                <span class="text-clock-gold font-bold">[${item.sender || 'Système'}]</span> 
                <span class="text-gray-300">${item.content || JSON.stringify(item)}</span>
            </div>
        `).join('');
    }

    // 2. Gestion des historiques personnels des agents (Menu + Détail)
    const agentHistories = data.agent_histories || data.llm_memories || {};
    const agentIds = Object.keys(agentHistories);
    const tabsContainer = document.getElementById('agents-tabs-container');

    if (agentIds.length === 0) {
        tabsContainer.innerHTML = `<span class="italic text-gray-500 text-xs">Aucun agent disponible.</span>`;
        document.getElementById('agent-detail-container').innerHTML = `<span class="italic text-gray-500 text-xs">Aucune mémoire disponible.</span>`;
        return;
    }

    // Sélectionner par défaut le premier agent si aucun n'est sélectionné ou si l'ancien n'existe plus
    if (!selectedAgentId || !agentIds.includes(selectedAgentId)) {
        selectedAgentId = agentIds[0];
    }

    // Rendu du menu latéral des agents
    tabsContainer.innerHTML = agentIds.map(agentId => {
        const isActive = agentId === selectedAgentId;
        const activeClass = isActive 
            ? 'bg-clock-gold/20 border-clock-gold text-clock-gold font-bold shadow-md' 
            : 'bg-clock-dark/50 border-clock-border/40 text-gray-300 hover:bg-clock-panel';
        
        const count = Array.isArray(agentHistories[agentId]) ? agentHistories[agentId].length : 0;

        return `
            <button onclick="selectAgent('${agentId}')" class="w-full text-left px-3 py-2.5 rounded-xl border text-xs transition flex items-center justify-between ${activeClass}">
                <span class="truncate">${agentId}</span>
                <span class="text-[10px] text-gray-400 ml-1 bg-black/30 px-1.5 py-0.5 rounded">${count}</span>
            </button>
        `;
    }).join('');

    // Rendu du détail de l'agent actif
    renderAgentDetail(selectedAgentId, agentHistories);
}

function selectAgent(agentId) {
    selectedAgentId = agentId;
    if (currentAdminData) {
        // Re-render pour mettre à jour les classes CSS des boutons du menu
        renderDashboard(currentAdminData);
    }
}

function renderAgentDetail(agentId, agentHistories) {
    const detailContainer = document.getElementById('agent-detail-container');
    const messages = agentHistories[agentId] || [];

    if (messages.length === 0) {
        detailContainer.innerHTML = `
            <div class="space-y-2">
                <div class="text-xs font-bold text-clock-gold pb-2 border-b border-clock-border/40">Agent : ${agentId}</div>
                <span class="italic text-gray-500 text-xs">La mémoire de cet agent est vide.</span>
            </div>
        `;
        return;
    }

    detailContainer.innerHTML = `
        <div class="space-y-3">
            <div class="flex items-center justify-between font-bold text-clock-gold text-xs border-b border-clock-border/40 pb-2">
                <span>Mémoire de l'agent : ${agentId}</span>
                <span class="text-[10px] text-gray-400 font-normal">${messages.length} messages en contexte</span>
            </div>
            <div class="space-y-2 max-h-[380px] overflow-y-auto pr-2 text-xs">
                ${messages.map(msg => `
                    <div class="p-2.5 rounded-xl bg-clock-panel/60 border border-clock-border/40 space-y-1">
                        <div class="text-[10px] font-bold text-gray-400 uppercase tracking-wider flex justify-between">
                            <span>${msg.role || 'Inconnu'}</span>
                        </div>
                        <div class="text-gray-300 whitespace-pre-wrap">${msg.content || JSON.stringify(msg)}</div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
}