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
    assert server.calls[0] == ("login", {"login": "Gardien", "password": "secret-admin"})


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


# --- Historique d'un joueur -------------------------------------------------------------------

PLAYER_GAMES = [
    {"id": 7, "date": "2026-11-24T20:00:00+00:00", "role_name": "Médium", "alignment": "good", "status": "won",
     "turns": 3, "has_detail": True},
    {"id": 3, "date": "2026-04-01T20:00:00+00:00", "role_name": "Faucheur", "alignment": "evil", "status": "lost",
     "turns": 5, "has_detail": False},
]
PLAYER_EVENTS = [
    {"kind": "password_changed", "label": "Mot de passe modifié (profil)", "date": "2026-11-24T21:00:00+00:00"},
    {"kind": "account_created", "label": "Compte créé", "date": "2026-11-20T10:00:00+00:00"},
]
PAST_DETAIL = {**ADMIN_DATA, "status": "victoire", "turn": 3, "game_in_progress": False,
               "public_history": [{"moment": "Jour 1", "sender": "Vesper", "content": "Message d'une partie passée"}]}


def mock_history(page):
    page.route("**/admin/users/*/games", lambda route: fulfill(route, body=PLAYER_GAMES))
    page.route("**/admin/users/*/events", lambda route: fulfill(route, body=PLAYER_EVENTS))
    page.route("**/admin/games/7", lambda route: fulfill(route, body={
        "game": {**PLAYER_GAMES[0], "pseudo": "Vesper"}, "detail": PAST_DETAIL}))


def open_history(page, static_url):
    mock_api(page)
    mock_history(page)
    login(page, static_url)
    page.locator("#accounts-container tr", has_text="Vesper").locator(".history-btn").click()
    expect(page.locator("#player-history")).to_be_visible()


def test_history_button_for_every_account(page, static_url):
    mock_api(page)
    login(page, static_url)
    expect(page.locator("#accounts-container .history-btn")).to_have_count(2)  # admin compris


def test_player_history_lists_games_and_account_log(page, static_url):
    open_history(page, static_url)
    expect(page.locator("#player-history-title")).to_have_text("Historique de Vesper")
    rows = page.locator("#player-games-container tbody tr")
    expect(rows).to_have_count(2)
    expect(rows.nth(0)).to_contain_text("Médium")
    expect(rows.nth(0).locator(".game-detail-btn")).to_have_count(1)
    expect(rows.nth(1)).to_contain_text("effacé (plus de 6 mois)")
    events = page.locator("#player-events-container")
    expect(events).to_contain_text("Mot de passe modifié (profil)")
    expect(events).to_contain_text("Compte créé")


def test_past_game_is_shown_then_back_to_current(page, static_url):
    open_history(page, static_url)
    page.locator(".game-detail-btn").click()
    banner = page.locator("#viewing-past-game")
    expect(banner).to_be_visible()
    expect(banner).to_contain_text("Partie de Vesper")
    expect(page.locator("#public-history-container")).to_contain_text("Message d'une partie passée")

    page.click("#back-to-current-game")
    expect(banner).to_be_hidden()
    expect(page.locator("#public-history-container")).not_to_contain_text("Message d'une partie passée")


def test_close_player_history(page, static_url):
    open_history(page, static_url)
    page.click("#close-player-history")
    expect(page.locator("#player-history")).to_be_hidden()


# --- Signalements des messages des IA ---------------------------------------------------------------

def report(id, agent, model, category, label, handled=False, game_link="detail", reporter="Vesper", comment=None,
           personality="agitator"):
    return {"id": id, "date": "2026-11-24T20:00:00+00:00", "agent": agent, "personality": personality,
            "role_name": "Médium", "model": model, "channel": "public", "moment": "Jour 2",
            "message": "<b>[joueur]</b> ment.", "category": category, "category_label": label, "comment": comment,
            "reporter": reporter, "handled": handled, "handled_at": "2026-11-25T08:00:00+00:00" if handled else None,
            "game_id": 7, "game_link": game_link}


