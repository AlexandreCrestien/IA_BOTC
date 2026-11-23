"""Comptes côté jeu : accueil (invité, connexion, inscription), joueur connecté qui rejoint sa partie,
reprise d'une partie d'invité, menu de la partie, inscription d'un invité pendant la partie ou en fin de partie."""
import json

from playwright.sync_api import expect

from conftest import PLAYER, players

USER = {"id": 1, "pseudo": PLAYER, "email": "vesper@exemple.fr", "is_admin": False}
ACHIEVEMENT = {"code": "one_turn_win", "title": "Coup de maître", "description": "Gagner une partie en un seul tour.",
               "message": "Talents de détective surnaturels ou chance inouïe ?"}


class FakeApi:
    """Routes /api/* simulées. responses : (méthode, chemin) -> (statut, corps). Garde les requêtes reçues."""

    def __init__(self, page, me=None, game=None):
        self.requests = []
        self.responses = {
            ("GET", "/api/auth/me"): (200, me) if me else (401, {"detail": "Vous n'êtes pas connecté."}),
            ("GET", "/api/game/current"): (200, game or {"running": False}),
            ("POST", "/api/auth/logout"): (204, None),
        }
        page.route("**/api/**", self._handle)

    def set(self, method, path, status, body):
        self.responses[(method, path)] = (status, body)

    def _handle(self, route):
        request = route.request
        path = "/" + request.url.split("/", 3)[3].split("?")[0]
        self.requests.append((request.method, path, request.post_data_json if request.post_data else None))
        status, body = self.responses.get((request.method, path), (404, {"detail": "Not Found"}))
        if body is None:
            route.fulfill(status=status)
        else:
            route.fulfill(status=status, body=json.dumps(body), content_type="application/json")

    def sent(self, method, path):
        return [data for m, p, data in self.requests if (m, p) == (method, path)]


def open_welcome(page, static_url, **api):
    fake = FakeApi(page, **api)
    page.goto(f"{static_url}/index.html")
    return fake


def join_as_guest(page, server):
    page.fill("#welcome-player-id", PLAYER)
    page.press("#welcome-player-id", "Enter")
    expect(page.locator("#screen-game")).to_be_visible()
    server.send(type="game_state", state={"phase": "discussion", "day": 1, "aliveCount": 6, "players": players()})


# --- Accueil -----------------------------------------------------------------------------

def test_welcome_tabs_show_one_form_at_a_time(page, static_url):
    open_welcome(page, static_url)
    expect(page.locator("#welcome-form")).to_be_visible()
    page.click("#welcome-tab-login")
    expect(page.locator("#login-form")).to_be_visible()
    expect(page.locator("#welcome-form")).to_be_hidden()
    page.click("#welcome-tab-register")
    expect(page.locator("#register-form")).to_be_visible()
    expect(page.locator("#welcome-tab-register")).to_have_attribute("aria-selected", "true")


def test_login_opens_the_dashboard(page, static_url):
    api = open_welcome(page, static_url)
    api.set("POST", "/api/auth/login", 200, {**USER, "game_claimed": False, "achievements": []})
    page.click("#welcome-tab-login")
    page.fill("#login-identifier", PLAYER)
    page.fill("#login-password", "mot-de-passe")
    page.press("#login-password", "Enter")
    page.wait_for_url("**/dashboard.html")
    assert api.sent("POST", "/api/auth/login")[0] == {"login": PLAYER, "password": "mot-de-passe", "guest_token": None}


def test_login_error_from_server_is_shown(page, static_url):
    api = open_welcome(page, static_url)
    api.set("POST", "/api/auth/login", 401, {"detail": "Pseudo ou mot de passe incorrect."})
    page.click("#welcome-tab-login")
    page.fill("#login-identifier", PLAYER)
    page.fill("#login-password", "mauvais")
    page.click("#login-btn")
    expect(page.locator("#login-error")).to_have_text("Pseudo ou mot de passe incorrect.")


def test_register_checks_the_confirmation_before_sending(page, static_url):
    api = open_welcome(page, static_url)
    page.click("#welcome-tab-register")
    page.fill("#register-pseudo", PLAYER)
    page.fill("#register-email", "vesper@exemple.fr")
    page.fill("#register-password", "mot-de-passe")
    page.fill("#register-password-confirm", "autre-chose")
    page.click("#register-btn")
    expect(page.locator("#register-error")).to_have_text("Les deux mots de passe ne correspondent pas.")
    assert api.sent("POST", "/api/auth/register") == []


