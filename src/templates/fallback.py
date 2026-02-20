from jinja2 import StrictUndefined, Template

from src.llm.prompts.draft import DraftOutput

SAFE_TEMPLATES: dict[str, dict[str, str]] = {
    "initial_outreach": {
        "subject": "Following up on your inquiry",
        "body": (
            "Hi {{ name }},\n\n"
            "Thank you for reaching out. We'd love to learn more about your needs at "
            "{{ company }}.\n\nBest regards"
        ),
    },
    "followup_1": {
        "subject": "Checking in - {{ company }}",
        "body": (
            "Hi {{ name }},\n\n"
            "I wanted to follow up on my previous message. Would you have time for a "
            "quick conversation about how we can help {{ company }}?\n\nBest regards"
        ),
    },
}

DEFAULT_TEMPLATE_NAME = "initial_outreach"


def render_fallback_template(template_name: str, context: dict) -> DraftOutput:
    """
    Render a safe fallback template.

    Uses StrictUndefined, so callers must provide required keys such as
    "name" and "company" in context.
    """

    selected_template = SAFE_TEMPLATES.get(
        template_name,
        SAFE_TEMPLATES[DEFAULT_TEMPLATE_NAME],
    )

    subject = _render_template_string(selected_template["subject"], context)
    body = _render_template_string(selected_template["body"], context)

    return DraftOutput(subject=subject, body=body, tone="professional")


def _render_template_string(template_str: str, context: dict) -> str:
    template = Template(template_str, undefined=StrictUndefined)
    return str(template.render(context))
