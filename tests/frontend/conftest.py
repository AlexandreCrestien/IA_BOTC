"""Fixtures des tests du frontend (Playwright + pytest).

- Le dossier static/ est servi par un petit serveur HTTP local (aucun backend lancé).
- Le serveur WebSocket du jeu est simulé par Playwright (page.route_web_socket) :
  les tests envoient de faux messages serveur et lisent ce que le front envoie.
- Tailwind (CDN) et Google Fonts sont remplacés localement : les tests tournent
  hors ligne et ne dépendent pas d'un service externe. Seul l'utilitaire `hidden`
  de Tailwind est recréé, car le front s'en sert pour afficher / masquer.
- Toute erreur JavaScript non interceptée dans la page fait échouer le test.

Lancer :  python -m pytest tests/frontend -q        (ajouter --headed pour voir le navigateur)
"""
import functools
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

STATIC_DIR = Path(__file__).resolve().parents[2] / "static"

PLAYER = "Lady Vesper"
AGENTS = ["Lord Ashcombe", "Mère Grimsby", "Dr. Thorne", "Révérend Hale", "Miss Pemberton"]
ALL_PLAYERS = AGENTS[:3] + [PLAYER] + AGENTS[3:]

# Remplace le CDN Tailwind : config vide + utilitaires indispensables au comportement
TAILWIND_STUB = """
window.tailwind = {};
document.head.insertAdjacentHTML('beforeend',
  '<style>.hidden{display:none}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}</style>');
"""


def pytest_collection_modifyitems(session, config, items):
    """Exécute les tests du frontend après tous les autres.

    L'API synchrone de Playwright laisse une boucle asyncio active jusqu'à la fin de la
    session : les tests backend qui appellent asyncio.run() échoueraient s'ils passaient après.
    """
    frontend_dir = Path(__file__).parent
    items.sort(key=lambda item: frontend_dir in Path(str(item.path)).parents)


def pytest_configure(config):
    # Avertissement interne au plugin pytest-base-url (dépendance de pytest-playwright), pas à nos tests
    config.addinivalue_line("filterwarnings", "ignore:Session-scoped fixtures defined as instance methods")


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="session")
def static_url():
    """URL d'un serveur HTTP local qui sert static/ pendant toute la session de tests."""
    handler = functools.partial(_QuietHandler, directory=str(STATIC_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def page(page: Page):
    """Page Playwright sans dépendance réseau, qui échoue sur toute erreur JS."""
    page.route("https://cdn.tailwindcss.com/**",
               lambda route: route.fulfill(body=TAILWIND_STUB, content_type="application/javascript"))
    page.route(lambda url: "fonts.googleapis.com" in url or "fonts.gstatic.com" in url,
               lambda route: route.abort())
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    yield page
    assert not errors, f"Erreurs JavaScript dans la page : {errors}"


class FakeServer:
    """Serveur WebSocket simulé : envoie des messages au front, mémorise ce qu'il reçoit."""

    def __init__(self, page: Page):
        self.page = page
        self.route = None
        self.received = []
        page.route_web_socket("**/ws/**", self._on_connect)

    def _on_connect(self, ws_route):
        self.route = ws_route
        ws_route.on_message(lambda message: self.received.append(json.loads(message)))

    def send(self, **message):
        self.route.send(json.dumps(message))

    def close(self):
        self.route.close()

    def actions(self, name):
        """Payloads des actions `name` envoyées par le front."""
        return [m["payload"] for m in self.received if m["action"] == name]

    def wait_for(self, name):
        """Attend (1 s max) que le front ait envoyé l'action `name` et renvoie son dernier payload."""
        for _ in range(50):
            if self.actions(name):
                return self.actions(name)[-1]
            self.page.wait_for_timeout(20)
        raise AssertionError(f"Action '{name}' jamais envoyée (reçu : {self.received})")


@pytest.fixture
def server(page):
    return FakeServer(page)


def players(dead=()):
    return [{"id": n, "name": n, "alive": n not in dead, "has_vote": True} for n in ALL_PLAYERS]


@pytest.fixture
def game(page, server, static_url):
    """Joueur connecté (via le vrai formulaire d'accueil) à une partie de 6 joueurs, en journée."""
    page.goto(f"{static_url}/index.html")
    page.fill("#welcome-player-id", PLAYER)
    page.press("#welcome-player-id", "Enter")
    expect(page.locator("#screen-game")).to_be_visible()
    server.send(type="game_state", state={"phase": "discussion", "day": 2, "aliveCount": 5,
                                          "players": players(dead=["Dr. Thorne"])})
    expect(page.locator("#game-phase")).to_have_text("Jour")
    return page
