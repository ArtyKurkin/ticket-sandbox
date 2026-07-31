# Временный compatibility-слой.
#
# Пока остальные view постепенно переносятся
# из legacy.py в тематические модули,
# urls.py продолжает обращаться к ним через
# единый модуль traineediary.views.

from .legacy import *  # noqa: F401,F403
from .completion import complete_trainee
