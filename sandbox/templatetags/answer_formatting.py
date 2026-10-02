from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.text import normalize_newlines


register = template.Library()


@register.filter
def render_client_answer(value):
    """Render only paired [code] tags; escape every part of the user's text."""
    text = normalize_newlines(str(value or ""))
    parts = []
    position = 0
    while True:
        opening = text.find("[code]", position)
        if opening == -1:
            break
        closing = text.find("[/code]", opening + len("[code]"))
        if closing == -1:
            break  # Keep an unclosed tag and the remaining text literal.
        parts.append(escape(text[position:opening]).replace("\n", "<br>"))
        content = escape(text[opening + len("[code]"):closing])
        parts.append(f'<pre class="client-answer-code"><code>{content}</code></pre>')
        position = closing + len("[/code]")
    parts.append(escape(text[position:]).replace("\n", "<br>"))
    # Only our markup and explicitly escaped text reach this point, even if
    # another caller supplied a SafeString. Never trust the input's safe flag.
    return mark_safe("".join(parts))
