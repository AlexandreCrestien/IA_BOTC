"""Page d'administration, avec l'API /admin/debug/all-states simulée."""
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
}


def mock_api(page, status=200, body=ADMIN_DATA):
    page.route(API, lambda route: route.fulfill(status=status, body=json.dumps(body),
                                                content_type="application/json"))


def login(page, static_url, token="jeton"):
    page.goto(f"{static_url}/admin.html")
    page.fill("#admin-token-input", token)
    page.press("#admin-token-input", "Enter")


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


def test_rejected_token_returns_to_login(page, static_url):
    mock_api(page, status=403, body={"detail": "Accès refusé"})
    login(page, static_url)

    expect(page.locator("#login-error")).to_have_text("Jeton administrateur invalide.")
    expect(page.locator("#dashboard-section")).to_be_hidden()
    assert page.evaluate("localStorage.getItem('botc_admin_token')") is None


def test_empty_api_response_shows_notice(page, static_url):
    # La route renvoie aujourd'hui null (TODO côté serveur)
    mock_api(page, body=None)
    login(page, static_url)

    expect(page.locator("#no-data-notice")).to_contain_text("ne renvoie pas encore de données")
    expect(page.locator("#stat-turn-phase")).to_have_text("—")


def test_missing_fields_are_shown_as_unknown(page, static_url):
    mock_api(page, body={})
    login(page, static_url)

    expect(page.locator("#no-data-notice")).to_be_hidden()
    expect(page.locator("#stat-agents-count")).to_have_text("—")
    expect(page.locator("#agents-tabs-container")).to_contain_text("Aucun agent disponible.")


def test_logout_clears_the_token(page, static_url):
    mock_api(page)
    login(page, static_url)
    page.click("#logout-btn")

    expect(page.locator("#login-section")).to_be_visible()
    assert page.evaluate("localStorage.getItem('botc_admin_token')") is None
