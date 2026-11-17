"""Historique des joueurs.
- save_histories : instantané de la mémoire de chaque joueur à la fin d'un tour.
- RecordingAgent : enregistre chaque appel d'une IA (contexte reçu, arguments, réponse ou erreur)."""
from pathlib import Path


def save_histories(memory, state, folder) -> None:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for player in state.players:
        lines = [
            f"# {player.name} ({player.id}) - {player.role.name_FR}",
            "",
            memory.context_for(player.id),
        ]
        (folder / f"{player.name}.txt").write_text("\n".join(lines), encoding="utf-8")


class RecordingAgent:
    """Enveloppe un agent IA sans changer son code. Chaque appel est écrit dans un fichier
    avec le contexte reçu au moment de l'appel, les arguments et la réponse (ou l'erreur)."""

    def __init__(self, agent, memory, folder):
        self._agent = agent
        self._memory = memory
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        self._file = folder / f"appels_{agent.name}.txt"
        self._file.write_text(
            f"# {agent.name} ({agent.player_id}) - {agent.role_name}\n\n"
            f"## Prompt système\n{agent._build_system_prompt()}\n",
            encoding="utf-8",
        )

    def __getattr__(self, name):
        return getattr(self._agent, name)

    def _record(self, method, args, kwargs, context, outcome):
        block = (
            f"\n=== {method} ===\n"
            f"arguments : {args} {kwargs}\n"
            f"--- contexte reçu ---\n{context}\n"
            f"--- {outcome} ---\n"
        )
        with self._file.open("a", encoding="utf-8") as f:
            f.write(block)

    async def _call(self, method, *args, **kwargs):
        context = self._memory.context_for(self._agent.player_id)
        try:
            result = await getattr(self._agent, method)(*args, **kwargs)
        except Exception as exc:
            self._record(method, args, kwargs, context, f"ERREUR : {exc!r}")
            raise
        self._record(method, args, kwargs, context, f"réponse : {result!r}")
        return result

    async def night_action(self, *args, **kwargs):
        return await self._call("night_action", *args, **kwargs)

    async def vote(self, *args, **kwargs):
        return await self._call("vote", *args, **kwargs)

    async def speak_public(self, *args, **kwargs):
        return await self._call("speak_public", *args, **kwargs)

    async def speak_private(self, *args, **kwargs):
        return await self._call("speak_private", *args, **kwargs)