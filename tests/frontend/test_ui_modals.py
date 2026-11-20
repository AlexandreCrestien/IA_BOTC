"""Modales : rôle, entretien, exécution, réveil, fin de partie, connexion perdue, Grimoire."""
from playwright.sync_api import expect

from conftest import PLAYER


def test_role_reveal_fills_the_role_bar(game, server):
    server.send(type="role_assigned", role_name="Moine", description="Protégez un joueur chaque nuit.")
    expect(game.locator("#modal-role-reveal")).to_be_visible()
    expect(game.locator("#modal-role-title")).to_have_text("Moine")

    game.click("[data-action='close-role-reveal']")
    expect(game.locator("#modal-role-reveal")).to_be_hidden()
    expect(game.locator("#player-role-name")).to_have_text("Moine")


def test_agent_whisper_accept_waits_for_the_server_channel(game, server):
    server.send(type="agent_whisper_request", agent_id="Mère Grimsby", agent_name="Mère Grimsby")
    expect(game.locator("#agent-whisper-text")).to_contain_text("Mère Grimsby souhaite s'entretenir")

    game.click("[data-action='accept-whisper']")
    assert server.wait_for("respond_whisper_invitation") == {"target_agent_id": "Mère Grimsby", "accepted": True}
    expect(game.locator("#modal-agent-whisper")).to_be_hidden()
    expect(game.locator("#chat-channels .channel-btn")).to_have_count(0)  # pas de salon inventé côté client


def test_agent_whisper_refuse_then_trigger_vote(game, server):
    server.send(type="agent_whisper_request", agent_id="Mère Grimsby", agent_name="Mère Grimsby")
    game.click("[data-action='refuse-whisper']")
    assert server.wait_for("respond_whisper_invitation")["accepted"] is False

    game.click("[data-action='whisper-vote']")
    server.wait_for("trigger_vote_phase")
    expect(game.locator("#modal-agent-whisper")).to_be_hidden()


def test_execution_modal_only_when_the_player_is_executed(game, server):
    server.send(type="vote_result", turn=2, executed="Mère Grimsby", votes=[])
    expect(game.locator("#modal-vote-result")).to_be_hidden()

    server.send(type="vote_result", turn=3, executed=PLAYER, votes=[])
    expect(game.locator("#modal-vote-result")).to_be_visible()
    expect(game.locator("#vote-death-notice")).to_be_visible()


def test_dawn_modal_announces_the_night_victim(game, server):
    server.send(type="night_result", turn=3, dead_player="Révérend Hale")
    expect(game.locator("#night-result-message")).to_contain_text("Révérend Hale est mort·e cette nuit.")
    expect(game.locator("#night-death-notice")).to_be_hidden()

    game.click("[data-action='close-night-result']")
    server.send(type="night_result", turn=4, dead_player=None)
    expect(game.locator("#night-result-message")).to_contain_text("Personne n'est mort")


def test_game_over_tells_if_the_player_won(game, server):
    server.send(type="role_assigned", role_name="Diablotin", description="…")
    game.click("[data-action='close-role-reveal']")
    server.send(type="game_over", winner="Villageois", details="Le Diablotin a été exécuté.")

    expect(game.locator("#gameover-title")).to_have_text("Victoire des Villageois")
    expect(game.locator("#gameover-outcome")).to_have_text("Votre camp a perdu…")


def test_disconnection_shows_modal(game, server):
    server.close()
    expect(game.locator("#modal-disconnected")).to_be_visible()
    expect(game.locator("#connection-status")).to_have_text("Déconnecté")

    game.click("[data-action='close-disconnected']")
    expect(game.locator("#modal-disconnected")).to_be_hidden()


def test_grimoire_tabs_backdrop_and_escape(game):
    game.click("[data-action='open-grimoire']")
    grimoire = game.locator("#modal-grimoire")
    expect(grimoire).to_be_visible()

    game.click("#grimoire-tab-btn-rules")
    expect(game.locator("#grimoire-tab-rules")).to_be_visible()
    expect(game.locator("#grimoire-tab-roles")).to_be_hidden()

    game.locator("#modal-grimoire .modal-card").click()  # un clic sur la carte ne ferme pas
    expect(grimoire).to_be_visible()
    grimoire.click(position={"x": 5, "y": 5})  # un clic sur le voile ferme
    expect(grimoire).to_be_hidden()

    game.click("[data-action='open-grimoire']")
    game.keyboard.press("Escape")
    expect(grimoire).to_be_hidden()


def test_abandon_asks_for_confirmation_and_can_be_cancelled(game, server):
    game.click("#abandon-btn")
    expect(game.locator("#modal-abandon")).to_be_visible()

    game.click("button[data-action='cancel-abandon']")
    expect(game.locator("#modal-abandon")).to_be_hidden()
    assert server.actions("abandon_game") == []


def test_abandon_returns_to_welcome_for_a_new_game(game, server):
    game.click("#abandon-btn")
    game.click("button[data-action='confirm-abandon']")
    server.wait_for("abandon_game")

    server.send(type="game_abandoned")
    expect(game.locator("#screen-welcome")).to_be_visible()  # page rechargée : accueil vierge
    expect(game.locator("#welcome-player-id")).to_have_value("")
    expect(game.locator("#modal-disconnected")).to_be_hidden()


def test_abandon_after_game_over_goes_straight_to_welcome(game, server):
    server.send(type="game_over", winner="Villageois", details="Fin.")
    game.click("#modal-gameover [data-action='reload']")  # bouton « Nouvelle partie » de la fin de partie
    expect(game.locator("#screen-welcome")).to_be_visible()
    assert server.actions("abandon_game") == []


def test_server_crash_offers_a_new_game(game, server):
    server.send(type="game_interrupted", text="Une erreur a interrompu la partie.")
    expect(game.locator("#gameover-title")).to_have_text("Partie interrompue")
    expect(game.locator("#gameover-desc")).to_have_text("Une erreur a interrompu la partie.")
    expect(game.locator("#gameover-outcome")).to_be_hidden()


def test_role_reveal_is_read_before_the_dawn_modal(game, server):
    """Au démarrage, le réveil du village peut arriver en même temps que le rôle : le rôle passe devant."""
    server.send(type="role_assigned", role_name="Moine", description="Protégez un joueur.")
    server.send(type="night_result", turn=1, dead_player=None)
    expect(game.locator("#modal-night-result")).to_be_visible()

    game.click("[data-action='close-role-reveal']")  # cliquable : la modale du rôle est au-dessus
    expect(game.locator("#modal-role-reveal")).to_be_hidden()
    game.click("[data-action='close-night-result']")
    expect(game.locator("#modal-night-result")).to_be_hidden()


def test_game_over_is_above_other_modals(game, server):
    server.send(type="night_result", turn=3, dead_player="Révérend Hale")
    server.send(type="game_over", winner="Villageois", details="Fin.")
    game.click("#modal-gameover [data-action='reload']")  # cliquable : la fin de partie est au-dessus
    expect(game.locator("#screen-welcome")).to_be_visible()
