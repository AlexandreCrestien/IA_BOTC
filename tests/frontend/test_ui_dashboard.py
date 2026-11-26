"""Tableau de bord du joueur connecté, avec les routes /api simulées : partie (commencer, reprendre,
abandonner), statistiques, historique, succès (cachés ou non), profil, déconnexion."""
from playwright.sync_api import expect

from conftest import PLAYER
from test_ui_accounts import FakeApi, USER

STATS = {"played": 4, "wins": 3, "win_rate": 0.75,
         "good": {"played": 3, "wins": 2, "win_rate": 0.667},
         "evil": {"played": 1, "wins": 1, "win_rate": 1.0},
         "average_turns": 3.5}
GAMES = [
    {"id": 3, "date": "2026-11-21T19:30:00+00:00", "role": "reaper", "role_name": "Faucheur", "alignment": "evil",
     "status": "won", "counted": True, "turns": 4},
    {"id": 2, "date": "2026-11-20T19:30:00+00:00", "role": "medium", "role_name": "Médium", "alignment": "good",
     "status": "abandoned", "counted": True, "turns": 2},
    {"id": 1, "date": "2026-11-19T19:30:00+00:00", "role": "valet", "role_name": "Valet", "alignment": "good",
     "status": "interrupted", "counted": False, "turns": 1},
]
ACHIEVEMENTS = [
    {"code": "win_reaper", "title": "Victoire : Faucheur", "description": "Gagner une partie en tant que Faucheur.",
     "message": "La moisson a été bonne.", "hidden": False, "unlocked": True, "unlocked_at": "2026-11-21T20:00:00+00:00"},
    {"code": "executed", "title": "Sur l'échafaud", "description": "Être exécuté.", "message": None,
     "hidden": False, "unlocked": False, "unlocked_at": None},
    {"code": "one_turn_win", "title": "???", "description": "Succès caché.", "message": None,
     "hidden": True, "unlocked": False, "unlocked_at": None},
]


def open_dashboard(page, static_url, game=None):
    api = FakeApi(page, me=USER, game=game)
    api.set("GET", "/api/me/stats", 200, STATS)
    api.set("GET", "/api/me/games", 200, GAMES)
    api.set("GET", "/api/me/achievements", 200, ACHIEVEMENTS)
    page.goto(f"{static_url}/dashboard.html")
    expect(page.locator("#dashboard-main")).to_be_visible()
    return api


def test_not_logged_in_goes_back_to_welcome(page, static_url):
    FakeApi(page)
    page.goto(f"{static_url}/dashboard.html")
    page.wait_for_url(lambda url: not url.endswith("dashboard.html"))
    expect(page.locator("#screen-welcome")).to_be_visible()


def test_header_and_stats(page, static_url):
    open_dashboard(page, static_url)
    expect(page.locator("#dashboard-pseudo")).to_have_text(PLAYER)
    expect(page.locator("#stat-played")).to_have_text("4")
    expect(page.locator("#stat-win-rate")).to_have_text("75 %")
    expect(page.locator("#stat-wins")).to_have_text("3 victoires sur 4")
    expect(page.locator("#stat-good-rate")).to_have_text("67 %")
    expect(page.locator("#stat-evil-wins")).to_have_text("1 victoire sur 1")
    expect(page.locator("#stat-turns")).to_have_text("3.5")


def test_empty_stats(page, static_url):
    api = open_dashboard(page, static_url)
    api.set("GET", "/api/me/stats", 200, {"played": 0, "wins": 0, "win_rate": None, "good": {"played": 0, "wins": 0, "win_rate": None},
                                          "evil": {"played": 0, "wins": 0, "win_rate": None}, "average_turns": None})
    api.set("GET", "/api/me/games", 200, [])
    page.reload()
    expect(page.locator("#stat-win-rate")).to_have_text("—")
    expect(page.locator("#stat-good-wins")).to_have_text("aucune partie")
    expect(page.locator("#history-container")).to_contain_text("Aucune partie jouée")


def test_history(page, static_url):
    open_dashboard(page, static_url)
    rows = page.locator("#history-container tbody tr")
    expect(rows).to_have_count(3)
    expect(rows.nth(0)).to_contain_text("Faucheur")
    expect(rows.nth(0)).to_contain_text("Démons")
    expect(rows.nth(0)).to_contain_text("Victoire")
    expect(rows.nth(1)).to_contain_text("Défaite (abandon)")
    expect(rows.nth(2)).to_contain_text("Interrompue (non comptée)")


