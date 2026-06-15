from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import TraineeProfile


@receiver(post_save, sender=User)
def create_trainee_profile(sender, instance, created, **kwargs):
    if created:
        TraineeProfile.objects.create(
            user=instance
        )
