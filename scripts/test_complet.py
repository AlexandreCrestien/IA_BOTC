"""Test complet de la chaîne front <-> serveur <-> moteur.

Ce que le script vérifie, sur une partie entière jouée en mode simulé :
- chaque message reçu par le front : type connu, champs obligatoires, phases valides ;
- les cas d'erreur (JSON invalide, action inconnue, champ en trop, message vide, action hors phase) ;
- les demandes d'action (nuit, vote, discussion) et leur validation
  (nombre de cibles, cible inconnue, se désigner soi-même) ;
- la reconnexion en pleine nuit (rôle et demande en attente renvoyés) ;
- la phase affichée pendant la discussion des IA ;
- les messages publics et privés (relais, expéditeurs affichés par leur nom, réponses des IA) ;
- les infos de nuit selon le rôle, les résultats de nuit et de vote, la fin de partie.

Usage, depuis la racine du projet :
    python scripts/test_complet.py
    python scripts/test_complet.py --seed 42 --log scripts/logs/partie.jsonl

Code de sortie : 0 si toutes les vérifications passent, 1 sinon.
"""
import argparse
import json
import os
import sys
import time
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["SIMULATE_LLM"] = "1"  # doit être défini avant l'import de llm_client

from fastapi.testclient import TestClient  # noqa: E402

from backend import llm_client  # noqa: E402
from backend.server import game_runner  # noqa: E402
from backend.server.app import app  # noqa: E402

llm_client.CALL_PAUSE_SECONDS = 0  # pas de pause entre les appels simulés

HUMAN = game_runner.GAME_CONFIG["human_id"]
RECV_TIMEOUT = 30  # secondes sans aucun message avant de déclarer la partie bloquée
MAX_MESSAGES = 20000  # garde-fou contre une boucle
MAX_PRIVATE_MESSAGES = 3

PHASES = {"nuit", "discussion", "vote"}
KINDS_PHASE = {"nuit": "nuit", "vote": "vote", "discussion": "discussion"}
ROLES_FR = {"Diablotin", "Empoisonneur", "Voyante", "Moine", "Détective", "Majordome"}
EVIL_ROLES = {"Diablotin", "Empoisonneur"}
WINNERS = {"Villageois", "Démons"}

# Champs obligatoires par type de message, d'après connection.js (handleServerMessage)
REQUIRED = {
    "role_assigned": ("role_name", "description"),
    "game_state": ("state",),
    "action_request": ("kind", "candidates"),
    "chat": ("channel_id", "sender", "content"),
    "private_channel_opened": ("channel_id", "members", "text"),
    "vote_result": ("turn", "executed", "votes"),
    "night_result": ("turn", "dead_player"),
    "night_info": ("turn", "info"),
    "night_action_ack": ("text",),
    "game_over": ("winner", "details"),
    "error": ("data",),
    "announcement": ("text",),
    "phase_update": ("phase",),
}


class Stalled(Exception):
    """La partie n'envoie plus rien : blocage."""


class Report:
    def __init__(self):
        self.passed = 0
        self.failed = []
        self.notes = []

    def check(self, condition, name, detail=""):
        if condition:
            self.passed += 1
        else:
            self.failed.append(name + (f" -- {detail}" if detail else ""))

    def note(self, text):
        self.notes.append(text)


class Session:
    """Connexion WebSocket de test, sur le même chemin que le front : /ws/<pseudo>."""

    def __init__(self, client: TestClient, player_id: str):
        self.client = client
        self.player_id = player_id
        self.cm = None
        self.ws = None
        self.pool = ThreadPoolExecutor(max_workers=1)

    def open(self) -> None:
        self.cm = self.client.websocket_connect(f"/ws/{self.player_id}")
        self.ws = self.cm.__enter__()

    def close(self) -> None:
        if self.cm is not None:
            self.cm.__exit__(None, None, None)
        self.cm = None
        self.ws = None
        time.sleep(0.5)  # laisse le serveur traiter la déconnexion avant une éventuelle reconnexion

    def send(self, action: str, payload: dict | None = None) -> None:
        self.ws.send_text(json.dumps({"action": action, "payload": payload or {}}))

    def send_raw(self, text: str) -> None:
        self.ws.send_text(text)

    def recv(self) -> dict:
        future = self.pool.submit(self.ws.receive_json)
        try:
            return future.result(timeout=RECV_TIMEOUT)
        except FutureTimeout as exc:
            raise Stalled(f"aucun message pendant {RECV_TIMEOUT} s") from exc


