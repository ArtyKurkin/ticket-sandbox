import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Rarity(models.TextChoices):
    BRONZE = "bronze", "Бронза"
    SILVER = "silver", "Серебро"
    GOLD = "gold", "Золото"
    PLATINUM = "platinum", "Платина"


class DefinitionQuerySet(models.QuerySet):
    def update(self, **kwargs):
        if {"code", "public_id"} & kwargs.keys():
            raise ValidationError("Идентификаторы определения неизменяемы.")
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        if {"code", "public_id"} & set(fields):
            raise ValidationError("Идентификаторы определения неизменяемы.")
        return super().bulk_update(objs, fields, **kwargs)


class AchievementDefinition(models.Model):
    code = models.SlugField(unique=True, max_length=100)
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=40)
    secret = models.BooleanField(default=False)
    kind = models.CharField(max_length=10, choices=[("tiered", "Tiered"), ("fixed", "Fixed")])
    active = models.BooleanField(default=True)
    applicability = models.CharField(max_length=30, default="both", choices=[("both", "Both"), ("new_hire", "NEW_HIRE")])
    evaluator_key = models.SlugField(max_length=100)
    rule_version = models.PositiveIntegerField(default=1)
    art_key = models.SlugField(default="generic", max_length=40)
    objects = DefinitionQuerySet.as_manager()

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(kind__in=["tiered", "fixed"]), name="achievement_kind_valid"),
            models.CheckConstraint(condition=Q(applicability__in=["both", "new_hire"]), name="achievement_applicability_valid"),
            models.CheckConstraint(condition=Q(rule_version__gte=1), name="achievement_rule_positive"),
        ]

    def clean(self):
        from .services.catalog import validate_definition
        validate_definition(self)
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values("code", "public_id").first()
            if previous and (previous["code"] != self.code or previous["public_id"] != self.public_id):
                raise ValidationError("Идентификаторы определения неизменяемы.")

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class AchievementTier(models.Model):
    definition = models.ForeignKey(AchievementDefinition, on_delete=models.PROTECT, related_name="tiers")
    code = models.SlugField(max_length=30)
    rank = models.PositiveSmallIntegerField()
    rarity = models.CharField(max_length=10, choices=Rarity.choices)
    criterion = models.TextField()
    parameters = models.JSONField(default=dict)
    rule_version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["rank"]
        constraints = [
            models.UniqueConstraint(fields=["definition", "code"], name="achievement_tier_code_unique"),
            models.UniqueConstraint(fields=["definition", "rank"], name="achievement_tier_rank_unique"),
            models.CheckConstraint(condition=Q(rank__gte=1), name="achievement_tier_rank_positive"),
            models.CheckConstraint(condition=Q(rarity__in=Rarity.values), name="achievement_rarity_valid"),
            models.CheckConstraint(condition=Q(rule_version__gte=1), name="achievement_tier_rule_positive"),
        ]

    def clean(self):
        from .services.catalog import validate_tier
        validate_tier(self)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class UserAchievement(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    definition = models.ForeignKey(AchievementDefinition, on_delete=models.PROTECT)
    active_tier = models.ForeignKey(AchievementTier, on_delete=models.PROTECT, null=True, blank=True)
    first_granted_at = models.DateTimeField(null=True, blank=True)
    last_upgraded_at = models.DateTimeField(null=True, blank=True)
    last_changed_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=0)
    auto_grant_blocked = models.BooleanField(default=False)
    evidence_disputed = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "definition"], name="user_achievement_unique")]

    def clean(self):
        if self.active_tier_id and self.active_tier.definition_id != self.definition_id:
            raise ValidationError("Уровень принадлежит другому определению.")


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Журнал неизменяем.")

    def delete(self):
        raise ValidationError("Журнал неизменяем.")

    def bulk_update(self, *args, **kwargs):
        raise ValidationError("Журнал неизменяем.")

    def bulk_create(self, *args, **kwargs):
        raise ValidationError("Используйте сервис выдачи.")


