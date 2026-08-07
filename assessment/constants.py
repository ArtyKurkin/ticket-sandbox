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
    MATCHING = (
        "matching",
        "Сопоставление",
    )
    ORDERING = (
        "ordering",
        "Последовательность",
    )
    LINE_SELECTION = (
        "line_selection",
        "Выбор строк",
    )


class QuestionStatus(models.TextChoices):
    DRAFT = "draft", "Черновик"
    ACTIVE = "active", "Активен"
    ARCHIVED = "archived", "Архив"


class ExamAttemptStatus(models.TextChoices):
    IN_PROGRESS = "in_progress", "В процессе"
    COMPLETED = "completed", "Завершена"
    INVALIDATED = "invalidated", "Аннулирована"
