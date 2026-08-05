from django.db import models


class SupportLevel(models.TextChoices):
    L1 = "l1", "L1"
    L2 = "l2", "L2"
    PRIME = "prime", "Prime"


class QuestionDifficulty(models.TextChoices):
    MEDIUM = "medium", "Средняя"
    HARD = "hard", "Сложная"
    ADVANCED = "advanced", "Повышенная"


class QuestionType(models.TextChoices):
    SINGLE_CHOICE = (
        "single_choice",
        "Один правильный ответ",
    )
    MULTIPLE_CHOICE = (
        "multiple_choice",
        "Несколько правильных ответов",
    )


class QuestionStatus(models.TextChoices):
    DRAFT = "draft", "Черновик"
    ACTIVE = "active", "Активен"
    ARCHIVED = "archived", "Архив"