def negative_tests(client: TestClient, report: Report) -> None:
    """Cas d'erreur, sur une connexion qui n'a pas de partie : aucune demande en cours."""
    session = Session(client, "Testeur")
    session.open()
    try:
        session.send_raw("{pas du json")
        msg = session.recv()
        report.check(msg.get("type") == "error" and "JSON" in str(msg.get("data")),
                     "JSON invalide refusé", str(msg))

        session.send_raw(json.dumps({"action": "action_inconnue", "payload": {}}))
        msg = session.recv()
        report.check(msg.get("type") == "error", "action inconnue refusée", str(msg))

        session.send_raw(json.dumps({"action": "send_chat",
                                     "payload": {"channel_id": "public", "content": "x", "en_trop": 1}}))
        msg = session.recv()
        report.check(msg.get("type") == "error", "champ inconnu refusé", str(msg))

        session.send("send_chat", {"channel_id": "public", "content": ""})
        msg = session.recv()
        report.check(msg.get("type") == "error", "message vide refusé", str(msg))

        session.send("submit_vote", {"target_id": None})
        msg = session.recv()
        report.check(msg.get("type") == "error" and "moment" in str(msg.get("data")),
                     "vote hors demande refusé", str(msg))

        session.send("submit_night_action", {"targets": [HUMAN]})
        msg = session.recv()
        report.check(msg.get("type") == "error", "action de nuit hors demande refusée", str(msg))

        session.send("request_whisper", {"targets": ["p1"]})
        msg = session.recv()
        report.check(msg.get("type") == "error", "discussion privée hors demande refusée", str(msg))
    finally:
        session.close()


