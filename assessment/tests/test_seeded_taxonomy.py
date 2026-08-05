from django.test import TestCase

from assessment.models import Skill, Topic


class SeededL1TaxonomyTests(TestCase):
    def test_initial_topics_exist(self):
        self.assertEqual(
            set(
                Topic.objects.values_list(
                    "slug",
                    flat=True,
                )
            ),
            {
                "linux-vds",
                "web",
                "networks",
                "internal-regulations",
            },
        )

    def test_initial_technical_skills_exist(self):
        expected_skills = {
            "linux-vds": 10,
            "web": 8,
            "networks": 8,
            "internal-regulations": 0,
        }

        for topic_slug, expected_count in expected_skills.items():
            with self.subTest(topic=topic_slug):
                self.assertEqual(
                    Skill.objects.filter(
                        topic__slug=topic_slug,
                    ).count(),
                    expected_count,
                )

    def test_all_seeded_entities_are_active(self):
        self.assertFalse(
            Topic.objects.filter(
                is_active=False,
            ).exists()
        )

        self.assertFalse(
            Skill.objects.filter(
                is_active=False,
            ).exists()
        )

    def test_key_skills_exist(self):
        expected_slugs = {
            "df-du-open-files",
            "cpu-io-load-average",
            "php-fpm-pool-limits",
            "mtr-intermediate-loss",
            "ipv6-routing-listening",
        }

        self.assertTrue(
            expected_slugs.issubset(
                set(
                    Skill.objects.values_list(
                        "slug",
                        flat=True,
                    )
                )
            )
        )