class AchievementEvent(models.Model):
    class Action(models.TextChoices):
        GRANT = "grant", "Grant"
        UPGRADE = "upgrade", "Upgrade"
        REVOKE = "revoke", "Revoke"
        EVIDENCE_DISPUTED = "evidence_disputed", "Evidence disputed"

    entitlement = models.ForeignKey(UserAchievement, on_delete=models.PROTECT, related_name="events")
    action = models.CharField(max_length=30, choices=Action.choices)
    from_tier = models.ForeignKey(AchievementTier, on_delete=models.PROTECT, null=True, related_name="+")
    to_tier = models.ForeignKey(AchievementTier, on_delete=models.PROTECT, null=True, related_name="+")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name="+")
    occurred_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)
    source_type = models.CharField(max_length=40)
    source_ref = models.CharField(max_length=200)
    rule_version = models.PositiveIntegerField()
    evidence = models.JSONField(default=dict)
    evidence_digest = models.CharField(max_length=64)
    reason = models.TextField(blank=True)
    idempotency_key = models.CharField(max_length=64, unique=True)
    revoked_event = models.ForeignKey("self", on_delete=models.PROTECT, null=True, related_name="+")
    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ["recorded_at", "id"]
        indexes = [models.Index(fields=["entitlement", "id"])]
        constraints = [
            models.CheckConstraint(condition=Q(action__in=["grant", "upgrade", "revoke", "evidence_disputed"]), name="achievement_event_action_valid"),
            models.CheckConstraint(condition=(Q(action="grant", from_tier__isnull=True, to_tier__isnull=False) | Q(action="upgrade", from_tier__isnull=False, to_tier__isnull=False) | Q(action="revoke", from_tier__isnull=False, to_tier__isnull=True) | Q(action="evidence_disputed")), name="achievement_event_shape_valid"),
        ]

    def clean(self):
        definition_id = self.entitlement.definition_id
        for tier in (self.from_tier, self.to_tier):
            if tier is not None and tier.definition_id != definition_id:
                raise ValidationError("Уровни события принадлежат другому определению.")
        if self.action == "upgrade" and (self.from_tier is None or self.to_tier is None or self.to_tier.rank <= self.from_tier.rank):
            raise ValidationError("Upgrade должен повышать уровень.")
        if self.action == "revoke" and self.source_type != "manual":
            raise ValidationError("Отзыв требует явного ручного действия.")
        if self.source_type == "manual" and (not self.actor_id or not self.actor.is_staff or not self.reason.strip()):
            raise ValidationError("Ручное событие требует staff и причину.")

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Журнал неизменяем.")
        self.clean()
        kwargs["force_insert"] = True
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Журнал неизменяем.")


class SourceEventQuerySet(models.QuerySet):
    PROCESSING_FIELDS = {"status", "attempts", "error", "result", "processed_at", "available_at"}

    def update(self, **kwargs):
        if set(kwargs) - self.PROCESSING_FIELDS:
            raise ValidationError("Факт источника неизменяем.")
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        if set(fields) - self.PROCESSING_FIELDS:
            raise ValidationError("Факт источника неизменяем.")
        return super().bulk_update(objs, fields, **kwargs)

    def delete(self):
        raise ValidationError("Durable источник нельзя удалить.")


class AchievementSourceEvent(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSED = "processed", "Processed"
        ERROR = "error", "Error"

    provider = models.CharField(max_length=40)
    external_id = models.CharField(max_length=200)
    schema_version = models.PositiveIntegerField(default=1)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    context = models.JSONField(default=dict)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    available_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True)
    result = models.JSONField(default=list)
    objects = SourceEventQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if not self._state.adding:
            fields = ("provider", "external_id", "schema_version", "user_id", "context", "payload", "created_at")
            previous = type(self).objects.filter(pk=self.pk).values(*fields).get()
            if any(previous[f] != getattr(self, f) for f in fields):
                raise ValidationError("Факт источника неизменяем.")
        else:
            kwargs["force_insert"] = True
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Durable источник нельзя удалить.")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["provider", "external_id"], name="achievement_source_unique"),
            models.CheckConstraint(condition=Q(status__in=["pending", "processed", "error"]), name="achievement_source_status_valid"),
        ]
        indexes = [models.Index(fields=["status", "id"])]


class AchievementOperation(models.Model):
    """Receipt also remembers no-ops, so an old request cannot become a new grant."""
    key = models.CharField(max_length=64, unique=True)
    request_digest = models.CharField(max_length=64)
    entitlement = models.ForeignKey(UserAchievement, on_delete=models.PROTECT)
    event = models.ForeignKey(AchievementEvent, on_delete=models.PROTECT, null=True)
    outcome = models.CharField(max_length=30)
    recorded_at = models.DateTimeField(auto_now_add=True)
    objects = AppendOnlyQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Квитанция операции неизменяема.")
        kwargs["force_insert"] = True
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Квитанция операции неизменяема.")


class AchievementNotificationBoundary(models.Model):
    """Migration-time opt-in boundary; never inferred from a user's first visit."""
    started_at = models.DateTimeField()

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(id=1), name="achievement_notification_boundary_singleton")]


class AchievementNotification(models.Model):
    event = models.OneToOneField(AchievementEvent, on_delete=models.PROTECT, related_name="notification")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    read_at = models.DateTimeField(null=True, blank=True)
    claim_token = models.UUIDField(null=True, blank=True)
    claim_expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "read_at", "event"], name="achievement_notification_feed")]

    def clean(self):
        if self.event.action not in ("grant", "upgrade") or self.user_id != self.event.entitlement.user_id:
            raise ValidationError("Уведомление должно принадлежать получателю grant/upgrade.")
