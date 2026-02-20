import pytest
from jinja2 import UndefinedError

from src.templates.fallback import render_fallback_template


def test_render_initial_outreach() -> None:
    draft = render_fallback_template(
        template_name="initial_outreach",
        context={"name": "John", "company": "Acme"},
    )

    assert draft.subject == "Following up on your inquiry"
    assert "John" in draft.body
    assert "Acme" in draft.body
    assert draft.tone == "professional"


def test_render_followup_1() -> None:
    draft = render_fallback_template(
        template_name="followup_1",
        context={"name": "John", "company": "Acme"},
    )

    assert "Acme" in draft.subject
    assert "John" in draft.body
    assert "Acme" in draft.body
    assert draft.tone == "professional"


def test_unknown_template_name_falls_back_to_initial_outreach() -> None:
    draft = render_fallback_template(
        template_name="nonexistent",
        context={"name": "John", "company": "Acme"},
    )

    assert draft.subject == "Following up on your inquiry"
    assert "John" in draft.body
    assert "Acme" in draft.body


def test_missing_context_key_raises_with_strict_undefined() -> None:
    with pytest.raises(UndefinedError):
        render_fallback_template(template_name="initial_outreach", context={})
