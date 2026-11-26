"""Page ouverte depuis le lien de vérification reçu par e-mail (route /api simulée)."""
from playwright.sync_api import expect

from test_ui_accounts import FakeApi, USER


def test_link_confirms_the_address(page, static_url):
    api = FakeApi(page)
    api.set("POST", "/api/auth/verify-email", 200, {"message": "Adresse e-mail confirmée.", "pseudo": "Vesper",
                                                    "email": "vesper@exemple.fr"})
    page.goto(f"{static_url}/verify-email.html?token=jeton-secret")
    expect(page.locator("#verify-title")).to_have_text("Adresse confirmée")
    expect(page.locator("#verify-status")).to_contain_text("vesper@exemple.fr")
    expect(page.locator("#verify-continue")).to_be_visible()
    assert "jeton-secret" not in page.url
    assert api.sent("POST", "/api/auth/verify-email") == [{"token": "jeton-secret"}]


def test_expired_link_is_explained(page, static_url):
    api = FakeApi(page)
    api.set("POST", "/api/auth/verify-email", 400, {"detail": "Ce lien de vérification n'est plus valable."})
    page.goto(f"{static_url}/verify-email.html?token=perime")
    expect(page.locator("#verify-title")).to_have_text("Lien non valable")
    expect(page.locator("#verify-status")).to_have_text("Ce lien de vérification n'est plus valable.")
    expect(page.locator("#verify-continue")).to_be_hidden()


def test_link_without_token(page, static_url):
    FakeApi(page)
    page.goto(f"{static_url}/verify-email.html")
    expect(page.locator("#verify-title")).to_have_text("Lien incomplet")


def test_unverified_account_on_the_welcome_goes_to_the_verification_screen(page, static_url):
    FakeApi(page, me={**USER, "email_verified": False})
    page.goto(f"{static_url}/index.html?play")
    page.wait_for_url("**/dashboard.html")
