import pytest
from jinja2 import UndefinedError
from src.templates.fallback import render_fallback_template

# test that the render_fallback_template function renders the initial outreach template
def test_render_initial_outreach() -> None:
    draft = render_fallback_template(
        template_name="initial_outreach",
        context={"name": "John", "company": "Acme"},
    )

    assert draft.subject == "Following up on your inquiry"
    assert "John" in draft.body
    assert "Acme" in draft.body
    assert draft.tone == "professional"

# test that the render_fallback_template function renders the followup 1 template
def test_render_followup_1() -> None:
    draft = render_fallback_template(
        template_name="followup_1",
        context={"name": "John", "company": "Acme"},
    )

    assert "Acme" in draft.subject
    assert "John" in draft.body
    assert "Acme" in draft.body
    assert draft.tone == "professional"

# test that the render_fallback_template function falls back to the initial outreach template if the template name is unknown
def test_unknown_template_name_falls_back_to_initial_outreach() -> None:
    draft = render_fallback_template(
        template_name="nonexistent",
        context={"name": "John", "company": "Acme"},
    )

    assert draft.subject == "Following up on your inquiry"
    assert "John" in draft.body
    assert "Acme" in draft.body

# test that the render_fallback_template function raises a UndefinedError if the context is missing a required key
def test_missing_context_key_raises_with_strict_undefined() -> None:
    with pytest.raises(UndefinedError):
        render_fallback_template(template_name="initial_outreach", context={})