REPORTS = [
    report(1, "Lord Ashcombe", "groq/openai/gpt-oss-20b", "knowledge", "Révèle une information qu'il ne devrait pas connaître",
           comment="Il connaît mon rôle"),
    report(2, "Mère Grimsby", "gemini/gemini-3.1-flash-lite", "character", "Sort de son personnage", game_link=None,
           reporter=None, personality="clown"),
    report(3, "Lord Ashcombe", None, "rules", "Incohérent ou contraire aux règles", handled=True,
           game_link="current"),
]


class FakeReports:
    def __init__(self, page):
        self.statuses = []
        page.route("**/admin/reports", lambda route: fulfill(route, body=REPORTS))
        page.route("**/admin/reports/*/status", self._status)

    def _status(self, route):
        report_id = int(route.request.url.split("/")[-2])
        handled = route.request.post_data_json["handled"]
        self.statuses.append((report_id, handled))
        fulfill(route, body={"id": report_id, "handled": handled,
                             "handled_at": "2026-11-25T09:00:00+00:00" if handled else None})


def open_reports(page, static_url):
    mock_api(page)
    mock_history(page)
    fake = FakeReports(page)
    login(page, static_url)
    expect(page.locator("#reports-count")).to_have_text("(2 en attente)")
    return fake


def test_pending_reports_are_shown_by_default(page, static_url):
    open_reports(page, static_url)
    cards = page.locator("#reports-container .report-card")
    expect(cards).to_have_count(2)
    first = cards.nth(0)
    expect(first).to_contain_text("Lord Ashcombe")
    expect(first).to_contain_text("gpt-oss-20b")
    expect(first).to_contain_text("Révèle une information qu'il ne devrait pas connaître — Il connaît mon rôle")
    expect(first).to_contain_text("« <b>[joueur]</b> ment. »")  # texte des IA jamais interprété
    expect(cards.nth(1)).to_contain_text("compte supprimé")
    expect(cards.nth(1)).to_contain_text("Partie plus disponible")


def test_reports_can_be_filtered(page, static_url):
    open_reports(page, static_url)
    page.select_option("#filter-status", "")
    expect(page.locator("#reports-container .report-card")).to_have_count(3)
    page.select_option("#filter-model", "gemini/gemini-3.1-flash-lite")
    expect(page.locator("#reports-container .report-card")).to_have_count(1)
    expect(page.locator("#reports-container")).to_contain_text("Mère Grimsby")

    page.select_option("#filter-model", "*")
    page.select_option("#filter-agent", "Lord Ashcombe")
    page.select_option("#filter-category", "rules")
    expect(page.locator("#reports-container .report-card")).to_have_count(1)
    expect(page.locator("#reports-container")).to_contain_text("modèle : inconnu")

    page.select_option("#filter-personality", "clown")
    expect(page.locator("#reports-container")).to_contain_text("Aucun signalement pour ces filtres.")


def test_report_can_be_marked_as_handled(page, static_url):
    fake = open_reports(page, static_url)
    page.locator(".report-card", has_text="Mère Grimsby").locator(".report-status-btn").click()
    expect(page.locator("#reports-count")).to_have_text("(1 en attente)")
    expect(page.locator("#reports-container .report-card")).to_have_count(1)
    assert fake.statuses == [(2, True)]

    page.select_option("#filter-status", "handled")
    handled = page.locator(".report-card", has_text="Mère Grimsby")
    expect(handled).to_contain_text("Traité le")
    handled.locator(".report-status-btn").click()
    expect(page.locator("#reports-count")).to_have_text("(2 en attente)")
    assert fake.statuses == [(2, True), (2, False)]


def test_report_links_to_its_game(page, static_url):
    open_reports(page, static_url)
    page.locator(".report-card", has_text="Lord Ashcombe").locator(".report-game-btn").click()
    expect(page.locator("#viewing-past-game")).to_be_visible()
    expect(page.locator("#public-history-container")).to_contain_text("Message d'une partie passée")


