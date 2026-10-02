"""Run the platform checker against a disposable task container, no platform DB."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from django.conf import settings
if not settings.configured:
    settings.configure(CHECK_TASK_TIMEOUT_SECONDS=60)
from sandbox.services.docker_service import check_task_container, get_docker_client

client = get_docker_client()
container = client.containers.run(
    'training-platform-fix-review-wordpress', detach=True,
    labels={'ticket-sandbox.queue': 'l1', 'ticket-sandbox.task': 'wordpress-500-after-move'},
)


def command(script):
    result = container.exec_run(['bash', '-c', script])
    if result.exit_code:
        raise AssertionError(result.output.decode(errors='replace'))
    return result.output.decode(errors='replace')


def check(expected, label):
    code, output = check_task_container(container.name)
    print(f'{label}: exit={code}\n{output}', flush=True)
    assert (code == 0) is expected, label
    # A checker must leave the fixture content unchanged, even on failed checks.
    content = command("mysql --default-character-set=utf8mb4 -NBe \"SELECT content FROM client_db.site_pages WHERE slug='home'\"").strip()
    assert content == 'Соединение с базой данных установлено.', content


try:
    for _ in range(120):
        if container.exec_run(['bash', '-c', 'test ! -f /start.sh && curl -s http://127.0.0.1/ >/dev/null']).exit_code == 0:
            break
        time.sleep(0.5)
    else:
        raise AssertionError(container.logs().decode())
    command('cp /var/www/html/index.php /tmp/index-original.php')
    check(False, 'initial broken state')
    command("sed -i s/OldPassword999/CorrectPass123/ /var/www/html/wp-config.php")
    check(False, 'DB-only repair')
    command("sed -i s/CorrectPass123/OldPassword999/ /var/www/html/wp-config.php")
    static_page = "<?php echo '<h1>Сайт клиента работает</h1><p>Соединение с базой данных установлено.</p>';"
    command("cat > /var/www/html/index.php <<'PHP'\n" + static_page + '\nPHP')
    check(False, 'static HTML with both causes still broken')
    command('cp /tmp/index-original.php /var/www/html/index.php')
    command('apt-get update >/tmp/check-apt.log 2>&1 && apt-get install -y php-mbstring >>/tmp/check-apt.log 2>&1')
    restart = 'service php$(ls /etc/php | head -n1)-fpm restart'
    command(restart)
    check(False, 'extension-only repair')
    command('sed -i s/OldPassword999/CorrectPass123/ /var/www/html/wp-config.php')
    command(restart)
    check(True, 'both causes repaired')
    command("cat > /var/www/html/index.php <<'PHP'\n" + static_page + '\nPHP')
    command(restart)
    check(False, 'static HTML with healthy dependencies')
    command('cp /tmp/index-original.php /var/www/html/index.php')
    # A read-only app user is a valid alternative; checker must not require UPDATE.
    command("mysql -e \"CREATE USER 'reader'@'localhost' IDENTIFIED BY 'ReaderTest123'; GRANT SELECT ON client_db.* TO 'reader'@'localhost';\"")
    command('sed -i -e s/client_user/reader/ -e s/CorrectPass123/ReaderTest123/ /var/www/html/wp-config.php')
    command(restart)
    check(True, 'alternative credentials with SELECT-only permission')
    # CLI/FPM configuration can differ: CLI-only mbstring must not pass.
    command('phpdismod -s fpm mbstring')
    command(restart)
    check(False, 'mbstring present in CLI but absent in FPM')
    command('phpenmod -s fpm mbstring')
    command(restart)
    check(True, 'FPM runtime restored')
    # The uploaded application remains free of diagnostic checker source.
    command("! grep -R -E 'extension_loaded|function_exists|runtimeProbe' /var/www /task")
    command('for file in /var/www/html/*.php /var/www/customer-site/*.php; do php -l "$file"; done')
    print('PASS: all WordPress runtime scenarios', flush=True)
finally:
    container.remove(force=True)
