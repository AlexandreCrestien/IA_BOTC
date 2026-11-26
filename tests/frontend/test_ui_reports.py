"""Signalement d'un message d'agent IA depuis le chat : réservé aux joueurs connectés, catégories,
commentaire facultatif (obligatoire pour « Autre »), réponse du serveur, état « Signalé » à la reconnexion."""
from playwright.sync_api import expect

from conftest import ID, PLAYER, players
from test_ui_accounts import USER, FakeApi, join_as_guest

AGENT = "Lord Ashcombe"


def logged_in_game(page, server, static_url):
    """Joueur connecté qui rejoint sa partie (lien ?play du tableau de bord)."""
    FakeApi(page, me=USER)
    page.goto(f"{static_url}/index.html?play")
    expect(page.locator("#screen-game")).to_be_visible()
    server.send(type="game_state", state={"phase": "discussion", "day": 2, "aliveCount": 6, "players": players()})
    expect(page.locator("#game-phase")).to_have_text("Jour")
    return page


def agent_message(server, message_id="m1", content="Vesper cache quelque chose.", reported=False):
    server.send(type="chat", channel_id="public", sender=ID[AGENT], content=content,
                message_id=message_id, reported=reported)


def open_report(page):
    page.locator(".chat-message").last.hover()
    page.click("[data-action='open-report']")
    expect(page.locator("#modal-report")).to_be_visible()


def test_guest_sees_no_report_button(page, server, static_url):
    FakeApi(page)
    page.goto(f"{static_url}/index.html")
    join_as_guest(page, server)
    agent_message(server)
    expect(page.locator(".chat-bubble").last).to_have_text("Vesper cache quelque chose.")
    expect(page.locator("[data-action='open-report']")).to_have_count(0)


def test_only_agent_messages_can_be_reported(page, server, static_url):
    logged_in_game(page, server, static_url)
    server.send(type="chat", channel_id="public", sender="Codex", content="Annonce", message_id=None)
    server.send(type="chat", channel_id="public", sender=PLAYER, content="Bonsoir", message_id=None)
    agent_message(server)
    expect(page.locator("[data-action='open-report']")).to_have_count(1)


def test_report_with_a_category_and_an_optional_comment(page, server, static_url):
    logged_in_game(page, server, static_url)
    agent_message(server)
    open_report(page)
    expect(page.locator("#report-quote")).to_have_text(f"{AGENT} : « Vesper cache quelque chose. »")
    expect(page.locator("#report-categories input")).to_have_count(5)

    page.click("#report-submit")
    expect(page.locator("#report-error")).to_have_text("Choisissez le problème.")

    page.check("#report-categories input[value='knowledge']")
    expect(page.locator("#report-comment-label")).to_have_text("Commentaire (facultatif)")
    expect(page.locator("#report-comment")).to_have_attribute("maxlength", "200")
    page.fill("#report-comment", "Il connaît mon rôle")
    expect(page.locator("#report-count")).to_have_text("19 / 200")
    page.click("#report-submit")
    assert server.wait_for("report_message") == {"message_id": "m1", "category": "knowledge",
                                                 "comment": "Il connaît mon rôle"}

    server.send(type="report_result", message_id="m1", error=None)
    expect(page.locator("#modal-report")).to_be_hidden()
    expect(page.locator(".report-done")).to_have_text("Signalé")
    expect(page.locator("[data-action='open-report']")).to_have_count(0)
    expect(page.locator("#chat-messages")).to_contain_text("Merci : votre signalement a été transmis à l'équipe.")


def test_other_requires_a_longer_comment(page, server, static_url):
    logged_in_game(page, server, static_url)
    agent_message(server)
    open_report(page)
    page.check("#report-categories input[value='other']")
    expect(page.locator("#report-comment-label")).to_have_text("Décrivez le problème (obligatoire)")
    expect(page.locator("#report-comment")).to_have_attribute("maxlength", "500")
    expect(page.locator("#report-count")).to_have_text("0 / 500")
    page.fill("#report-comment", "   ")  # que des espaces : pas un commentaire
    page.click("#report-submit")
    expect(page.locator("#report-error")).to_have_text("Décrivez le problème en quelques mots.")
    assert server.actions("report_message") == []


def test_refusal_is_shown_in_the_window(page, server, static_url):
    logged_in_game(page, server, static_url)
    agent_message(server)
    open_report(page)
    page.check("#report-categories input[value='rules']")
    page.click("#report-submit")
    server.wait_for("report_message")
    server.send(type="report_result", message_id="m1", error="Vous avez atteint la limite de 10 signalements.")
    expect(page.locator("#report-error")).to_have_text("Vous avez atteint la limite de 10 signalements.")
    expect(page.locator("#report-submit")).to_be_enabled()


def test_cancel_and_escape_close_the_window(page, server, static_url):
    logged_in_game(page, server, static_url)
    agent_message(server)
    open_report(page)
    page.click("#modal-report [data-action='close-report'].btn-ghost")
    expect(page.locator("#modal-report")).to_be_hidden()
    open_report(page)
    page.keyboard.press("Escape")
    expect(page.locator("#modal-report")).to_be_hidden()


def test_already_reported_message_after_reconnection(page, server, static_url):
    logged_in_game(page, server, static_url)
    agent_message(server, reported=True)
    expect(page.locator(".report-done")).to_be_visible()
    expect(page.locator("[data-action='open-report']")).to_have_count(0)


def test_guest_who_registers_during_the_game_can_report(page, server, static_url):
    api = FakeApi(page)
    page.goto(f"{static_url}/index.html")
    join_as_guest(page, server)
    agent_message(server)
    expect(page.locator("[data-action='open-report']")).to_have_count(0)

    api.set("POST", "/api/auth/login", 200, {**USER, "game_claimed": True, "achievements": []})
    page.click("#menu-btn")
    page.click("#menu-login")
    page.fill("#account-pseudo", PLAYER)
    page.fill("#account-password", "mot-de-passe")
    page.click("#account-submit")
    expect(page.locator("[data-action='open-report']")).to_have_count(1)
