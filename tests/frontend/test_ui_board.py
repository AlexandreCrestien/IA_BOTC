"""État de la partie : en-tête, table ronde, liste des convives, soupçons."""
from playwright.sync_api import expect

from conftest import AGENTS, PLAYER


def test_header_shows_turn_phase_and_alive_count(game, server):
    expect(game.locator("#game-day")).to_have_text("2")
    expect(game.locator("#alive-count")).to_have_text("5")

    server.send(type="phase_update", phase="vote", announcement="Le vote est ouvert.")
    expect(game.locator("#game-phase")).to_have_text("Vote")
    expect(game.locator("#game-announcement")).to_have_text("Le vote est ouvert.")
    expect(game.locator("#center-stage")).to_have_attribute("data-phase", "vote")


def test_round_table_seats_every_player(game):
    seats = game.locator("#round-table-seats .seat")
    expect(seats).to_have_count(6)
    expect(game.locator(".seat.is-me .seat-name")).to_have_text(f"{PLAYER} (vous)")
    expect(game.locator(".seat.is-dead .seat-name")).to_have_text("Dr. Thorne (mort)")


def test_players_list_excludes_the_player_and_shows_status(game):
    cards = game.locator("#players-notes-list .player-card")
    expect(cards).to_have_count(len(AGENTS))
    expect(game.locator("#players-notes-list")).not_to_contain_text(PLAYER)
    expect(game.locator("#players-count")).to_have_text("5 vivant·e·s · 1 mort·e·s")
    expect(cards.filter(has_text="Dr. Thorne").locator(".status-dead")).to_contain_text("Mort")


def test_own_role_is_removed_from_suspicions(game, server):
    server.send(type="role_assigned", role_name="Voyante", description="Sondez deux joueurs.")
    game.click("[data-action='close-role-reveal']")

    options = game.locator(".suspicion-select").first.locator("option")
    expect(options.filter(has_text="Voyante")).to_have_count(0)
    expect(options.filter(has_text="Moine")).to_have_count(1)


def test_suspicion_survives_a_server_update(game, server):
    game.locator(".suspicion-select").first.select_option("moine")
    server.send(type="game_state", state={"aliveCount": 5})
    expect(game.locator(".suspicion-select").first).to_have_value("moine")


def test_evil_player_sees_suspicions_locked_until_allies_are_revealed(game, server):
    server.send(type="role_assigned", role_name="Diablotin", description="Choisissez une victime.")
    game.click("[data-action='close-role-reveal']")
    expect(game.locator(".suspicion-select:disabled")).to_have_count(len(AGENTS))

    server.send(type="night_info", turn=1, info="Votre allié est Mère Grimsby.",
                allies=[{"id": "Mère Grimsby", "role": "poisoner"}])
    game.click("[data-action='close-night-info']")

    expect(game.locator(".ally-tag")).to_have_text("Votre allié · Empoisonneur")
    expect(game.locator(".player-card").first).to_contain_text("Mère Grimsby")  # allié en tête
    good_only = game.locator(".suspicion-select").first.locator("option")
    expect(good_only.filter(has_text="Diablotin")).to_have_count(0)
    expect(game.locator(".suspicion-select:disabled")).to_have_count(0)