# --- Évaluations des agents (fin de partie) ---------------------------------------------------------

RATINGS = {
    "count": 4, "average": 3.25,
    "by_personality": [{"key": "agitator", "count": 2, "average": 4.5}, {"key": "clown", "count": 2, "average": 2.0}],
    "by_model": [{"key": "groq/openai/gpt-oss-20b", "count": 3, "average": 3.67}, {"key": None, "count": 1, "average": 2.0}],
    "comments": [{"id": 1, "date": "2026-11-24T20:00:00+00:00", "agent": "Lord Ashcombe", "personality": "agitator",
                  "role_name": "Médium", "model": "groq/openai/gpt-oss-20b", "score": 4,
                  "comment": "<i>Très</i> crédible", "author": None, "game_id": 7, "game_link": "detail"}],
}


def test_ratings_show_averages_and_comments(page, static_url):
    mock_api(page)
    mock_history(page)
    page.route("**/admin/ratings", lambda route: fulfill(route, body=RATINGS))
    login(page, static_url)

    expect(page.locator("#ratings-summary")).to_have_text("(3,25 / 5, 4 notes)")
    personality = page.locator("#ratings-personality tbody tr")
    expect(personality.nth(0)).to_contain_text("agitator")
    expect(personality.nth(0)).to_contain_text("4,5 / 5")
    expect(page.locator("#ratings-model")).to_contain_text("aucun message")
    comment = page.locator("#ratings-comments .report-card")
    expect(comment).to_contain_text("★★★★☆")
    expect(comment).to_contain_text("« <i>Très</i> crédible »")
    expect(comment).to_contain_text("compte supprimé")
    comment.locator(".report-game-btn").click()
    expect(page.locator("#viewing-past-game")).to_be_visible()


def test_no_rating_yet(page, static_url):
    mock_api(page)
    page.route("**/admin/ratings", lambda route: fulfill(route, body={
        "count": 0, "average": None, "by_personality": [], "by_model": [], "comments": []}))
    login(page, static_url)
    expect(page.locator("#ratings-personality")).to_contain_text("Aucune évaluation.")
    expect(page.locator("#ratings-comments")).to_contain_text("Aucun commentaire.")


# --- Raccourcis de l'en-tête ---------------------------------------------------------------------

def test_header_shortcuts_scroll_to_sections(page, static_url):
    mock_api(page)
    page.route("**/admin/reports", lambda route: fulfill(route, body=REPORTS))
    login(page, static_url)
    nav = page.locator("#admin-nav")
    expect(nav.locator(".dash-nav-link")).to_have_text(["Accueil", "Signalements", "Partie"])
    expect(nav.locator(".dash-nav-link.is-active")).to_have_text("Accueil")  # en haut de la page

    nav.locator("a", has_text="Signalements").click()
    # La section s'arrête juste sous l'en-tête collant (quelle que soit sa hauteur), sans passer dessous
    page.wait_for_function("""Math.abs(document.getElementById('admin-reports').getBoundingClientRect().top
        - document.querySelector('.admin-header').getBoundingClientRect().bottom - 16) < 2""")
    expect(nav.locator(".dash-nav-link.is-active")).to_have_text("Signalements")

    nav.locator("a", has_text="Accueil").click()
    page.wait_for_function("window.scrollY === 0")
    expect(nav.locator(".dash-nav-link.is-active")).to_have_text("Accueil")


def test_header_shortcuts_wrap_on_a_medium_screen(page, static_url):
    page.set_viewport_size({"width": 900, "height": 800})
    mock_api(page)
    login(page, static_url)
    nav = page.locator("#admin-nav")
    expect(nav).to_be_visible()
    title_bottom = page.evaluate("document.querySelector('.admin-header > div').getBoundingClientRect().bottom")
    assert nav.bounding_box()["y"] >= title_bottom - 1  # deuxième ligne de l'en-tête
    assert page.evaluate("document.documentElement.scrollWidth") <= 900  # pas de défilement horizontal
