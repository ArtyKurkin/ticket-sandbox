"""Lab/CI only: separate PostgreSQL DB, Redis queue and Docker resource namespace."""
import os
from config.settings import *  # noqa: F403

TB2_FULLSTACK_TEST = True
TB2_CONTROL_TOKEN = os.environ['TB2_CONTROL_TOKEN']
TB2_MODE = os.environ['TB2_MODE']
TB2_PREFIX = os.environ['TB2_PREFIX']
TB2_WEB_HOST = os.environ['TB2_WEB_HOST']
SANDBOX_DOCKER_PREFIX = TB2_PREFIX + '-' + TB2_MODE
CELERY_TASK_DEFAULT_QUEUE = SANDBOX_DOCKER_PREFIX
CELERY_IMPORTS = ('experiments.terminal_broker.fullstack_tasks',)
ROOT_URLCONF = 'experiments.terminal_broker.fullstack_urls'
TERMINAL_NETWORK_MODE = TB2_MODE
