from django.core.management.base import BaseCommand
from sandbox.tasks import reconcile_broker_environments


class Command(BaseCommand):
    help = 'Requeue unfinished broker lifecycle operations; safe with active executors.'

    def handle(self, **options):
        reconcile_broker_environments()
        self.stdout.write('Unfinished terminal operations queued.')