class Game:
    """Joue le joueur humain comme le front le ferait, et vérifie chaque message reçu."""

    def __init__(self, session: Session, report: Report, log_file):
        self.session = session
        self.report = report
        self.log_file = log_file
        self.counts = Counter()
        self.messages = 0
        self.names = {}
        self.phase = None
        self.role = None
        self.probes = set()
        self.reconnecting = None
        self.votes_cast = 0
        self.private_channel = None
        self.private_pending = False
        self.private_left_seen = []
        self.private_sent = 0
        self.public_sent = 0
        self.echo_seen = 0
        self.ai_public = 0
        self.ai_private_replies = 0
        self.night_infos = []
        self.allies = None
        self.night_acks = 0
        self.votes = []
        self.night_results = []
        self.errors = []
        self.game_over = None

    # ---------- boucle de réception ----------

    def play(self) -> None:
        while self.game_over is None:
            self.dispatch(self.session.recv())

    def wait_for(self, types: set[str]) -> dict:
        while True:
            msg = self.session.recv()
            self.dispatch(msg)
            if msg.get("type") in types:
                return msg

    def send_and_wait(self, action: str, payload: dict, types: set[str]) -> dict:
        self.session.send(action, payload)
        return self.wait_for(types)

    def dispatch(self, msg: dict) -> None:
        self.messages += 1
        if self.messages > MAX_MESSAGES:
            raise Stalled("trop de messages : boucle probable")
        kind = msg.get("type")
        self.counts[kind] += 1
        if self.log_file:
            self.log_file.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self.check_shape(msg)
        handler = getattr(self, "on_" + str(kind), None)
        if handler:
            handler(msg)

    def check_shape(self, msg: dict) -> None:
        kind = msg.get("type")
        if kind not in REQUIRED:
            self.report.check(False, "type de message connu du front", str(kind))
            return
        missing = [field for field in REQUIRED[kind] if field not in msg]
        self.report.check(not missing, f"message « {kind} » complet", f"champs manquants : {missing}")

    # ---------- messages reçus du serveur ----------

    def on_role_assigned(self, msg: dict) -> None:
        self.role = msg.get("role_name")
        self.report.check(self.role in ROLES_FR, "rôle connu du front", str(self.role))

    def on_game_state(self, msg: dict) -> None:
        state = msg.get("state", {})
        players = state.get("players", [])
        self.phase = state.get("phase")
        self.report.check(self.phase in PHASES, "phase envoyée connue du front", str(self.phase))
        self.report.check(len(players) == 6, "6 joueurs dans la liste", str(len(players)))
        alive = sum(1 for p in players if p.get("alive"))
        self.report.check(alive == state.get("aliveCount"), "aliveCount égal aux joueurs vivants",
                          f"{alive} vivants, aliveCount={state.get('aliveCount')}")
        self.names = {p["id"]: p["name"] for p in players if "id" in p and "name" in p}
        self.report.check(HUMAN in self.names, "le joueur humain figure dans la liste")

    def on_night_info(self, msg: dict) -> None:
        self.night_infos.append(msg)
        self.report.check(self.phase == "nuit", "info de nuit reçue pendant la nuit", str(self.phase))
        if msg.get("allies") is not None:
            self.allies = msg["allies"]
            self.report.check(self.role in EVIL_ROLES, "alliés révélés seulement au camp du mal", str(self.role))

    def on_night_result(self, msg: dict) -> None:
        self.night_results.append(msg)
        dead = msg.get("dead_player")
        self.report.check(dead is None or dead in self.names, "mort de nuit identifiable", str(dead))

    def on_vote_result(self, msg: dict) -> None:
        self.votes.append(msg)
        executed = msg.get("executed")
        self.report.check(executed is None or executed in self.names, "joueur exécuté identifiable", str(executed))
        self.report.check(all({"voter", "target"} <= set(v) for v in msg.get("votes", [])),
                          "bulletins de vote complets (voter, target)")

    def on_night_action_ack(self, msg: dict) -> None:
        self.night_acks += 1

    def on_error(self, msg: dict) -> None:
        self.errors.append(msg.get("data"))

    def on_game_over(self, msg: dict) -> None:
        self.game_over = msg
        self.report.check(msg.get("winner") in WINNERS, "libellé de victoire lisible en français",
                          str(msg.get("winner")))

    def on_announcement(self, msg: dict) -> None:
        text = str(msg.get("text", ""))
        if "message public" in text:
            # Le moteur attend le message public de l'humain
            self.public_sent += 1
            self.session.send("send_chat", {"channel_id": "public", "content": "Bonjour, je suis l'humain."})
        elif "privé(s)" in text:
            # Le moteur attend un message privé : « Il vous reste N message(s) privé(s) ... »
            left = int(text.split("Il vous reste ")[1].split()[0])
            self.report.check(left == MAX_PRIVATE_MESSAGES - len(self.private_left_seen),
                              "compte des messages privés restants", f"annoncé {left}")
            self.private_left_seen.append(left)
            self.send_private_message()

    def on_private_channel_opened(self, msg: dict) -> None:
        self.private_channel = msg["channel_id"]
        self.private_left_seen = []
        self.report.check(HUMAN in msg["members"], "salon privé : le joueur humain est membre")
        partners = [m for m in msg["members"] if m != HUMAN]
        self.report.check(all(m in self.names.values() for m in partners),
                          "salon privé : membres affichés par leur nom",
                          f"reçu {partners}, attendu {list(self.names.values())}")
        if self.private_pending:
            self.private_pending = False
            self.send_private_message()

    def on_chat(self, msg: dict) -> None:
        sender, channel = msg.get("sender"), msg.get("channel_id")
        if sender == HUMAN:
            if channel == "public":
                self.echo_seen += 1
            return
        if sender == "Grimoire":
            return
        self.report.check(sender in self.names.values(), "expéditeur affiché par son nom",
                          f"« {sender} » reçu, le front affichera cet identifiant")
        if channel == "public":
            self.ai_public += 1
            self.report.check(self.phase == "discussion", "discussion des IA affichée en phase « discussion »",
                              f"phase reçue : {self.phase}")
        elif str(channel).startswith("whisper_"):
            self.ai_private_replies += 1

    def on_phase_update(self, msg: dict) -> None:
        pass

    # ---------- demandes d'action ----------

    def on_action_request(self, msg: dict) -> None:
        kind = msg.get("kind")
        self.report.check(kind in KINDS_PHASE, "kind d'action connu", str(kind))
        if kind not in KINDS_PHASE:
            return
        self.report.check(KINDS_PHASE[kind] == self.phase, f"demande « {kind} » pendant sa phase",
                          f"phase reçue : {self.phase}")
        if self.reconnecting is not None:
            self.report.check(list(msg.get("candidates", [])) == self.reconnecting,
                              "demande en attente renvoyée à la reconnexion")
            self.reconnecting = None
        if kind == "nuit":
            self.answer_night(msg)
        elif kind == "vote":
            self.answer_vote(msg)
        else:
            self.answer_discussion(msg)

    def answer_night(self, msg: dict) -> None:
        cands = list(msg.get("candidates", []))
        count = int(msg.get("max_targets", 1))
        if "reconnect" not in self.probes:
            self.probes.add("reconnect")
            self.reconnect(cands)
            return
        if "night" not in self.probes:
            self.probes.add("night")
            wrong = cands[: count + 1] if len(cands) > count else []
            reply = self.send_and_wait("submit_night_action", {"targets": wrong},
                                       {"error", "night_action_ack"})
            self.report.check(reply.get("type") == "error", "nuit : mauvais nombre de cibles refusé",
                              "le serveur accepte, le moteur remplace le choix au hasard")
            if reply.get("type") != "error":
                return
        good = cands[:count]
        reply = self.send_and_wait("submit_night_action", {"targets": good}, {"night_action_ack", "error"})
        self.report.check(reply.get("type") == "night_action_ack", "nuit : choix valide confirmé", str(reply))

    def reconnect(self, cands: list) -> None:
        """Coupure en pleine nuit : à la reconnexion, le rôle et la demande doivent revenir."""
        roles_before = self.counts["role_assigned"]
        self.session.close()
        self.session.open()
        self.reconnecting = cands
        self.wait_for({"action_request"})
        self.report.check(self.counts["role_assigned"] > roles_before, "rôle renvoyé à la reconnexion")

    def answer_vote(self, msg: dict) -> None:
        cands = list(msg.get("candidates", []))
        if "vote" not in self.probes:
            self.probes.add("vote")
            reply = self.send_and_wait("submit_vote", {"target_id": "__inconnu__"}, {"error", "announcement"})
            self.report.check(reply.get("type") == "error", "vote : cible inconnue refusée",
                              "le serveur accepte, le moteur compte une abstention")
            if reply.get("type") != "error":
                return
        target = cands[0] if cands and self.votes_cast % 2 == 0 else None  # alterne vote et abstention
        self.votes_cast += 1
        reply = self.send_and_wait("submit_vote", {"target_id": target}, {"announcement", "error"})
        self.report.check(reply.get("type") == "announcement", "vote valide accepté", str(reply))

    def answer_discussion(self, msg: dict) -> None:
        cands = list(msg.get("candidates", []))
        self.private_channel = None
        if "whisper" not in self.probes:
            self.probes.add("whisper")
            reply = self.send_and_wait("request_whisper", {"targets": [HUMAN]},
                                       {"error", "private_channel_opened"})
            self.report.check(reply.get("type") == "error", "discussion : se parler à soi-même refusé",
                              "le serveur ouvre un salon avec soi-même")
            if reply.get("type") != "error":
                return
        if not cands:
            return
        reply = self.send_and_wait("request_whisper", {"targets": [cands[0]]},
                                   {"error", "private_channel_opened"})
        self.report.check(reply.get("type") == "private_channel_opened", "discussion : interlocuteur valide accepté",
                          str(reply))

    def send_private_message(self) -> None:
        if self.private_channel is None:
            self.private_pending = True  # le salon n'est pas encore ouvert côté front : on attend
            return
        self.private_sent += 1
        self.session.send("send_chat", {
            "channel_id": self.private_channel,
            "content": f"Message privé de test n°{self.private_sent}.",
        })

    # ---------- bilan ----------

    def final_checks(self) -> None:
        r = self.report
        texts = [str(m.get("info", "")) for m in self.night_infos]

        r.check(self.game_over is not None, "la partie se termine par game_over")
        r.check(self.night_acks >= 1, "choix de nuit confirmés (night_action_ack)", str(self.night_acks))
        r.check(self.ai_public > 0, "messages publics des IA reçus par le front")
        r.check(self.echo_seen == self.public_sent, "message public de l'humain relayé",
                f"envoyés {self.public_sent}, relayés {self.echo_seen}")
        if self.private_sent:
            r.check(self.ai_private_replies > 0, "réponses des IA dans le salon privé")
        r.check(len(self.night_results) == len(self.votes), "un night_result et un vote_result par tour",
                f"{len(self.night_results)} nuits, {len(self.votes)} votes")
        r.check(bool(self.night_results), "au moins une nuit complète reçue")

        r.check((self.allies is not None) == (self.role in EVIL_ROLES),
                "alliés révélés si et seulement si camp du mal", f"rôle {self.role}")
        if self.role in EVIL_ROLES:
            r.check(any("Première nuit" in t for t in texts), "camp du mal : information de première nuit")
        if self.role == "Voyante":
            r.check(any("Parmi" in t for t in texts), "Voyante : réponse du sondage reçue")
        if self.role == "Détective":
            r.check(any("Première nuit : parmi" in t for t in texts), "Détective : information reçue")

        if "reconnect" not in self.probes:
            r.note("reconnexion non testée : aucune demande de nuit pour ce rôle")
        if "vote" not in self.probes:
            r.note("validation du vote non testée : joueur humain sans vote")
        if self.errors:
            r.note(f"erreurs reçues pendant la partie (hors tests) : {self.errors}")


