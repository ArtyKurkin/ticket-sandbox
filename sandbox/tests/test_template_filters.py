from django.test import SimpleTestCase

from sandbox.templatetags.ru_plural import ru_plural


class RuPluralFilterTests(SimpleTestCase):
    def test_ru_plural_for_tickets(self):
        cases = {
            0: "тикетов",
            1: "тикет",
            2: "тикета",
            3: "тикета",
            4: "тикета",
            5: "тикетов",
            11: "тикетов",
            14: "тикетов",
            21: "тикет",
            22: "тикета",
            27: "тикетов",
            101: "тикет",
            112: "тикетов",
        }

        for number, expected in cases.items():
            with self.subTest(number=number):
                self.assertEqual(
                    ru_plural(number, "тикет,тикета,тикетов"),
                    expected,
                )
