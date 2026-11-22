"""Page d'administration, avec les routes du serveur simulées (connexion, état de la partie, comptes)."""
import json

from playwright.sync_api import expect

API = "**/admin/debug/all-states"

ADMIN_DATA = {
    "turn": 3,
    "phase": "nuit",
    "agents": ["Lord Ashcombe", "Mère Grimsby"],
    "channels": ["whisper_a"],
    "public_history": [{"sender": "Mère Grimsby", "content": "<img src=x onerror=alert(1)>"}],
    "agent_histories": {
        "Lord Ashcombe": [{"role": "system", "content": "Tu es Lord Ashcombe."}],
        "L'Ombre": [{"role": "assistant", "content": "Je me cache."}],
    },
    "players": [
        {"name": "Alex", "is_human": True, "role": "Médium", "team": "Villageois", "personality": None, "alive": True, "has_vote": True},
        {"name": "Lord Ashcombe", "is_human": False, "role": "Faucheur", "team": "Démon", "personality": "Stratège", "alive": False, "has_vote": True},
    ],
    "night_actions": [{"turn": 1, "player": "Lord Ashcombe", "content": "Nuit 1 : tu as choisi Alex."}],
    "night_history": [{"turn": 2, "type": "result", "info": "Mère Grimsby est mort·e cette nuit."}],
    "vote_history": [{"turn": 2, "voter": "Alex", "target": "Lord Ashcombe", "executed": "Lord Ashcombe"}],
}


USERS = [
    {"id": 1, "pseudo": "Gardien", "is_admin": True, "created_at": "2026-11-20T10:00:00"},
    {"id": 2, "pseudo": "Vesper", "is_admin": False, "created_at": "2026-11-21T18:30:00"},
]


def fulfill(route, status=200, body=None):
    route.fulfill(status=status, body=json.dumps(body), content_type="application/json")


class FakeAdminServer:
    """Simule le serveur : connexion par cookie, données admin, comptes, réinitialisation."""

    def __init__(self, page, status=200, body=ADMIN_DATA, logged_in=False, login_status=200):
        self.logged_in = logged_in
        self.status, self.body, self.login_status = status, body, login_status
        self.calls = []
        page.route(API, self._admin_data)
        page.route("**/admin/users", lambda route: fulfill(route, body=USERS))
        page.route("**/admin/users/*/reset-password", self._reset)
        page.route("**/admin/users/*", self._delete)
        self.delete_status = 204
        page.route("**/api/auth/login", self._login)
        page.route("**/api/auth/logout", self._logout)

    def _admin_data(self, route):
        if not self.logged_in:
            return fulfill(route, 401, {"detail": "Vous n'êtes pas connecté."})
        fulfill(route, self.status, self.body)

    def _login(self, route):
        self.calls.append(("login", route.request.post_data_json))
        if self.login_status != 200:
            return fulfill(route, self.login_status, {"detail": "Pseudo ou mot de passe incorrect."})
        self.logged_in = True
        fulfill(route, body={"id": 1, "pseudo": "Gardien", "is_admin": True})

    def _logout(self, route):
        self.calls.append(("logout", None))
        self.logged_in = False
        route.fulfill(status=204)

    def _delete(self, route):
        if route.request.method != "DELETE":
            return route.fallback()
        self.calls.append(("delete", route.request.url))
        if self.delete_status == 204:
            route.fulfill(status=204)
        else:
            fulfill(route, self.delete_status, {"detail": "Le compte administrateur ne peut pas être supprimé."})

    def _reset(self, route):
        self.calls.append(("reset", route.request.url))
        fulfill(route, body={"pseudo": "Vesper", "temporary_password": "Temp-1234567"})


def mock_api(page, status=200, body=ADMIN_DATA, **options):
    return FakeAdminServer(page, status, body, **options)


def login(page, static_url, pseudo="Gardien", password="mot-de-passe"):
    page.goto(f"{static_url}/admin.html")
    page.fill("#admin-pseudo-input", pseudo)
    page.fill("#admin-password-input", password)
    page.press("#admin-password-input", "Enter")


