from copy import deepcopy
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from achievements.models import AchievementDefinition, AchievementEvent, AchievementOperation, UserAchievement
from achievements.services.grants import GrantConflict, grant, revoke
from .base import AchievementTestCase


class GrantTests(AchievementTestCase):
    def test_sequential_upgrades_and_one_family(self):
        for tier in ("bronze", "silver", "gold", "platinum"):
            self.award(tier)
        entitlement = UserAchievement.objects.get()
        self.assertEqual(entitlement.active_tier.code, "platinum")
        self.assertEqual(entitlement.revision, 4)
        self.assertEqual(list(entitlement.events.values_list("action", "from_tier__code", "to_tier__code")),
            [("grant", None, "bronze"), ("upgrade", "bronze", "silver"), ("upgrade", "silver", "gold"), ("upgrade", "gold", "platinum")])

    def test_direct_platinum_is_one_real_grant(self):
        self.award("platinum")
        self.assertEqual(list(AchievementEvent.objects.values_list("action", "from_tier__code", "to_tier__code")), [("grant", None, "platinum")])

    def test_bronze_to_platinum_does_not_invent_intermediate_levels(self):
        self.award()
        self.award("platinum")
        self.assertEqual(AchievementEvent.objects.count(), 2)
        self.assertEqual(AchievementEvent.objects.last().from_tier.code, "bronze")

    def test_same_lower_or_repeated_operations_do_not_change_history(self):
        self.award("gold")
        self.assertEqual(self.award("gold")[1], "duplicate")
        self.assertEqual(self.award("gold", operation="different")[1], "no_op")
        self.assertEqual(self.award("bronze")[1], "no_op")
        self.assertEqual(AchievementEvent.objects.count(), 1)

    def test_revoke_preserves_original_and_blocks_all_auto_regrant(self):
        entitlement, _, event = self.award("platinum")
        original = deepcopy(event.evidence)
        revoke(user_id=self.user.pk, definition_id=entitlement.definition_id, actor=self.staff,
               reason="Ошибочное доказательство", operation_id="revoke")
        entitlement.refresh_from_db()
        event.refresh_from_db()
        self.assertIsNone(entitlement.active_tier_id)
        self.assertTrue(entitlement.auto_grant_blocked)
        self.assertEqual(event.evidence, original)
        self.assertEqual(self.award("platinum", operation="new-proof")[1], "suppressed")
        self.assertEqual(self.award("platinum")[1], "suppressed")
        self.assertEqual(AchievementEvent.objects.count(), 2)

    def test_staff_regrant_is_explicit_and_does_not_release_auto_block(self):
        entitlement, _, _ = self.award()
        revoke(user_id=self.user.pk, definition_id=entitlement.definition_id, actor=self.staff, reason="Ошибка", operation_id="r")
        self.assertEqual(self.award("silver", manual=True, operation="staff-regrant")[1], "grant")
        self.assertEqual(self.award("gold", operation="new")[1], "suppressed")

    def test_repeated_noop_cannot_become_a_regrant_after_revoke(self):
        entitlement, _, _ = self.award("gold", manual=True)
        self.award("silver", manual=True, operation="old-noop")
        revoke(user_id=self.user.pk, definition_id=entitlement.definition_id, actor=self.staff, reason="Ошибка", operation_id="r")
        self.assertEqual(self.award("silver", manual=True, operation="old-noop")[1], "duplicate")
        entitlement.refresh_from_db()
        self.assertIsNone(entitlement.active_tier_id)

    def test_operation_id_conflicting_payload_rejected(self):
        self.award("silver", operation="id")
        with self.assertRaises(GrantConflict):
            self.award("gold", operation="id")

    def test_expected_revision_guards_mutation(self):
        self.award()
        with self.assertRaises(GrantConflict):
            self.award("gold", expected_revision=0)
        self.assertEqual(AchievementEvent.objects.count(), 1)

    def test_revoke_staff_reason_idempotency(self):
        entitlement, _, _ = self.award()
        kwargs = dict(user_id=self.user.pk, definition_id=entitlement.definition_id, operation_id="r")
        with self.assertRaises(PermissionDenied):
            revoke(**kwargs, actor=self.user, reason="x")
        with self.assertRaises(ValidationError):
            revoke(**kwargs, actor=self.staff, reason=" ")
        revoke(**kwargs, actor=self.staff, reason="Ошибка")
        self.assertEqual(revoke(**kwargs, actor=self.staff, reason="Ошибка")[1], "duplicate")

    def test_append_only_instance_queryset_and_explicit_pk(self):
        _, _, event = self.award()
        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            event.delete()
        with self.assertRaises(ValidationError):
            AchievementEvent.objects.filter(pk=event.pk).update(reason="changed")
        with self.assertRaises(ValidationError):
            AchievementEvent.objects.all().delete()
        with self.assertRaises(ValidationError):
            AchievementEvent.objects.bulk_update([event], ["reason"])
        with self.assertRaises(ValidationError):
            AchievementEvent.objects.bulk_create([event])
        clone = deepcopy(event)
        clone._state.adding = True
        with self.assertRaises(IntegrityError), transaction.atomic():
            clone.save()
        self.assertEqual(AchievementEvent.objects.count(), 1)

    def test_projection_and_event_roll_back_together(self):
        with patch("achievements.models.UserAchievement.save", side_effect=IntegrityError("rollback")):
            with self.assertRaises(IntegrityError):
                self.award()
        self.assertFalse(UserAchievement.objects.exists())
        self.assertFalse(AchievementEvent.objects.exists())
        self.assertFalse(AchievementOperation.objects.exists())

    def test_pending_auto_tiers_cannot_be_issued_by_grant_service(self):
        for code, tier in [("training_program", "platinum"), ("sandbox_program", "silver"), ("clean_week", "platinum")]:
            with self.subTest(code=code), self.assertRaises(ValidationError):
                self.award(tier, code=code)

    def test_catalog_requires_known_evaluator_version_and_safe_art(self):
        definition = self.definition()
        for field, value in [("evaluator_key", "__import__"), ("rule_version", 2), ("art_key", "../../secrets")]:
            with self.subTest(field=field):
                setattr(definition, field, value)
                with self.assertRaises(ValidationError):
                    definition.full_clean()
                definition.refresh_from_db()
        tier = definition.tiers.first()
        tier.parameters = {"minimum": "0", "automatic": True}
        with self.assertRaises(ValidationError):
            tier.full_clean()

    def test_catalog_has_eleven_families_quality_three_and_secret_separate(self):
        self.assertEqual(AchievementDefinition.objects.count(), 11)
        self.assertEqual(self.definition("review_quality").tiers.count(), 3)
        secret = self.definition("clean_week")
        self.assertTrue(secret.secret)
        self.assertEqual(secret.tiers.get().code, "platinum")
