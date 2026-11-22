"""Écran d'accueil : connexion au serveur."""
from playwright.sync_api import expect

from conftest import PLAYER

# WebSocket qui échoue aussitôt, comme un serveur éteint
FAILING_WEBSOCKET = """
window.WebSocket = class {
    static CONNECTING = 0; static OPEN = 1; static CLOSING = 2; static CLOSED = 3;
    constructor() { this.readyState = 0; setTimeout(() => { this.readyState = 3; this.onclose && this.onclose({}); }, 10); }
    send() {}
    close() {}
};
"""


def test_empty_pseudo_shows_error(page, static_url):
    page.goto(f"{static_url}/index.html")
    page.click("#welcome-join-btn")
    expect(page.locator("#welcome-error")).to_have_text("Veuillez entrer un pseudo.")
    expect(page.locator("#screen-welcome")).to_be_visible()


def test_enter_joins_the_game(page, server, static_url):
    page.goto(f"{static_url}/index.html")
    page.fill("#welcome-player-id", PLAYER)
    page.press("#welcome-player-id", "Enter")

    expect(page.locator("#screen-game")).to_be_visible()
    expect(page.locator("#screen-welcome")).to_be_hidden()
    expect(page.locator("#connection-status")).to_have_text("Connecté")
    assert server.route.url.endswith("/ws/Vesper")


def test_unreachable_server_shows_error_and_reenables_button(page, static_url):
    page.add_init_script(FAILING_WEBSOCKET)
    page.goto(f"{static_url}/index.html")
    page.fill("#welcome-player-id", PLAYER)
    page.click("#welcome-join-btn")

    expect(page.locator("#welcome-error")).to_contain_text("Impossible de joindre le serveur")
    expect(page.locator("#welcome-join-btn")).to_be_enabled()
    expect(page.locator("#screen-game")).to_be_hidden()


def test_refused_connection_shows_reason_on_welcome(page, server, static_url):
    server.refuse("Une partie est déjà en cours avec un autre joueur.")
    page.goto(f"{static_url}/index.html")
    page.fill("#welcome-player-id", PLAYER)
    page.click("#welcome-join-btn")

    expect(page.locator("#welcome-error")).to_have_text("Une partie est déjà en cours avec un autre joueur.")
    expect(page.locator("#screen-game")).to_be_hidden()  # pas de passage par l'écran de jeu
    expect(page.locator("#welcome-join-btn")).to_be_enabled()


def test_pseudo_with_forbidden_characters_is_refused_before_connecting(page, server, static_url):
    page.goto(f"{static_url}/index.html")
    page.fill("#welcome-player-id", "Jean?Paul")
    page.press("#welcome-player-id", "Enter")
    expect(page.locator("#welcome-error")).to_contain_text("lettres, des chiffres, des tirets")
    expect(page.locator("#screen-welcome")).to_be_visible()
    assert server.route is None  # aucune connexion tentée


def test_pseudo_is_limited_to_20_characters(page, static_url):
    page.goto(f"{static_url}/index.html")
    page.fill("#welcome-player-id", "a" * 30)
    expect(page.locator("#welcome-player-id")).to_have_value("a" * 20)


def test_accented_pseudo_with_apostrophe_is_encoded_in_the_address(page, server, static_url):
    page.goto(f"{static_url}/index.html")
    page.fill("#welcome-player-id", "Zoé_O'Neil")
    page.press("#welcome-player-id", "Enter")
    expect(page.locator("#screen-game")).to_be_visible()
    assert server.route.url.endswith("/ws/Zo%C3%A9_O'Neil")


def test_guest_token_is_kept_in_memory_and_never_shown(game, server):
    """Partie d'invité : le jeton servira à rattacher la partie au compte en cas d'inscription."""
    server.send(type="guest_session", guest_token="jeton-secret")
    game.wait_for_function("guestToken === 'jeton-secret'")
    expect(game.locator("body")).not_to_contain_text("jeton-secret")