def test_login_shows_dashboard_with_escaped_content(page, static_url):
    mock_api(page)
    login(page, static_url)

    expect(page.locator("#dashboard-section")).to_be_visible()
    expect(page.locator("#stat-turn-phase")).to_have_text("Tour 3 · nuit")
    expect(page.locator("#stat-agents-count")).to_have_text("2")
    # Le HTML venant des LLM est affiché comme du texte, jamais interprété
    expect(page.locator("#public-history-container")).to_contain_text("<img src=x onerror=alert(1)>")
    expect(page.locator("#public-history-container img")).to_have_count(0)


def test_agent_with_apostrophe_can_be_selected(page, static_url):
    mock_api(page)
    login(page, static_url)

    page.locator(".agent-tab", has_text="L'Ombre").click()
    expect(page.locator("#agent-detail-container")).to_contain_text("Je me cache.")
    expect(page.locator(".agent-tab.is-active")).to_contain_text("L'Ombre")


def test_login_sends_credentials(page, static_url):
    server = mock_api(page)
    login(page, static_url, "Gardien", "secret-admin")
    expect(page.locator("#dashboard-section")).to_be_visible()
    assert server.calls[0] == ("login", {"pseudo": "Gardien", "password": "secret-admin"})


def test_page_opens_directly_when_already_logged_in(page, static_url):
    mock_api(page, logged_in=True)
    page.goto(f"{static_url}/admin.html")
    expect(page.locator("#dashboard-section")).to_be_visible()


def test_not_logged_in_shows_login_without_error(page, static_url):
    mock_api(page)
    page.goto(f"{static_url}/admin.html")
    expect(page.locator("#login-section")).to_be_visible()
    expect(page.locator("#login-error")).to_be_hidden()


def test_wrong_credentials_show_server_message(page, static_url):
    mock_api(page, login_status=401)
    login(page, static_url)

    expect(page.locator("#login-error")).to_have_text("Pseudo ou mot de passe incorrect.")
    expect(page.locator("#dashboard-section")).to_be_hidden()


def test_player_account_is_refused_and_logged_out(page, static_url):
    server = mock_api(page, status=403, body={"detail": "Accès réservé à l'administrateur."})
    login(page, static_url, "Vesper")

    expect(page.locator("#login-error")).to_have_text("Ce compte n'a pas accès au panneau d'administration.")
    expect(page.locator("#dashboard-section")).to_be_hidden()
    assert ("logout", None) in server.calls


def test_empty_fields_are_not_sent(page, static_url):
    server = mock_api(page)
    page.goto(f"{static_url}/admin.html")
    page.press("#admin-password-input", "Enter")
    expect(page.locator("#login-error")).to_contain_text("pseudo et le mot de passe")
    assert server.calls == []


def test_unexpected_api_response_shows_notice(page, static_url):
    mock_api(page, body=None)
    login(page, static_url)

    expect(page.locator("#no-data-notice")).to_have_text("Réponse inattendue du serveur.")
    expect(page.locator("#stat-turn-phase")).to_have_text("—")


def test_missing_fields_are_shown_as_unknown(page, static_url):
    mock_api(page, body={})
    login(page, static_url)

    expect(page.locator("#no-data-notice")).to_be_hidden()
    expect(page.locator("#stat-agents-count")).to_have_text("—")
    expect(page.locator("#agents-tabs-container")).to_contain_text("Aucun agent disponible.")


def test_logout_calls_the_server(page, static_url):
    server = mock_api(page)
    login(page, static_url)
    page.click("#logout-btn")

    expect(page.locator("#login-section")).to_be_visible()
    expect(page.locator("#admin-password-input")).to_have_value("")
    assert ("logout", None) in server.calls


def test_accounts_are_listed_without_reset_for_admin(page, static_url):
    mock_api(page)
    login(page, static_url)

    accounts = page.locator("#accounts-container")
    expect(accounts.locator("tr", has_text="Gardien")).to_contain_text("(admin)")
    expect(accounts.locator("tr", has_text="Gardien").locator(".reset-password-btn")).to_have_count(0)
    expect(accounts.locator("tr", has_text="Vesper").locator(".reset-password-btn")).to_have_count(1)


