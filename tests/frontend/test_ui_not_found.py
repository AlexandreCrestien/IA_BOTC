"""Page 404 du jeu : texte et retour au village."""
from playwright.sync_api import expect


def test_not_found_page_leads_back_to_the_village(page, static_url):
    page.goto(f"{static_url}/not-found.html")
    expect(page.locator("h1")).to_have_text("Ce chemin ne mène nulle part")
    page.click("#not-found-home")
    expect(page.locator("#screen-welcome")).to_be_visible()
