"""Conversation privée simulée entre deux agents, pendant le salon privé du joueur humain.

Les deux agents ne se parlent pas vraiment (trop d'appels LLM) :
- le duo est tiré au sort dans le code (aucun appel LLM), avec des poids qui tiennent compte
  des rôles (le camp du mal se concerte, les rôles d'information partagent) et des entretiens
  passés (un duo qui revient trop souvent serait un indice flagrant pour le joueur) ;
- la conversation est annoncée sur la place publique : c'est un indice pour le joueur ;
- un seul appel LLM écrit un résumé par agent, de son point de vue, ajouté à sa mémoire personnelle.
"""
import logging
import random
from itertools import combinations
from typing import Optional

from pydantic import BaseModel, Field

from backend.llm_client import ask_llm_json
from backend.memory_manager import MemoryManager, game_master
from backend.models import Alignement, EventType, GameState, RoleKey

logger = logging.getLogger(__name__)

# Poids d'un duo (1 par défaut)
EVIL_PAIR_WEIGHT = 3.0    # Démon + Sbire : ils doivent se concerter sur leur stratégie
INFO_PAIR_WEIGHT = 1.5    # duo avec un rôle du bien qui a des informations à partager
INFO_ROLES = {RoleKey.PSYCHIC, RoleKey.DETECTIVE}
SOLICITATION_PENALTY = 0.25  # par entretien passé de chacun des deux agents

NEUTRAL_SUMMARY = "Vous avez échangé quelques banalités, sans rien apprendre de décisif."


def pair_weight(state: GameState, pair: frozenset[str], past: list[tuple[int, frozenset[str]]], turn: int) -> float:
    """Poids d'un duo pour le tirage. past : entretiens passés entre agents seuls (tour, duo).

    - duo qui s'est entretenu au tour précédent : exclu (deux soirs de suite, trop flagrant) ;
    - duo du mal ×EVIL_PAIR_WEIGHT, duo avec la Voyante ou le Détective ×INFO_PAIR_WEIGHT ;
    - chaque entretien passé du même duo divise le poids par (1 + n)² ;
    - les agents déjà très sollicités sont un peu moins choisis.
    """
    if any(t == turn - 1 and met == pair for t, met in past):
        return 0.0
    roles = [state.player(pid).role for pid in pair]
    weight = 1.0
    if all(role.alignment == Alignement.MAUVAIS for role in roles):
        weight *= EVIL_PAIR_WEIGHT
    elif any(role.name_EN in INFO_ROLES for role in roles):
        weight *= INFO_PAIR_WEIGHT
    times_together = sum(1 for _, met in past if met == pair)
    weight /= (1 + times_together) ** 2
    solicited = sum(1 for _, met in past for pid in pair if pid in met)
    weight /= 1 + SOLICITATION_PENALTY * solicited
    return weight


def choose_whisper_pair(state: GameState, candidates: list[str], human_id: str,
                        memory: MemoryManager, rng: random.Random) -> Optional[tuple[str, str]]:
    """Tire au sort le duo d'agents qui s'entretient en privé. candidates : agents disponibles
    (vivants ou morts, hors interlocuteurs du joueur). None si aucun duo n'est possible."""
    past = [(t, met) for t, met in memory.meetings() if human_id not in met]
    pairs = [frozenset(p) for p in combinations(sorted(candidates), 2)]
    weights = [pair_weight(state, pair, past, memory.turn) for pair in pairs]
    if not pairs or sum(weights) == 0:
        return None
    chosen = rng.choices(pairs, weights=weights)[0]
    return tuple(sorted(chosen))


class WhisperSummaries(BaseModel):
    resume_1: str = Field(min_length=1)
    resume_2: str = Field(min_length=1)


def _summary_messages(state: GameState, memory: MemoryManager, pair: tuple[str, str]) -> list[dict]:
    first, second = pair
    sheets = []
    for number, pid in ((1, first), (2, second)):
        role = state.player(pid).role
        camp = "camp du mal" if role.alignment == Alignement.MAUVAIS else "camp du bien"
        sheets.append(
            f"## Joueur {number} : {memory.name_of(pid)}\n"
            f"Vrai rôle : {role.name_FR} ({camp}). {role.description}\n"
            f"Ce que {memory.name_of(pid)} sait (son historique) :\n{memory.context_for(pid)}"
        )
    a, b = memory.name_of(first), memory.name_of(second)
    system = (
        "Tu es le narrateur d'une partie de Blood on the Clocktower jouée par des IA. "
        f"{a} et {b} viennent d'avoir une conversation privée. Tu ne l'écris pas en entier : "
        "tu en écris un résumé pour chacun des deux, de son propre point de vue."
    )
    instruction = (
        "\n\n".join(sheets) + "\n\n# CONSIGNES\n"
        f"- resume_1 est le souvenir de {a}, resume_2 celui de {b}. Écris à la deuxième personne "
        f"(« Tu as dit à {b} que… », « {b} t'a confié que… »), 2 à 4 phrases chacun.\n"
        "- Un joueur du camp du mal ne révèle jamais son vrai rôle à un joueur du bien : il bluffe "
        "de façon cohérente avec ce qu'il a déjà prétendu.\n"
        "- Deux joueurs du camp du mal se concertent vraiment : stratégie, faux rôles, cible de la nuit.\n"
        "- Un joueur du bien partage sincèrement ce qu'il croit savoir (même si c'est faux).\n"
        "- Chaque résumé ne contient que ce que ce joueur peut savoir : jamais le vrai rôle de l'autre, "
        "sauf s'il le connaissait déjà ou si l'autre le lui a dit sincèrement. Ce que l'autre a prétendu "
        "est rapporté comme une affirmation, pas comme un fait.\n"
        'Réponds uniquement en JSON : {"resume_1": "...", "resume_2": "..."}.'
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": instruction}]


async def write_whisper_summaries(state: GameState, memory: MemoryManager, pair: tuple[str, str]) -> None:
    """Un seul appel LLM : un résumé par agent, ajouté à sa seule mémoire personnelle.
    Si l'appel échoue, chacun garde un souvenir neutre (la conversation a été annoncée publiquement)."""
    first, second = pair
    try:
        result = await ask_llm_json("capable", _summary_messages(state, memory, pair), WhisperSummaries)
        summaries = (result.resume_1, result.resume_2)
    except Exception:
        logger.exception("Résumés de la conversation privée %s / %s impossibles", first, second)
        summaries = (NEUTRAL_SUMMARY, NEUTRAL_SUMMARY)
    for pid, other, summary in ((first, second, summaries[0]), (second, first, summaries[1])):
        memory.add_personal(EventType.private_summary, game_master,
                            f"Conversation privée avec {memory.name_of(other)} : {summary}", pid)
    logger.info("Conversation privée simulée entre %s et %s", first, second)
