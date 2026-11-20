"""Sidebar gauche : chat public, salons privés, pastille de nouveaux messages, historiques."""
from playwright.sync_api import expect

from conftest import PLAYER

PRIVATE = f"whisper_{PLAYER}_Mère Grimsby"


def test_enter_sends_message_and_shift_enter_does_not(game, server):
    game.fill("#chat-input", "Bonjour le village")
    game.press("#chat-input", "Shift+Enter")
    assert server.actions("send_chat") == []

    game.press("#chat-input", "Enter")
    assert server.wait_for("send_chat") == {"channel_id": "public", "content": "Bonjour le village"}
    expect(game.locator("#chat-input")).to_have_value("")


def test_received_message_is_displayed_with_its_time(game, server):
    server.send(type="chat", channel_id="public", sender="Lord Ashcombe", content="Je soupçonne <b>Dr. Thorne</b>.")
    message = game.locator(".chat-bubble").last
    expect(message).to_have_text("Je soupçonne <b>Dr. Thorne</b>.")  # HTML affiché comme du texte
    expect(game.locator("#chat-messages")).to_contain_text("Lord Ashcombe")


def test_system_messages_survive_new_messages(game, server):
    expect(game.locator("#chat-messages")).to_contain_text("Connexion établie avec le serveur.")
    server.send(type="chat", channel_id="public", sender="Lord Ashcombe", content="Bonjour")
    expect(game.locator("#chat-messages")).to_contain_text("Connexion établie avec le serveur.")


def test_private_channel_opens_and_public_badge_appears(game, server):
    server.send(type="private_channel_opened", channel_id=PRIVATE,
                members=[PLAYER, "Mère Grimsby"], text="Salon privé ouvert avec Mère Grimsby")
    expect(game.locator("#active-channel-title")).to_have_text("Mère Grimsby")
    expect(game.locator(f"[data-channel='{PRIVATE}']")).to_have_class("channel-btn is-active")

    server.send(type="chat", channel_id="public", sender="Lord Ashcombe", content="Où êtes-vous ?")
    expect(game.locator("#unread-public")).to_be_visible()

    game.click("#tab-public")
    expect(game.locator("#unread-public")).to_be_hidden()
    expect(game.locator("#chat-messages")).to_contain_text("Où êtes-vous ?")


def test_chat_tab_badge_when_on_another_tab(game, server):
    game.click("#tab-btn-votes")
    expect(game.locator("#tab-content-votes")).to_be_visible()
    server.send(type="chat", channel_id="public", sender="Lord Ashcombe", content="Hé !")
    expect(game.locator("#unread-chat-tab")).to_be_visible()

    game.click("#tab-btn-chat")
    expect(game.locator("#unread-chat-tab")).to_be_hidden()


def test_vote_and_night_histories_are_recorded(game, server):
    server.send(type="vote_result", turn=2, executed=None,
                votes=[{"voter": "Lord Ashcombe", "target": "Mère Grimsby"}])
    server.send(type="night_result", turn=3, dead_player="Révérend Hale")
    game.click("[data-action='close-night-result']")

    game.click("#tab-btn-votes")
    expect(game.locator("#tab-content-votes")).to_contain_text("Lord Ashcombe a voté pour Mère Grimsby")
    game.click("#tab-btn-night")
    expect(game.locator("#tab-content-night")).to_contain_text("Révérend Hale est mort·e cette nuit.")


# --- Saisie attendue par le moteur (bandeau au-dessus du chat) -----------------

def test_public_message_prompt_can_be_skipped(game, server):
    server.send(type="input_request", kind="public_message", channel_id="public",
                text="C'est à vous de parler sur la place publique.")
    prompt = game.locator("#turn-prompt")
    expect(prompt).to_be_visible()
    expect(prompt).to_contain_text("C'est à vous de parler sur la place publique.")
    expect(game.locator("#turn-prompt-skip")).to_have_text("Passer")

    game.click("#turn-prompt-skip")
    assert server.wait_for("skip_turn") == {"kind": "public_message"}
    expect(prompt).to_be_hidden()


def test_writing_the_public_message_hides_the_prompt(game, server):
    server.send(type="input_request", kind="public_message", channel_id="public", text="À vous.")
    game.fill("#chat-input", "Je soupçonne Dr. Thorne.")
    game.press("#chat-input", "Enter")
    server.wait_for("send_chat")
    expect(game.locator("#turn-prompt")).to_be_hidden()
    assert server.actions("skip_turn") == []


def test_private_message_prompt_moves_to_the_salon_and_can_end_it(game, server):
    server.send(type="private_channel_opened", channel_id=PRIVATE,
                members=[PLAYER, "Mère Grimsby"], text="Salon privé ouvert avec Mère Grimsby")
    game.click("#tab-public")  # le joueur est retourné sur la place publique
    server.send(type="input_request", kind="private_message", channel_id=PRIVATE, left=2,
                text="Il vous reste 2 message(s) privé(s) avec vos interlocuteurs.")

    expect(game.locator("#active-channel-title")).to_have_text("Mère Grimsby")
    expect(game.locator("#turn-prompt-skip")).to_have_text("Terminer la discussion")
    game.click("#turn-prompt-skip")
    assert server.wait_for("skip_turn") == {"kind": "private_message"}


def test_new_step_hides_the_prompt(game, server):
    server.send(type="input_request", kind="public_message", channel_id="public", text="À vous.")
    server.send(type="action_request", kind="vote", candidates=["Lord Ashcombe"])
    expect(game.locator("#turn-prompt")).to_be_hidden()


# --- Reprise après rechargement -----------------------------------------------

def test_restored_salon_and_history_after_reconnection(game, server):
    # Ce que le serveur renvoie à la reconnexion : salon rouvert sans s'y placer, puis l'historique
    server.send(type="private_channel_opened", channel_id=PRIVATE,
                members=[PLAYER, "Mère Grimsby"], text="", focus=False)
    server.send(type="chat", channel_id="public", sender="Lord Ashcombe", content="Bonjour")
    server.send(type="chat", channel_id=PRIVATE, sender="Mère Grimsby", content="Approchez…")

    expect(game.locator(f"[data-channel='{PRIVATE}']")).to_be_visible()
    expect(game.locator("#active-channel-title")).to_have_text("Place publique")
    expect(game.locator("#chat-messages")).to_contain_text("Bonjour")

    game.click(f"[data-channel='{PRIVATE}']")
    expect(game.locator("#chat-messages")).to_contain_text("Approchez…")
