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
    assert server.route.url.endswith("/ws/Lady%20Vesper")


def test_unreachable_server_shows_error_and_reenables_button(page, static_url):
    page.add_init_script(FAILING_WEBSOCKET)
    page.goto(f"{static_url}/index.html")
    page.fill("#welcome-player-id", PLAYER)
    page.click("#welcome-join-btn")

    expect(page.locator("#welcome-error")).to_contain_text("Impossible de joindre le serveur")
    expect(page.locator("#welcome-join-btn")).to_be_enabled()
    expect(page.locator("#screen-game")).to_be_hidden()
