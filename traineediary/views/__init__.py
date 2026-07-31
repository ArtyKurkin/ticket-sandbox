# Временный compatibility-слой.
#
# Пока последняя view постепенно
# переносится из legacy.py,
# urls.py продолжает обращаться
# к обработчикам через единый пакет
# traineediary.views.

from .legacy import *  # noqa: F401,F403

from .completion import complete_trainee
from .kanban import (
    kanban_board_fragment,
    move_trainee_stage,
    trainees_kanban,
)
from .trainee_detail import trainee_detail
from .trainee_management import (
    create_trainee,
    edit_trainee,
    pre_adaptation_users,
    start_adaptation,
)
from .weekly_metrics import (
    save_weekly_metric,
    weekly_metrics,
)