def test_achievements_unlocked_locked_and_hidden(page, static_url):
    open_dashboard(page, static_url)
    expect(page.locator("#achievements-count")).to_have_text("(1 / 3)")
    unlocked = page.locator(".achievement[data-code='win_reaper']")
    expect(unlocked).to_have_class("achievement is-unlocked")
    expect(unlocked).to_contain_text("La moisson a été bonne.")
    expect(page.locator(".achievement[data-code='executed']")).to_have_class("achievement is-locked")
    expect(page.locator(".achievement[data-code='one_turn_win']")).to_contain_text("???")


def test_start_a_game_without_game_in_progress(page, static_url):
    open_dashboard(page, static_url)
    start = page.locator("#start-game-btn")
    expect(start).to_be_enabled()
    expect(page.locator("#resume-game-btn")).to_be_hidden()
    start.click()
    page.wait_for_url("**/?play")


def test_own_game_in_progress(page, static_url):
    open_dashboard(page, static_url, game={"running": True, "pseudo": PLAYER, "turn": 2, "yours": True})
    expect(page.locator("#start-game-btn")).to_be_disabled()
    expect(page.locator("#start-game-btn")).to_have_text("Une partie est déjà en cours")
    expect(page.locator("#game-status")).to_have_text("Votre partie est en cours (tour 2).")
    expect(page.locator("#resume-game-btn")).to_be_visible()
    expect(page.locator("#abandon-game-btn")).to_be_visible()


def test_someone_elses_game_in_progress(page, static_url):
    open_dashboard(page, static_url, game={"running": True, "pseudo": "Lune", "turn": 2, "yours": False})
    expect(page.locator("#start-game-btn")).to_be_disabled()
    expect(page.locator("#resume-game-btn")).to_be_hidden()
    expect(page.locator("#abandon-game-btn")).to_be_hidden()


def test_abandon_from_dashboard(page, static_url):
    api = open_dashboard(page, static_url, game={"running": True, "pseudo": PLAYER, "turn": 2, "yours": True})
    api.set("POST", "/api/game/abandon", 204, None)
    page.click("#abandon-game-btn")
    expect(page.locator("#modal-abandon")).to_be_visible()

    api.set("GET", "/api/game/current", 200, {"running": False})
    page.click("#abandon-confirm")
    expect(page.locator("#start-game-btn")).to_be_enabled()
    assert len(api.sent("POST", "/api/game/abandon")) == 1


def test_abandon_can_be_cancelled(page, static_url):
    api = open_dashboard(page, static_url, game={"running": True, "pseudo": PLAYER, "turn": 2, "yours": True})
    page.click("#abandon-game-btn")
    page.click("#abandon-cancel")
    expect(page.locator("#modal-abandon")).to_be_hidden()
    assert api.sent("POST", "/api/game/abandon") == []


def test_change_pseudo(page, static_url):
    api = open_dashboard(page, static_url)
    api.set("PATCH", "/api/account/pseudo", 200, {"id": 1, "pseudo": "Ombre", "is_admin": False})
    page.fill("#new-pseudo", "Ombre")
    page.fill("#pseudo-current-password", "mot-de-passe")
    page.click("#pseudo-submit")
    expect(page.locator("#pseudo-success")).to_have_text("Votre pseudo est maintenant Ombre.")
    expect(page.locator("#dashboard-pseudo")).to_have_text("Ombre")
    assert api.sent("PATCH", "/api/account/pseudo")[0] == {"pseudo": "Ombre", "current_password": "mot-de-passe"}


def test_change_pseudo_refused_during_a_game(page, static_url):
    api = open_dashboard(page, static_url)
    api.set("PATCH", "/api/account/pseudo", 409, {"detail": "Impossible de changer de pseudo pendant une partie en cours."})
    page.fill("#new-pseudo", "Ombre")
    page.fill("#pseudo-current-password", "mot-de-passe")
    page.click("#pseudo-submit")
    expect(page.locator("#pseudo-error")).to_have_text("Impossible de changer de pseudo pendant une partie en cours.")
    expect(page.locator("#dashboard-pseudo")).to_have_text(PLAYER)


