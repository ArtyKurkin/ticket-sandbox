from decimal import Decimal

from .models import StageGroup


WEEKLY_SPEED_TARGET = Decimal("6.0")
WEEKLY_QUALITY_TARGET = 80

TICKET_METRIC_GROUPS = {
    StageGroup.WITH_REVIEW,
    StageGroup.OPTIONAL_REVIEW,
    StageGroup.NO_REVIEW,
}