def test_register_opens_the_dashboard(page, static_url):
    api = open_welcome(page, static_url)
    api.set("POST", "/api/auth/register", 201, {**USER, "game_claimed": False, "achievements": []})
    page.click("#welcome-tab-register")
    page.fill("#register-pseudo", PLAYER)
    page.fill("#register-email", "vesper@exemple.fr")
    page.fill("#register-password", "mot-de-passe")
    page.fill("#register-password-confirm", "mot-de-passe")
    page.click("#register-btn")
    page.wait_for_url("**/dashboard.html")


def test_logged_in_player_is_sent_to_the_dashboard(page, static_url):
    open_welcome(page, static_url, me=USER)
    page.wait_for_url("**/dashboard.html")


def test_logged_in_player_joins_his_game_directly(page, server, static_url):
    FakeApi(page, me=USER)
    page.goto(f"{static_url}/index.html?play")
    expect(page.locator("#screen-game")).to_be_visible()
    assert server.route.url.endswith(f"/ws/{PLAYER}")


def test_logged_in_player_resumes_a_game_under_his_guest_pseudo(page, server, static_url):
    """Invité « Lune » inscrit pendant sa partie : la partie garde son pseudo d'invité."""
    FakeApi(page, me=USER, game={"running": True, "pseudo": "Lune", "turn": 2, "yours": True})
    page.goto(f"{static_url}/index.html?play")
    expect(page.locator("#screen-game")).to_be_visible()
    assert server.route.url.endswith("/ws/Lune")


def test_refused_auto_join_is_explained(page, server, static_url):
    FakeApi(page, me=USER)
    server.refuse("Une partie est déjà en cours avec un autre joueur.")
    page.goto(f"{static_url}/index.html?play")
    expect(page.locator("#welcome-account-error")).to_have_text("Une partie est déjà en cours avec un autre joueur.")
    expect(page.locator("#welcome-form")).to_be_hidden()


def test_expired_session_asks_to_log_in_again(page, static_url):
    FakeApi(page)
    page.goto(f"{static_url}/index.html?play")
    expect(page.locator("#login-form")).to_be_visible()
    expect(page.locator("#login-error")).to_contain_text("reconnectez-vous")


def test_guest_can_resume_his_game(page, server, static_url):
    open_welcome(page, static_url, game={"running": True, "pseudo": "Lune", "turn": 3, "yours": True})
    expect(page.locator("#welcome-resume")).to_contain_text("Lune")
    page.click("[data-action='resume-guest-game']")
    expect(page.locator("#screen-game")).to_be_visible()
    assert server.route.url.endswith("/ws/Lune")


# --- Menu de la partie ---------------------------------------------------------------------

def test_guest_menu(page, server, static_url):
    open_welcome(page, static_url)
    join_as_guest(page, server)
    page.click("#menu-btn")
    expect(page.locator("#game-menu")).to_be_visible()
    expect(page.locator("#menu-register")).to_be_visible()
    expect(page.locator("#menu-login")).to_be_visible()
    expect(page.locator("#menu-dashboard")).to_be_hidden()
    expect(page.locator("#menu-logout")).to_be_hidden()
    page.keyboard.press("Escape")
    expect(page.locator("#game-menu")).to_be_hidden()


def test_logged_in_menu(page, server, static_url):
    api = FakeApi(page, me=USER)
    page.goto(f"{static_url}/index.html?play")
    expect(page.locator("#screen-game")).to_be_visible()
    page.click("#menu-btn")
    expect(page.locator("#menu-player")).to_have_text(f"Connecté : {PLAYER}")
    expect(page.locator("#menu-dashboard")).to_have_attribute("target", "_blank")
    expect(page.locator("#menu-register")).to_be_hidden()

    page.click("#menu-logout")
    page.wait_for_url(lambda url: url.endswith("/") or url.endswith("/index.html"))
    assert len(api.sent("POST", "/api/auth/logout")) == 1


def test_menu_closes_on_outside_click(page, server, static_url):
    open_welcome(page, static_url)
    join_as_guest(page, server)
    page.click("#menu-btn")
    page.click("#game-announcement")
    expect(page.locator("#game-menu")).to_be_hidden()


# --- Invité qui crée un compte ou se connecte -------------------------------------------------