def test_change_password(page, static_url):
    api = open_dashboard(page, static_url)
    api.set("PATCH", "/api/account/password", 200, USER)
    page.fill("#password-current", "ancien-mdp")
    page.fill("#password-new", "nouveau-mdp")
    page.fill("#password-confirm", "autre-mdp")
    page.click("#password-submit")
    expect(page.locator("#password-error")).to_have_text("Les deux nouveaux mots de passe ne correspondent pas.")
    assert api.sent("PATCH", "/api/account/password") == []

    page.fill("#password-confirm", "nouveau-mdp")
    page.click("#password-submit")
    expect(page.locator("#password-success")).to_contain_text("Mot de passe modifié")


def test_logout(page, static_url):
    api = open_dashboard(page, static_url)
    page.click("#dashboard-logout")
    page.wait_for_url(lambda url: not url.endswith("dashboard.html"))
    assert len(api.sent("POST", "/api/auth/logout")) == 1


def test_html_from_the_server_is_never_interpreted(page, static_url):
    api = FakeApi(page, me={**USER, "pseudo": "<img src=x onerror=alert(1)>"})
    api.set("GET", "/api/me/stats", 200, STATS)
    api.set("GET", "/api/me/games", 200, [{**GAMES[0], "role_name": "<b>Faucheur</b>"}])
    api.set("GET", "/api/me/achievements", 200, [])
    page.goto(f"{static_url}/dashboard.html")
    expect(page.locator("#dashboard-pseudo")).to_have_text("<img src=x onerror=alert(1)>")
    expect(page.locator("#history-container")).to_contain_text("<b>Faucheur</b>")
    expect(page.locator("#history-container b")).to_have_count(0)


def test_header_shortcuts_scroll_to_sections(page, static_url):
    open_dashboard(page, static_url)
    nav = page.locator("#dashboard-nav")
    expect(nav.locator(".dash-nav-link")).to_have_text(["Statistiques", "Succès", "Profil"])
    expect(nav.locator(".dash-nav-sep")).to_have_count(2)

    page.set_viewport_size({"width": 1280, "height": 500})  # assez petit pour devoir défiler
    expect(nav.locator(".dash-nav-link.is-active")).to_have_count(0)  # en haut de la page : aucune section
    nav.locator("a", has_text="Profil").click()
    page.wait_for_function("window.scrollY > 0")
    expect(page.locator("#section-profile")).to_be_in_viewport()
    expect(nav.locator("a", has_text="Profil")).to_have_class("dash-nav-link is-active")


def test_no_shortcut_highlighted_at_the_top_of_a_short_page(page, static_url):
    """Page qui tient dans l'écran (aucun défilement) : aucun raccourci mis en valeur."""
    page.set_viewport_size({"width": 1280, "height": 3000})
    open_dashboard(page, static_url)
    page.wait_for_timeout(200)
    expect(page.locator(".dash-nav-link.is-active")).to_have_count(0)


def test_delete_account_modal_explains_what_is_deleted(page, static_url):
    api = open_dashboard(page, static_url)
    page.click("#delete-account-btn")
    modal = page.locator("#modal-delete-account")
    expect(modal).to_be_visible()
    expect(modal).to_contain_text("vos succès")
    expect(modal).to_contain_text("Gardés de façon anonyme")
    expect(page.locator("#delete-account-password")).to_be_focused()

    page.click("#delete-account-confirm")  # sans mot de passe : rien n'est envoyé
    expect(page.locator("#delete-account-error")).to_contain_text("mot de passe")
    page.click("#delete-account-cancel")
    expect(modal).to_be_hidden()
    assert api.sent("DELETE", "/api/account") == []


def test_delete_account_wrong_password(page, static_url):
    api = open_dashboard(page, static_url)
    api.set("DELETE", "/api/account", 403, {"detail": "Mot de passe actuel incorrect."})
    page.click("#delete-account-btn")
    page.fill("#delete-account-password", "mauvais")
    page.press("#delete-account-password", "Enter")
    expect(page.locator("#delete-account-error")).to_have_text("Mot de passe actuel incorrect.")
    expect(page.locator("#modal-delete-account")).to_be_visible()


def test_delete_account_then_welcome_confirms(page, static_url):
    api = open_dashboard(page, static_url)
    api.set("DELETE", "/api/account", 204, None)
    page.click("#delete-account-btn")
    page.fill("#delete-account-password", "mot-de-passe")
    api.set("GET", "/api/auth/me", 401, {"detail": "Vous n'êtes pas connecté."})
    page.click("#delete-account-confirm")

    expect(page.locator("#welcome-notice")).to_have_text("Votre compte a été supprimé.")
    assert api.sent("DELETE", "/api/account") == [{"current_password": "mot-de-passe"}]
    assert not page.url.endswith("deleted")  # l'adresse est nettoyée