def test_reset_password_shows_temporary_password_once_confirmed(page, static_url):
    server = mock_api(page)
    login(page, static_url)
    page.once("dialog", lambda dialog: dialog.accept())
    page.locator("#accounts-container tr", has_text="Vesper").locator(".reset-password-btn").click()

    expect(page.locator("#reset-result")).to_contain_text("Mot de passe temporaire de Vesper : Temp-1234567")
    assert any(call[0] == "reset" and call[1].endswith("/admin/users/2/reset-password") for call in server.calls)


def test_reset_password_cancelled(page, static_url):
    server = mock_api(page)
    login(page, static_url)
    page.once("dialog", lambda dialog: dialog.dismiss())
    page.locator("#accounts-container tr", has_text="Vesper").locator(".reset-password-btn").click()

    expect(page.locator("#reset-result")).to_be_hidden()
    assert not any(call[0] == "reset" for call in server.calls)


def test_players_roles_and_night_actions_are_shown(page, static_url):
    mock_api(page)
    login(page, static_url)

    players = page.locator("#players-container")
    expect(players).to_contain_text("Alex (humain)")
    expect(players.locator("tr", has_text="Lord Ashcombe")).to_contain_text("Faucheur")
    expect(players.locator("tr", has_text="Lord Ashcombe")).to_contain_text("Stratège")
    expect(players.locator("tr", has_text="Lord Ashcombe")).to_contain_text("Mort")
    expect(page.locator("#night-actions-container")).to_contain_text("Nuit 1 : tu as choisi Alex.")


def test_player_night_and_vote_histories_are_shown(page, static_url):
    mock_api(page)
    login(page, static_url)

    expect(page.locator("#night-history-container")).to_contain_text("Mère Grimsby est mort·e cette nuit.")
    votes = page.locator("#vote-history-container")
    expect(votes).to_contain_text("Tour 2 — Lord Ashcombe exécuté·e")
    expect(votes).to_contain_text("Alex")


def test_no_game_message_from_server(page, static_url):
    mock_api(page, body={"game_in_progress": False, "message": "Aucune partie n'a encore été lancée."})
    login(page, static_url)

    expect(page.locator("#no-data-notice")).to_have_text("Aucune partie n'a encore été lancée.")
    expect(page.locator("#players-container")).to_contain_text("Aucune partie en cours.")


def test_delete_account_asks_for_confirmation(page, static_url):
    server = mock_api(page)
    login(page, static_url)
    page.locator("#accounts-container tr", has_text="Vesper").locator(".delete-account-btn").click()

    modal = page.locator("#modal-delete-account")
    expect(modal).to_be_visible()
    expect(modal).to_contain_text("Compte : Vesper")
    expect(page.locator("#delete-account-cancel")).to_be_focused()  # Entrée par réflexe : annule
    page.click("#delete-account-cancel")
    expect(modal).to_be_hidden()
    assert not any(call[0] == "delete" for call in server.calls)


def test_delete_account_once_confirmed(page, static_url):
    server = mock_api(page)
    login(page, static_url)
    page.locator("#accounts-container tr", has_text="Vesper").locator(".delete-account-btn").click()
    page.click("#delete-account-confirm")

    expect(page.locator("#modal-delete-account")).to_be_hidden()
    expect(page.locator("#reset-result")).to_have_text("Le compte Vesper a été supprimé.")
    assert any(call[0] == "delete" and call[1].endswith("/admin/users/2") for call in server.calls)


def test_delete_account_error_stays_in_the_modal(page, static_url):
    server = mock_api(page)
    server.delete_status = 400
    login(page, static_url)
    page.locator("#accounts-container tr", has_text="Vesper").locator(".delete-account-btn").click()
    page.click("#delete-account-confirm")
    expect(page.locator("#delete-account-error")).to_have_text("Le compte administrateur ne peut pas être supprimé.")
    page.keyboard.press("Escape")
    expect(page.locator("#modal-delete-account")).to_be_hidden()


def test_admin_account_has_no_delete_button(page, static_url):
    mock_api(page)
    login(page, static_url)
    expect(page.locator("#accounts-container tr", has_text="Gardien").locator(".delete-account-btn")).to_have_count(0)
