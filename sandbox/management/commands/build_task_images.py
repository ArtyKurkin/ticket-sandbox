from pathlib import Path

from django.core.management.base import BaseCommand

from sandbox.services.docker_service import get_docker_client


class Command(BaseCommand):
    help = "Build Docker images for all training tasks"

    def handle(self, *args, **options):
        client = get_docker_client()

        tasks_dir = Path("training_tasks")

        if not tasks_dir.exists():
            self.stderr.write("training_tasks directory not found")
            return

        task_paths = sorted(
            task_path
            for task_path in tasks_dir.glob("*/*")
            if task_path.is_dir()
        )

        if not task_paths:
            self.stderr.write("training task directories not found")
            return

        for task_path in task_paths:
            dockerfile = task_path / "Dockerfile"

            queue_slug = task_path.parent.name
            task_slug = task_path.name

            if not dockerfile.exists():
                self.stdout.write(
                    self.style.WARNING(
                        f"Skip {queue_slug}/{task_slug}: Dockerfile not found"
                    )
                )
                continue

            image_name = f"ticket-sandbox-{queue_slug}-{task_slug}"

            self.stdout.write(f"Building {image_name}...")

            client.images.build(
                path=str(task_path),
                tag=image_name,
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Built {image_name}"
                )
            )
