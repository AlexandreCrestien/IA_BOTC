"""Évaluation des agents IA sur l'écran de fin : proposée au joueur connecté après une partie terminée,
une note par agent (au moins une) et un commentaire facultatif, puis « Merci » et une nouvelle partie."""
from playwright.sync_api import expect

from conftest import ID
from test_ui_accounts import USER, FakeApi, join_as_guest
from test_ui_reports import logged_in_game


def game_over(server):
    server.send(type="game_over", winner="good", details="Le village a rendu son dernier verdict.", achievements=[])


def open_rating(page, server, static_url):
    logged_in_game(page, server, static_url)
    game_over(server)
    expect(page.locator("#gameover-rate")).to_be_visible()
    page.click("[data-action='open-rating']")
    expect(page.locator("#modal-rating")).to_be_visible()
    expect(page.locator("#modal-gameover")).to_be_hidden()


def star(page, agent, score):
    page.click(f"label[for='rating-{ID[agent]}-{score}']")


def test_end_screen_offers_to_rate_the_agents_or_play_again(page, server, static_url):
    logged_in_game(page, server, static_url)
    game_over(server)
    expect(page.locator("#gameover-rate")).to_contain_text("Ça ne prendra que 2 minutes.")
    expect(page.locator("#modal-gameover [data-action='new-game']")).to_be_visible()


def test_guest_is_not_offered_to_rate(page, server, static_url):
    FakeApi(page)
    page.goto(f"{static_url}/index.html")
    join_as_guest(page, server)
    game_over(server)
    expect(page.locator("#modal-gameover")).to_be_visible()
    expect(page.locator("#gameover-rate")).to_be_hidden()


def test_interrupted_game_cannot_be_rated(page, server, static_url):
    logged_in_game(page, server, static_url)
    server.send(type="game_interrupted", text="Une erreur a interrompu la partie.")
    expect(page.locator("#modal-gameover")).to_be_visible()
    expect(page.locator("#gameover-rate")).to_be_hidden()


def test_rating_sends_the_rated_agents_then_thanks(page, server, static_url):
    open_rating(page, server, static_url)
    agents = page.locator("#rating-agents .rating-agent")
    expect(agents).to_have_count(5)  # tous les personnages sauf le joueur

    page.click("#rating-submit")
    expect(page.locator("#rating-error")).to_have_text("Donnez une note à au moins un personnage.")

    star(page, "Lord Ashcombe", 4)
    agents.nth(0).locator("textarea").fill("  Très crédible  ")
    star(page, "Dr. Thorne", 2)
    page.click("#rating-submit")
    assert server.wait_for("rate_agents") == {"ratings": [
        {"agent_id": ID["Lord Ashcombe"], "score": 4, "comment": "Très crédible"},
        {"agent_id": ID["Dr. Thorne"], "score": 2, "comment": None},
    ]}

    server.send(type="rating_result", error=None)
    expect(page.locator("#rating-thanks")).to_be_visible()
    expect(page.locator("#rating-thanks")).to_contain_text("Merci !")
    expect(page.locator("#rating-thanks [data-action='new-game']")).to_be_visible()
    expect(page.locator("#rating-form")).to_be_hidden()


def test_refusal_is_shown_and_can_be_retried(page, server, static_url):
    open_rating(page, server, static_url)
    star(page, "Lord Ashcombe", 3)
    page.click("#rating-submit")
    server.wait_for("rate_agents")
    expect(page.locator("#rating-submit")).to_be_disabled()
    server.send(type="rating_result", error="L'évaluation n'a pas pu être enregistrée. Réessayez plus tard.")
    expect(page.locator("#rating-error")).to_contain_text("Réessayez plus tard.")
    expect(page.locator("#rating-submit")).to_be_enabled()


def test_back_returns_to_the_end_screen(page, server, static_url):
    open_rating(page, server, static_url)
    page.click("[data-action='close-rating']")
    expect(page.locator("#modal-rating")).to_be_hidden()
    expect(page.locator("#modal-gameover")).to_be_visible()
    expect(page.locator("#gameover-rate")).to_be_visible()


def test_comment_is_limited_to_300_characters(page, server, static_url):
    open_rating(page, server, static_url)
    expect(page.locator("#rating-agents textarea").first).to_have_attribute("maxlength", "300")


def test_guest_who_registers_on_the_end_screen_can_rate(page, server, static_url):
    api = FakeApi(page)
    page.goto(f"{static_url}/index.html")
    join_as_guest(page, server)
    server.send(type="guest_session", guest_token="jeton")
    game_over(server)
    expect(page.locator("#gameover-rate")).to_be_hidden()

    api.set("POST", "/api/auth/login", 200, {**USER, "game_claimed": True, "achievements": []})
    page.click("#gameover-register [data-mode='login']")
    page.fill("#account-pseudo", USER["pseudo"])
    page.fill("#account-password", "mot-de-passe")
    page.click("#account-submit")
    expect(page.locator("#gameover-rate")).to_be_visible()
