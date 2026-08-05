from django.db import models


class SupportLevel(models.TextChoices):
    L1 = "l1", "L1"
    L2 = "l2", "L2"
    PRIME = "prime", "Prime"
