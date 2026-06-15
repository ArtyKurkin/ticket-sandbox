from django import template

register = template.Library()


@register.filter
def ru_plural(value, forms):
    """
    Склоняет слово после числа.

    Пример:
    {{ count|ru_plural:"тикет,тикета,тикетов" }}
    """

    try:
        number = abs(int(value))
    except (TypeError, ValueError):
        number = 0

    one, few, many = [form.strip() for form in forms.split(",")]

    if 11 <= number % 100 <= 14:
        return many

    last_digit = number % 10

    if last_digit == 1:
        return one

    if 2 <= last_digit <= 4:
        return few

    return many
