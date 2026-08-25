from django import template

register = template.Library()


@register.filter
def ru_plural(value, forms):
    try:
        value = abs(int(value))
    except (TypeError, ValueError):
        return ""

    one, few, many = [
        item.strip()
        for item in forms.split(",")
    ]

    last_two = value % 100
    last_one = value % 10

    if 11 <= last_two <= 14:
        return many

    if last_one == 1:
        return one

    if 2 <= last_one <= 4:
        return few

    return many
