from django.test import SimpleTestCase

from assessment.templatetags.russian import (
    ru_plural,
)


class RussianPluralTests(SimpleTestCase):
    def test_family_pluralization(self):
        cases = {
            1: "семейство",
            2: "семейства",
            4: "семейства",
            5: "семейств",
            11: "семейств",
            14: "семейств",
            21: "семейство",
            23: "семейства",
            27: "семейств",
        }

        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(
                    ru_plural(
                        value,
                        (
                            "семейство,"
                            "семейства,"
                            "семейств"
                        ),
                    ),
                    expected,
                )
