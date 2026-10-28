import json
import os
from pathlib import Path
import secrets

import django
django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import Client
from sandbox.models import Queue, Task, TaskAttempt, TraineeProfile


def main():
    assert settings.TB2_FULLSTACK_TEST and connection.vendor == 'postgresql'
    call_command('migrate', interactive=False, verbosity=0)
    queue, _ = Queue.objects.get_or_create(slug='l1', defaults={'name': 'L1 lab', 'required_level': 'l1'})
    task = Task.objects.create(queue=queue, slug='service-bind-localhost', title='Real task lifecycle', order=1)
    data = {'mode': settings.TB2_MODE, 'control': settings.TB2_CONTROL_TOKEN,
            'csrf': secrets.token_hex(16), 'paths': {}, 'attempts': {}}
    for role in ('owner', 'outsider'):
        user = get_user_model().objects.create_user(username='tb2-' + role)
        profile, _ = TraineeProfile.objects.get_or_create(user=user)
        profile.level = 'l1'
        profile.save(update_fields=['level'])
        attempt = TaskAttempt.objects.create(user=user, task=task)
        browser = Client()
        browser.force_login(user)
        data[role] = browser.cookies[settings.SESSION_COOKIE_NAME].value
        data['attempts'][role] = attempt.pk
    path = Path('/lab/' + settings.TB2_MODE + '.json')
    path.write_text(json.dumps(data))
    path.chmod(0o600)
    print('PostgreSQL fixtures ready', flush=True)


if __name__ == '__main__':
    main()
