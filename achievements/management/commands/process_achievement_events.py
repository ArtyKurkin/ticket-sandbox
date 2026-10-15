import json
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from achievements.models import AchievementSourceEvent
from achievements.services.events import process_source_event
from achievements.services.notifications import repair_delivery


class Command(BaseCommand):
    help = "Обрабатывает durable pending/error источники (включая законченные недели)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        ids = list(AchievementSourceEvent.objects.exclude(status="processed").filter(
            Q(available_at__isnull=True) | Q(available_at__lte=timezone.now())).order_by("id").values_list("id", flat=True)[:max(0, options["limit"])])
        for event_id in ids:
            try:
                self.stdout.write(json.dumps({"source_event_id": event_id, "result": process_source_event(event_id)}, ensure_ascii=False))
            except Exception as error:
                self.stderr.write(f"{event_id}: {type(error).__name__}: {error}")
        repaired = repair_delivery(options["limit"])
        if repaired:
            self.stdout.write(json.dumps({"notification_deliveries_repaired": repaired}))
