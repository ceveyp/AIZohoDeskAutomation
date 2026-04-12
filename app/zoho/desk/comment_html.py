import html


def plain_text_to_zoho_html(text: str) -> str:
    """Turn plain text (possibly multi-line) into simple HTML for Desk comments."""
    lines = text.splitlines()
    if not lines:
        return "<p></p>"
    inner = "<br />".join(html.escape(line) for line in lines)
    return f"<p>{inner}</p>"