def test_guest_registers_during_the_game(page, server, static_url):
    api = open_welcome(page, static_url)
    join_as_guest(page, server)
    server.send(type="guest_session", guest_token="jeton")
    api.set("POST", "/api/auth/register", 201, {**USER, "game_claimed": True, "achievements": []})

    page.click("#menu-btn")
    page.click("#menu-register")
    expect(page.locator("#account-pseudo")).to_have_value(PLAYER)  # pseudo d'invité proposé
    page.fill("#account-email", "vesper@exemple.fr")
    page.fill("#account-password", "mot-de-passe")
    page.fill("#account-password-confirm", "mot-de-passe")
    page.click("#account-submit")

    expect(page.locator("#modal-account")).to_be_hidden()
    assert api.sent("POST", "/api/auth/register")[0]["guest_token"] == "jeton"
    expect(page.locator("#chat-messages")).to_contain_text("Cette partie sera enregistrée dans votre compte.")
    page.click("#menu-btn")
    expect(page.locator("#menu-dashboard")).to_be_visible()


def test_account_modal_switches_to_login_and_shows_errors(page, server, static_url):
    api = open_welcome(page, static_url)
    join_as_guest(page, server)
    api.set("POST", "/api/auth/login", 401, {"detail": "Pseudo ou mot de passe incorrect."})
    page.click("#menu-btn")
    page.click("#menu-register")
    page.click("#account-switch")
    expect(page.locator("#account-title")).to_have_text("Se connecter")
    expect(page.locator("#account-confirm-row")).to_be_hidden()
    page.fill("#account-pseudo", PLAYER)
    page.fill("#account-password", "mauvais")
    page.click("#account-submit")
    expect(page.locator("#account-error")).to_have_text("Pseudo ou mot de passe incorrect.")
    page.click("#modal-account [data-action='close-account']")
    expect(page.locator("#modal-account")).to_be_hidden()


# --- Fin de partie ------------------------------------------------------------------------------

def test_game_over_lists_unlocked_achievements(page, server, static_url):
    FakeApi(page, me=USER)
    page.goto(f"{static_url}/index.html?play")
    expect(page.locator("#screen-game")).to_be_visible()
    server.send(type="game_over", winner="good", details="Fin.", achievements=[ACHIEVEMENT])

    expect(page.locator("#gameover-achievements")).to_contain_text("Coup de maître")
    expect(page.locator("#gameover-achievements")).to_contain_text("Talents de détective surnaturels ou chance inouïe ?")
    expect(page.locator("#gameover-register")).to_be_hidden()
    expect(page.locator("#gameover-dashboard")).to_be_visible()


def test_guest_registers_from_the_end_screen(page, server, static_url):
    api = open_welcome(page, static_url)
    join_as_guest(page, server)
    server.send(type="guest_session", guest_token="jeton")
    server.send(type="game_over", winner="good", details="Fin.", achievements=[])
    expect(page.locator("#gameover-register")).to_be_visible()
    expect(page.locator("#gameover-achievements")).to_be_hidden()

    api.set("POST", "/api/auth/register", 201, {**USER, "game_claimed": True, "achievements": [ACHIEVEMENT]})
    page.click("#gameover-register [data-mode='register']")
    page.fill("#account-email", "vesper@exemple.fr")
    page.fill("#account-password", "mot-de-passe")
    page.fill("#account-password-confirm", "mot-de-passe")
    page.click("#account-submit")

    expect(page.locator("#gameover-register")).to_be_hidden()
    expect(page.locator("#gameover-achievements")).to_contain_text("Coup de maître")
    expect(page.locator("#gameover-dashboard")).to_be_visible()


def test_interrupted_game_offers_no_registration(page, server, static_url):
    open_welcome(page, static_url)
    join_as_guest(page, server)
    server.send(type="guest_session", guest_token="jeton")
    server.send(type="game_interrupted", text="Une erreur a interrompu la partie.")
    expect(page.locator("#modal-gameover")).to_be_visible()
    expect(page.locator("#gameover-register")).to_be_hidden()


def test_new_game_for_a_logged_in_player_starts_right_away(page, server, static_url):
    FakeApi(page, me=USER)
    page.goto(f"{static_url}/index.html?play")
    expect(page.locator("#screen-game")).to_be_visible()
    server.send(type="game_over", winner="evil", details="Fin.")
    page.click("#modal-gameover [data-action='new-game']")
    page.wait_for_url("**/?play")


