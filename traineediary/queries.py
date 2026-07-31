from django.contrib.auth.models import User

from sandbox.models import TraineeProfile

from .models import TraineeJourney


def get_pre_adaptation_users_queryset():
    """
    Сотрудники с доступом к очереди L1,
    для которых адаптация ещё не началась.
    """
    journey_user_ids = (
        TraineeJourney.objects
        .values_list(
            "user_id",
            flat=True,
        )
    )

    return (
        User.objects
        .filter(
            trainee_profile__level=(
                TraineeProfile.Level.L1
            ),
        )
        .exclude(
            id__in=journey_user_ids,
        )
        .select_related(
            "trainee_profile",
        )
        .order_by(
            "last_name",
            "first_name",
            "username",
        )
    )
