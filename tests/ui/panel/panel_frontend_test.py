# pip install panel pytest pytest-playwright
# playwright install
# pytest panel_frontend_test.py --headed --slowmo 1000

import time

import panel as pn
import pytest
from playwright.sync_api import Page

# pytest ./tests/ui/panel/panel_frontend_test.py --headed --slowmo 1000


# required playwright installed, skip for now
@pytest.mark.skip(reason="Playwright tests do not run in CI")
def test_component(page: Page, port):
    from panel_app import App

    app = App()
    url = f"http://localhost:{port}"

    server = pn.serve(app, port=port, threaded=True, show=False)
    time.sleep(0.2)

    page.goto(url)
    time.sleep(3)  # wait for page to load

    # print(json.dumps(app.jsoneditor.get_value()))
    assert app.jsoneditor.get_value() == {"testxy": ""}

    # note: css selector for id=root[testxy] needs to escaped,
    # see https://stackoverflow.com/questions/1466103/escape-square-brackets-when-assigning-a-class-name-to-an-element # noqa
    page.locator("#root\\[testxy\\]").fill("test123")
    page.locator("[for=root\\[testxy\\]]").click()
    assert app.jsoneditor.get_value() == {"testxy": "test123"}

    # click save button (button element with text "Save")
    page.locator("button:has-text('Save')").click()

    time.sleep(0.5)  # wait for save action to complete
    # check if the span with class "je-object__title" contains "Updated Title"
    assert page.locator(".je-object__title").text_content() == "Updated Title"

    assert page.locator("#root\\[testxy\\]").input_value() == "test123"

    app.jsoneditor.set_value({"testxy": "new value"})
    time.sleep(0.5)
    # assert that the input field has the value "new value"
    assert page.locator("#root\\[testxy\\]").input_value() == "new value"

    server.stop()
