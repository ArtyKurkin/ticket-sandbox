from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from django.db.models import Prefetch

from traineediary.models import (
    StageHistory,
    TraineeJourney,
)
from traineediary.services.integrity import (
    check_journey_integrity,
)


class Command(BaseCommand):
    help = (
        "Проверяет согласованность карточек, "
        "истории этапов и результатов ИС."
    )

    def add_arguments(
        self,
        parser,
    ):
        parser.add_argument(
            "--journey-id",
            action="append",
            dest="journey_ids",
            type=int,
            help=(
                "Проверить только указанную "
                "карточку. Аргумент можно "
                "передать несколько раз."
            ),
        )

    def handle(
        self,
        *args,
        **options,
    ):
        journey_ids = options[
            "journey_ids"
        ]

        history_queryset = (
            StageHistory.objects
            .select_related(
                "stage",
            )
            .order_by(
                "started_at",
                "id",
            )
        )

        queryset = (
            TraineeJourney.objects
            .select_related(
                "user",
                "current_stage",
                "completed_by",
            )
            .prefetch_related(
                Prefetch(
                    "stage_history",
                    queryset=(
                        history_queryset
                    ),
                ),
            )
            .order_by(
                "id",
            )
        )

        if journey_ids:
            requested_ids = set(
                journey_ids,
            )

            existing_ids = set(
                queryset
                .filter(
                    id__in=requested_ids,
                )
                .values_list(
                    "id",
                    flat=True,
                )
            )

            missing_ids = sorted(
                requested_ids
                - existing_ids
            )

            if missing_ids:
                missing_ids_text = ", ".join(
                    str(journey_id)
                    for journey_id
                    in missing_ids
                )

                raise CommandError(
                    (
                        "Карточки не найдены: "
                        f"{missing_ids_text}."
                    ),
                )

            queryset = queryset.filter(
                id__in=requested_ids,
            )

        journeys = list(
            queryset,
        )

        issues = []

        for journey in journeys:
            issues.extend(
                check_journey_integrity(
                    journey,
                ),
            )

        if not issues:
            self.stdout.write(
                self.style.SUCCESS(
                    (
                        "Проверка пройдена: "
                        f"карточек {len(journeys)}, "
                        "проблем не найдено."
                    ),
                ),
            )

            return

        for issue in issues:
            self.stderr.write(
                self.style.ERROR(
                    str(issue),
                ),
            )

        raise CommandError(
            (
                "Проверка не пройдена: "
                f"найдено проблем {len(issues)}."
            ),
        )