# --- E-mail : inscription, mot de passe oublié -------------------------------------------------

def test_register_sends_the_email(page, static_url):
    api = open_welcome(page, static_url)
    api.set("POST", "/api/auth/register", 201, {**USER, "game_claimed": False, "achievements": []})
    page.click("#welcome-tab-register")
    page.fill("#register-pseudo", PLAYER)
    page.fill("#register-email", " Vesper@Exemple.fr ")
    page.fill("#register-password", "mot-de-passe")
    page.fill("#register-password-confirm", "mot-de-passe")
    page.click("#register-btn")
    page.wait_for_url("**/dashboard.html")
    assert api.sent("POST", "/api/auth/register")[0]["email"] == "Vesper@Exemple.fr"


def test_register_requires_the_email(page, static_url):
    api = open_welcome(page, static_url)
    page.click("#welcome-tab-register")
    page.fill("#register-pseudo", PLAYER)
    page.fill("#register-password", "mot-de-passe")
    page.fill("#register-password-confirm", "mot-de-passe")
    page.click("#register-btn")
    expect(page.locator("#register-error")).to_contain_text("adresse e-mail")
    assert api.sent("POST", "/api/auth/register") == []


def test_forgot_password_panel(page, static_url):
    api = open_welcome(page, static_url)
    message = "Si un compte existe avec cette adresse, un e-mail vient d'y être envoyé."
    api.set("POST", "/api/auth/forgot-password", 200, {"message": message})
    page.click("#welcome-tab-login")
    page.click("#forgot-link")
    expect(page.locator("#forgot-form")).to_be_visible()
    expect(page.locator("#login-form")).to_be_hidden()
    expect(page.locator("#welcome-tab-login")).to_have_attribute("aria-selected", "true")  # onglet Connexion gardé
    expect(page.locator("#forgot-email")).to_be_focused()

    page.click("#forgot-btn")
    expect(page.locator("#forgot-error")).to_have_text("Veuillez entrer votre adresse e-mail.")
    assert api.sent("POST", "/api/auth/forgot-password") == []

    page.fill("#forgot-email", "vesper@exemple.fr")
    page.press("#forgot-email", "Enter")
    expect(page.locator("#forgot-message")).to_have_text(message)
    assert api.sent("POST", "/api/auth/forgot-password") == [{"email": "vesper@exemple.fr"}]

    page.click("#forgot-form [data-tab='login']")
    expect(page.locator("#login-form")).to_be_visible()


def test_welcome_confirms_a_password_reset(page, static_url):
    FakeApi(page)
    page.goto(f"{static_url}/index.html?reset=done")
    expect(page.locator("#welcome-notice")).to_have_text("Votre mot de passe a été modifié : connectez-vous avec le nouveau.")
    expect(page.locator("#login-form")).to_be_visible()
    assert "reset" not in page.url


def test_in_game_login_accepts_pseudo_or_email(page, server, static_url):
    api = open_welcome(page, static_url)
    join_as_guest(page, server)
    api.set("POST", "/api/auth/login", 200, {**USER, "game_claimed": True, "achievements": []})
    page.click("#menu-btn")
    page.click("#menu-login")
    expect(page.locator("#account-pseudo-label")).to_have_text("Pseudo ou adresse e-mail")
    expect(page.locator("#account-email-row")).to_be_hidden()
    page.fill("#account-pseudo", "vesper@exemple.fr")
    page.fill("#account-password", "mot-de-passe")
    page.click("#account-submit")
    expect(page.locator("#modal-account")).to_be_hidden()
    assert api.sent("POST", "/api/auth/login")[0]["login"] == "vesper@exemple.fr"


def test_email_info_tooltip_on_hover_and_focus(page, static_url):
    open_welcome(page, static_url)
    page.click("#welcome-tab-register")
    tip = page.locator("#register-email-tip")
    expect(tip).to_be_hidden()
    page.hover("#register-form .info-tip-icon")
    expect(tip).to_be_visible()
    expect(tip).to_contain_text("jamais transmise")
    page.mouse.move(0, 0)
    expect(tip).to_be_hidden()

    page.focus("#register-form .info-tip-icon")  # au clavier (Tab) : visible aussi
    expect(tip).to_be_visible()
    expect(page.locator("#register-email")).to_have_attribute("aria-describedby", "register-email-tip")