def test_export_downloads_a_json_file(page, static_url):
    open_dashboard(page, static_url)
    page.route("**/api/me/export", lambda route: route.fulfill(
        status=200, body='{"account": {"pseudo": "Vesper"}}', content_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="lantern-hollow-mes-donnees-2026-11-23.json"'}))
    with page.expect_download() as download_info:
        page.click("#export-data-btn")
    download = download_info.value
    assert download.suggested_filename == "lantern-hollow-mes-donnees-2026-11-23.json"
    expect(page.locator("#export-error")).to_be_hidden()
    expect(page.locator("#export-data-btn")).to_be_enabled()


def test_export_error_is_shown(page, static_url):
    open_dashboard(page, static_url)
    page.route("**/api/me/export", lambda route: route.fulfill(status=500, body="erreur"))
    page.click("#export-data-btn")
    expect(page.locator("#export-error")).to_have_text("Le téléchargement a échoué. Réessayez.")


def test_profile_shows_and_changes_the_email(page, static_url):
    api = open_dashboard(page, static_url)
    expect(page.locator("#profile-email")).to_have_text("vesper@exemple.fr")
    expect(page.locator("#profile-email-status")).to_have_text("Vérifiée")
    api.set("PATCH", "/api/account/email", 200, {**USER, "pending_email": "nouveau@exemple.fr"})
    page.fill("#new-email", "nouveau@exemple.fr")
    page.fill("#email-current-password", "mot-de-passe")
    page.click("#email-submit")
    expect(page.locator("#email-success")).to_contain_text("Un lien de confirmation a été envoyé à nouveau@exemple.fr")
    expect(page.locator("#profile-email")).to_have_text("vesper@exemple.fr")  # l'ancienne reste active
    expect(page.locator("#profile-pending")).to_contain_text("nouveau@exemple.fr")
    assert api.sent("PATCH", "/api/account/email") == [{"email": "nouveau@exemple.fr", "current_password": "mot-de-passe"}]


def test_change_email_error_is_shown(page, static_url):
    api = open_dashboard(page, static_url)
    api.set("PATCH", "/api/account/email", 409, {"detail": "Cette adresse e-mail est déjà utilisée par un autre compte."})
    page.fill("#new-email", "pris@exemple.fr")
    page.fill("#email-current-password", "mot-de-passe")
    page.click("#email-submit")
    expect(page.locator("#email-error")).to_have_text("Cette adresse e-mail est déjà utilisée par un autre compte.")


# --- Adresse pas encore vérifiée ------------------------------------------------------------

UNVERIFIED = {**USER, "email_verified": False}


def open_unverified(page, static_url, game=None):
    api = FakeApi(page, me=UNVERIFIED, game=game)
    page.goto(f"{static_url}/dashboard.html")
    expect(page.locator("#verify-section")).to_be_visible()
    return api


def test_unverified_account_sees_only_the_verification_screen(page, static_url):
    api = open_unverified(page, static_url)
    expect(page.locator("#verify-email")).to_have_text("vesper@exemple.fr")
    expect(page.locator("#dashboard-main")).to_be_hidden()
    expect(page.locator("#dashboard-nav")).to_be_hidden()
    expect(page.locator("#verify-resume")).to_be_hidden()
    assert api.sent("GET", "/api/me/stats") == []  # aucune donnée du tableau de bord demandée


def test_resend_the_verification_link(page, static_url):
    api = open_unverified(page, static_url)
    api.set("POST", "/api/account/verification-email", 200,
            {"message": "Un lien de confirmation vient d'être envoyé à vesper@exemple.fr (valable 24 heures)."})
    page.click("#verify-resend")
    expect(page.locator("#verify-message")).to_contain_text("vient d'être envoyé")


def test_resend_limit_is_explained(page, static_url):
    api = open_unverified(page, static_url)
    api.set("POST", "/api/account/verification-email", 429, {"detail": "Plusieurs liens viennent d'être envoyés."})
    page.click("#verify-resend")
    expect(page.locator("#verify-error")).to_have_text("Plusieurs liens viennent d'être envoyés.")


def test_fix_a_typo_in_the_address(page, static_url):
    api = open_unverified(page, static_url)
    api.set("PATCH", "/api/account/email", 200, {**UNVERIFIED, "email": "bonne@exemple.fr"})
    page.fill("#verify-fix-email", "bonne@exemple.fr")
    page.fill("#verify-fix-password", "mot-de-passe")
    page.click("#verify-fix-submit")
    expect(page.locator("#verify-email")).to_have_text("bonne@exemple.fr")
    expect(page.locator("#verify-message")).to_contain_text("un nouveau lien a été envoyé à bonne@exemple.fr")
    assert api.sent("PATCH", "/api/account/email") == [{"email": "bonne@exemple.fr", "current_password": "mot-de-passe"}]


def test_unverified_player_can_resume_the_game_claimed_at_signup(page, static_url):
    open_unverified(page, static_url, game={"running": True, "pseudo": "Lune", "turn": 2, "yours": True})
    expect(page.locator("#verify-resume")).to_be_visible()
    page.click("#verify-resume")
    page.wait_for_url("**/?play")


def test_pending_email_change_is_shown_in_the_profile(page, static_url):
    api = FakeApi(page, me={**USER, "pending_email": "nouveau@exemple.fr"})
    api.set("GET", "/api/me/stats", 200, STATS)
    api.set("GET", "/api/me/games", 200, GAMES)
    api.set("GET", "/api/me/achievements", 200, ACHIEVEMENTS)
    api.set("POST", "/api/account/verification-email", 200, {"message": "Lien renvoyé."})
    page.goto(f"{static_url}/dashboard.html")
    expect(page.locator("#profile-pending")).to_contain_text("nouveau@exemple.fr")
    page.click("#profile-pending-resend")
    expect(page.locator("#profile-pending-message")).to_have_text("Lien renvoyé.")


# --- Comparaison aux autres joueurs ------------------------------------------------------------

COMPARISON = {"available": True, "players": 12, "min_players": 10,
              "averages": {"played": 8.4, "win_rate": 0.5, "good_win_rate": 0.8, "evil_win_rate": 0.3,
                           "average_turns": 4.2},
              "achievements": {"win_reaper": 25, "executed": 40, "one_turn_win": 5}}


def test_comparison_with_other_players(page, static_url):
    api = FakeApi(page, me=USER)
    api.set("GET", "/api/me/stats", 200, STATS)  # 75 % de victoires, 67 % côté villageois, 100 % côté démons
    api.set("GET", "/api/me/games", 200, GAMES)
    api.set("GET", "/api/me/achievements", 200, ACHIEVEMENTS)
    api.set("GET", "/api/me/comparison", 200, COMPARISON)
    page.goto(f"{static_url}/dashboard.html")

    expect(page.locator("#cmp-win-rate")).to_contain_text("Tous les joueurs : 50 %")
    expect(page.locator("#cmp-win-rate")).to_have_attribute("data-trend", "above")
    expect(page.locator("#cmp-good-rate")).to_have_attribute("data-trend", "below")  # 67 % contre 80 %
    expect(page.locator("#cmp-played")).to_contain_text("8.4 parties en moyenne")
    expect(page.locator("#cmp-turns")).to_contain_text("4.2 tours")
    expect(page.locator("#cmp-turns .trend")).to_have_count(0)  # pas de « mieux » pour le nombre de tours
    expect(page.locator(".achievement[data-code='win_reaper']")).to_contain_text("Débloqué par 25 % des joueurs")
    expect(page.locator(".achievement[data-code='one_turn_win']")).to_contain_text("Débloqué par 5 % des joueurs")
    expect(page.locator("#comparison-notice")).to_be_hidden()


def test_comparison_needs_10_players(page, static_url):
    api = FakeApi(page, me=USER)
    api.set("GET", "/api/me/stats", 200, STATS)
    api.set("GET", "/api/me/games", 200, GAMES)
    api.set("GET", "/api/me/achievements", 200, ACHIEVEMENTS)
    api.set("GET", "/api/me/comparison", 200, {"available": False, "players": 4, "min_players": 10})
    page.goto(f"{static_url}/dashboard.html")
    expect(page.locator("#comparison-notice")).to_have_text(
        "La comparaison aux autres joueurs apparaîtra quand au moins 10 joueurs auront joué (4 pour l'instant).")
    expect(page.locator(".stat-compare:not(:empty)")).to_have_count(0)
    expect(page.locator(".achievement-rarity")).to_have_count(0)
