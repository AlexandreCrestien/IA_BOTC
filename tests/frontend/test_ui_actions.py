"""Encadré d'action de la sidebar droite : discussion, vote, nuit."""
from playwright.sync_api import expect

from conftest import ALL_PLAYERS, PLAYER


def option(page, name):
    return page.locator(".option-btn", has_text=name)


def test_panel_is_hidden_without_pending_action(game):
    expect(game.locator("#action-zone")).to_be_hidden()


def test_discussion_excludes_the_player_and_allows_two_targets(game, server):
    server.send(type="action_request", kind="discussion", candidates=ALL_PLAYERS, max_targets=2)

    expect(game.locator(".option-btn")).to_have_count(5)  # tout le monde sauf soi (morts compris)
    expect(game.locator("#dynamic-action-panel")).not_to_contain_text(PLAYER)

    option(game, "Lord Ashcombe").click()
    option(game, "Dr. Thorne").click()
    expect(option(game, "Mère Grimsby")).to_be_disabled()  # maximum atteint
    expect(game.locator("#action-counter")).to_have_text("2/2 joueur(s) sélectionné(s)")

    game.click("#action-submit")
    assert server.wait_for("request_whisper") == {"targets": ["Lord Ashcombe", "Dr. Thorne"]}
    expect(game.locator("#action-zone")).to_be_hidden()


def test_vote_excludes_player_and_dead_then_shows_loader_and_results(game, server):
    server.send(type="action_request", kind="vote", candidates=ALL_PLAYERS)

    expect(game.locator(".option-btn")).to_have_count(5)  # 4 vivants (ni soi, ni Dr. Thorne) + "Personne"
    expect(option(game, "Dr. Thorne")).to_have_count(0)
    expect(game.locator("#action-submit")).to_be_disabled()

    option(game, "Personne").click()
    game.click("#action-submit")
    assert server.wait_for("submit_vote") == {"target_id": None}
    expect(game.locator("#action-submit .action-spinner")).to_be_visible()

    server.send(type="vote_result", turn=2, executed="Mère Grimsby", votes=[
        {"voter": "Lord Ashcombe", "target": "Mère Grimsby"},
        {"voter": "Révérend Hale", "target": "Mère Grimsby"},
        {"voter": "Dr. Thorne", "target": "Lord Ashcombe", "ghost": True},
        {"voter": PLAYER, "target": None},
    ])
    panel = game.locator("#dynamic-action-panel")
    expect(panel).to_contain_text("Mère Grimsby est exécuté·e avec 2 voix.")
    expect(game.locator(".ballot")).to_have_count(4)
    expect(game.locator(".ballot", has_text="Dr. Thorne")).to_contain_text("(vote fantôme)")
    # Le joueur exécuté ce tour-ci votait vivant : pas de mention
    expect(game.locator(".ballot", has_text="Lord Ashcombe").first).not_to_contain_text("(vote fantôme)")


def test_next_action_waits_while_a_result_is_displayed(game, server):
    server.send(type="vote_result", turn=2, executed=None, votes=[])
    server.send(type="phase_update", phase="nuit")
    server.send(type="action_request", kind="nuit", candidates=ALL_PLAYERS, max_targets=1, role="monk")

    expect(game.locator("#dynamic-action-panel")).to_contain_text("Résultats du vote")
    game.click("[data-action='close-result']")
    expect(game.locator("#dynamic-action-panel")).to_contain_text("Pouvoir : Moine")


def test_night_action_needs_exact_targets_and_shows_server_answer(game, server):
    server.send(type="phase_update", phase="nuit")
    server.send(type="action_request", kind="nuit", candidates=ALL_PLAYERS, max_targets=2, role="psychic")
    expect(game.locator("#dynamic-action-panel")).to_contain_text("Pouvoir : Voyante")

    option(game, "Lord Ashcombe").click()
    expect(game.locator("#action-submit")).to_be_disabled()  # la Voyante doit choisir 2 joueurs
    option(game, "Mère Grimsby").click()
    game.click("#action-submit")
    assert server.wait_for("submit_night_action") == {"targets": ["Lord Ashcombe", "Mère Grimsby"]}

    server.send(type="night_info", turn=2, info="L'un des deux est le Démon.")
    expect(game.locator("#dynamic-action-panel")).to_contain_text("L'un des deux est le Démon.")
    expect(game.locator("#modal-night-info")).to_be_hidden()  # affiché dans l'encadré, pas en modale


def test_server_error_lets_the_player_choose_again(game, server):
    server.send(type="phase_update", phase="nuit")
    server.send(type="action_request", kind="nuit", candidates=ALL_PLAYERS, max_targets=1, role="imp")
    option(game, "Lord Ashcombe").click()
    game.click("#action-submit")
    server.wait_for("submit_night_action")

    server.send(type="error", data="Cible invalide.")
    expect(game.locator("#action-submit")).to_be_enabled()
    expect(game.locator("#chat-messages")).to_contain_text("Cible invalide.")


def test_discussion_can_be_skipped_to_go_to_the_vote(game, server):
    server.send(type="action_request", kind="discussion", candidates=ALL_PLAYERS, max_targets=2, min_targets=1)
    skip = game.locator("#action-skip")
    expect(skip).to_have_text("Passer au vote")

    skip.click()
    assert server.wait_for("skip_turn") == {"kind": "private_partners"}
    expect(game.locator("#action-zone")).to_be_hidden()


def test_skip_button_only_for_the_discussion(game, server):
    server.send(type="action_request", kind="vote", candidates=ALL_PLAYERS)
    expect(game.locator("#dynamic-action-panel")).to_contain_text("Sceller mon vote")
    expect(game.locator("#action-skip")).to_have_count(0)


# --- Sans choix pendant 10 s, un agent vient proposer un entretien ------------------

INVITATION_DELAY_MS = 10_000


def show_discussion(game, server):
    game.clock.install()  # temps simulé : les 10 s s'écoulent à la demande
    server.send(type="action_request", kind="discussion", candidates=ALL_PLAYERS, max_targets=2, min_targets=1)
    expect(game.locator("#action-skip")).to_be_visible()


def test_no_choice_during_the_delay_asks_for_an_agent(game, server):
    show_discussion(game, server)

    game.clock.run_for(INVITATION_DELAY_MS - 1000)
    assert server.actions("discussion_timeout") == []

    game.clock.run_for(1000)
    server.wait_for("discussion_timeout")
    expect(game.locator("#action-zone")).to_be_hidden()


def test_starting_to_choose_cancels_the_delay(game, server):
    show_discussion(game, server)
    option(game, "Lord Ashcombe").click()

    game.clock.run_for(INVITATION_DELAY_MS * 2)
    assert server.actions("discussion_timeout") == []
    expect(game.locator("#action-zone")).to_be_visible()


def test_skipping_to_the_vote_cancels_the_delay(game, server):
    show_discussion(game, server)
    game.click("#action-skip")
    server.wait_for("skip_turn")

    game.clock.run_for(INVITATION_DELAY_MS * 2)
    assert server.actions("discussion_timeout") == []


def test_delay_waits_while_a_modal_is_open(game, server):
    show_discussion(game, server)
    server.send(type="night_result", turn=2, dead_player=None)
    expect(game.locator("#modal-night-result")).to_be_visible()

    game.clock.run_for(INVITATION_DELAY_MS * 2)
    assert server.actions("discussion_timeout") == []

    game.click("[data-action='close-night-result']")
    game.clock.run_for(INVITATION_DELAY_MS)
    server.wait_for("discussion_timeout")
