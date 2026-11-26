"""Page « nouveau mot de passe », ouverte depuis le lien reçu par e-mail (route /api simulée)."""
from playwright.sync_api import expect

from test_ui_accounts import FakeApi


def test_link_without_token_is_explained(page, static_url):
    FakeApi(page)
    page.goto(f"{static_url}/reset-password.html")
    expect(page.locator("#reset-invalid")).to_contain_text("Mot de passe oublié ?")
    expect(page.locator("#reset-form")).to_be_hidden()


def test_new_password_is_sent_and_welcome_confirms(page, static_url):
    api = FakeApi(page)
    api.set("POST", "/api/auth/reset-password", 200, {"message": "Mot de passe modifié."})
    page.goto(f"{static_url}/reset-password.html?token=jeton-secret")
    assert "jeton-secret" not in page.url  # retiré de l'adresse affichée

    page.fill("#reset-password", "nouveau-mdp")
    page.fill("#reset-password-confirm", "autre")
    page.click("#reset-btn")
    expect(page.locator("#reset-error")).to_have_text("Les deux mots de passe ne correspondent pas.")
    assert api.sent("POST", "/api/auth/reset-password") == []

    page.fill("#reset-password-confirm", "nouveau-mdp")
    page.click("#reset-btn")
    expect(page.locator("#welcome-notice")).to_contain_text("Votre mot de passe a été modifié")
    assert api.sent("POST", "/api/auth/reset-password") == [{"token": "jeton-secret", "new_password": "nouveau-mdp"}]


def test_expired_link_hides_the_form(page, static_url):
    api = FakeApi(page)
    api.set("POST", "/api/auth/reset-password", 400,
            {"detail": "Ce lien n'est plus valable (déjà utilisé ou expiré). Demandez-en un nouveau."})
    page.goto(f"{static_url}/reset-password.html?token=perime")
    page.fill("#reset-password", "nouveau-mdp")
    page.fill("#reset-password-confirm", "nouveau-mdp")
    page.click("#reset-btn")
    expect(page.locator("#reset-invalid")).to_contain_text("n'est plus valable")
    expect(page.locator("#reset-form")).to_be_hidden()


def test_too_short_password_keeps_the_form(page, static_url):
    api = FakeApi(page)
    api.set("POST", "/api/auth/reset-password", 400, {"detail": "Le mot de passe doit contenir au moins 8 caractères."})
    page.goto(f"{static_url}/reset-password.html?token=jeton")
    page.fill("#reset-password", "court")
    page.fill("#reset-password-confirm", "court")
    page.click("#reset-btn")
    expect(page.locator("#reset-error")).to_contain_text("8 caractères")
    expect(page.locator("#reset-form")).to_be_visible()