def summary(game: Game, report: Report, args, elapsed: float) -> None:
    print("=" * 64)
    print(f"Partie : seed={args.seed}, rôle du joueur humain : {game.role}, "
          f"tours joués : {len(game.votes)}, gagnant : {game.game_over and game.game_over.get('winner')}")
    print(f"Durée : {elapsed:.1f} s, messages reçus : {game.messages}")
    print("Types reçus :", dict(game.counts))
    print(f"Vérifications réussies : {report.passed}")
    for note in report.notes:
        print("NOTE :", note)
    if report.failed:
        print(f"ÉCHECS ({len(report.failed)}) :")
        for failure in report.failed:
            print("  -", failure)
    else:
        print("Tout passe.")
    print("=" * 64)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=1, help="graine de la partie (rôles, personnalités)")
    parser.add_argument("--log", type=Path, help="fichier JSON Lines où écrire chaque message reçu")
    args = parser.parse_args()

    game_runner.GAME_CONFIG["seed"] = args.seed
    report = Report()
    client = TestClient(app)

    negative_tests(client, report)

    log_file = None
    if args.log:
        args.log.parent.mkdir(parents=True, exist_ok=True)
        log_file = args.log.open("w", encoding="utf-8")

    session = Session(client, HUMAN)
    game = Game(session, report, log_file)
    started = time.time()
    try:
        session.open()
        game.play()
    except Stalled as exc:
        report.check(False, "la partie avance sans blocage", str(exc))
    except Exception as exc:  # noqa: BLE001 : toute erreur doit apparaître dans le bilan
        report.check(False, "aucune exception pendant la partie", repr(exc))
        traceback.print_exc()
    finally:
        try:
            session.close()
        except Exception:  # noqa: BLE001
            pass
        if log_file:
            log_file.close()

    game.final_checks()
    summary(game, report, args, time.time() - started)
    sys.stdout.flush()
    # os._exit : coupe le thread de réception resté bloqué en cas de blocage
    os._exit(1 if report.failed else 0)


if __name__ == "__main__":
    main()