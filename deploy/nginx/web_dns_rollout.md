# Gateway: восстановление после смены IP Web

Подготовлено 05.11.2026 в `fix/gateway-web-dns` от `origin/main` (`3a9af6e`,
PR канбана уже объединён). Production не изменялся. Исходные версии по данным
оператора: Web `4ab6530`, Worker/Scheduler `d4aa79c`, Broker Lite включён.
Эта правка не требует замены этих образов, миграций или изменения флагов.

## Причина и исправление

В исходном `deploy/nginx/docker/default.conf` на `4ab6530` и `3a9af6e`:

- строка 17: `resolver 127.0.0.11 ipv6=off valid=10s;`;
- строка 20: `proxy_pass http://web:8000;` в `location /`;
- строка 60: `proxy_pass http://web:8000/terminal-auth/;` во внутреннем auth location.

Статические `proxy_pass` разрешают имя при загрузке конфигурации. Само наличие
`resolver` не включает обновление этих адресов. После замены Web старый IP
сохраняется до reload. `depends_on: condition: service_healthy` задаёт порядок
запуска Compose, но не обновляет DNS в nginx. Healthcheck также не делает reload.
Terminal peer уже использует динамический `http://$terminal_upstream`; его менять
не нужно, но авторизация новых подключений тоже зависит от Web.

Добавлен `set $web_upstream web:8000;`, оба обращения к Web используют переменную.
Тогда nginx обращается к существующему Docker resolver и кеширует ответ на 10 с.
В `location /` адрес указан **без URI и завершающего слеша**: путь, percent encoding
и query string сохраняются. В auth location URI явно остаётся `/terminal-auth/`,
без подстановки внешнего `$request_uri`; внешний URI передаётся прежним заголовком
`X-Original-URI`.

Явный `proxy_redirect http://web:8000/ /;` сохраняет прежнее неявное правило
`proxy_redirect default` для ответов Web с внутренним абсолютным Location/Refresh.
При переменной в `proxy_pass` это правило больше не создаётся автоматически.
Все прежние заголовки, terminal routing, auth restrictions, Upgrade/Connection,
HTTP/1.1, таймауты 3600 с, buffering и лимит тела сохранены.

Compose задаёт `nginx:1.28-alpine`; в локальном тесте это nginx **1.28.3**.
Переменный `proxy_pass` совместим с этой версией. Альтернатива — shared upstream
`zone` + `server web:8000 resolve`, доступный в OSS с 1.27.3; здесь он не нужен.
Фактическую версию production необходимо проверить перед внедрением.
Основание: [proxy_pass и URI](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass),
[proxy_redirect](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_redirect),
[resolver и valid](https://nginx.org/en/docs/http/ngx_http_core_module.html#resolver),
[upstream resolve](https://nginx.org/en/docs/http/ngx_http_upstream_module.html#resolve).

Это восстановление после смены адреса, не гарантия нулевого простоя: пока Web
недоступен или кеш содержит прежний IP, возможны 502. После появления нового
готового Web ожидается обновление при следующих запросах после истечения кеша.
При ошибках DNS/сети время может быть больше 10 с; healthcheck имеет собственные
interval/retries. Он проверяет Web через Gateway, а не просто живой процесс nginx.

## Автоматизированная проверка

На отдельном Docker daemon или локально с разрешением на временные lab-контейнеры:

```sh
python3 -m venv /tmp/gateway-dns-venv
/tmp/gateway-dns-venv/bin/pip install PyYAML==6.0.2
RUN_GATEWAY_DNS_TESTS=1 /tmp/gateway-dns-venv/bin/python -m unittest discover \
  -s deploy/tests -p test_gateway_dns.py -v
```

Нужны Docker Compose, образы `nginx:1.28-alpine` и `python:3.13-alpine`
(Compose может скачать отсутствующие). Можно задать `GATEWAY_TEST_WEB_IMAGE`
на имеющийся образ с Python; локальный прогон использовал `training-platform-web:latest`.
Без `RUN_GATEWAY_DNS_TESTS=1` тест явно пропускается.

Тест создаёт уникальный проект `gateway-dns-<random>` и отдельную bridge-сеть,
копирует конфиг в временный каталог. Из основного Compose берёт только образ
Gateway и его **настоящий healthcheck**. Нет production env, socket mounts,
app volumes, Django startup, PostgreSQL, Redis, Worker или Scheduler.
Два маленьких HTTP/WS peer моделируют Web/auth и terminal backend.

Проверяются `nginx -t`, HTTP 200 с X-Forwarded-Proto=https, redirect без него,
URI/query/body, Host и forwarded headers, upstream redirect, auth subrequest,
запрет публичных auth endpoints, отказ без cookie, terminal HTTP и настоящий
WebSocket handshake + masked-frame echo. IP Web принудительно меняется с .10
на .11 через `compose up -d --no-deps --force-recreate web`.
После смены повторяются маршруты, проверяются старый и новый WebSocket,
`healthy` и неизменность ID/StartedAt/RestartCount Gateway, terminal peer и PID
master/workers nginx. Существовавшие до теста контейнеры только инспектируются;
их ID/image/StartedAt/RestartCount сравниваются после уборки ресурсов теста.

Job `gateway-dns` в существующем `terminal-broker.yml` запускает этот тест
на GitHub-hosted runner при соответствующем PR. Деплой, SSH и секреты не добавлены.
Этот транспортный тест не заменяет полноценный Broker/ttyd browser E2E.
Для Django отдельно проверяются healthz, terminal auth, gateway и Broker Lite:

```sh
DEBUG=True SECRET_KEY=gateway-dns-local-tests \
DB_ENGINE=django.db.backends.sqlite3 DB_NAME=:memory: \
  .venv/bin/python manage.py test sandbox.tests.test_healthcheck \
  sandbox.tests.test_terminal_auth sandbox.tests.test_terminal_gateway \
  sandbox.tests.test_terminal_broker sandbox.tests.test_terminal_lite --noinput
```

Локальные результаты на 05.11.2026:

- nginx 1.28.3: `nginx -t` PASS, весь Docker-тест PASS за 18,5 с;
- Web `172.23.0.10 → 172.23.0.11`: HTTP восстановился за **8,7 с** от начала
  Compose-recreate, Gateway healthy, PID nginx прежние, старый/новый WS echo PASS;
- все 8 ранее запущенных локальных контейнеров сохранили ID/image/StartedAt/RestartCount;
- отрицательный контроль: этот же тест с исходным конфигом `origin/main` проходит
  начальные routing/auth/WS проверки, но **не восстанавливает HTTP за 45 с** после
  смены IP; ожидаемый FAIL на DNS recovery, ресурсы теста удалены;
- **64 Django-теста PASS**, **24 теста CI policy PASS**, workflow policy PASS.

Production не опрашивался; hosted CI в этот локальный результат не входит.

## Исправление CI после a4b3e8f

В [запуске PR #7](https://github.com/ArtyKurkin/ticket-sandbox/actions/runs/42001309260)
`broker` упал на `Install browser test dependencies`, `fullstack` — на
`Install Chromium`, до браузерных проверок. GitHub API подтвердил шаги;
полные фрагменты ошибок предоставил оператор (скачивание логов API требует
авторизации). В обоих случаях npm успешно установил Playwright 1.56.1,
а `playwright install --with-deps chromium` сообщил:

```text
Cannot install dependencies for ubuntu26.04-x64 with Playwright 1.56.1!
ERROR: Playwright does not support chromium on ubuntu26.04-x64
```

Причина — переход `ubuntu-latest` на Ubuntu 26.04, несовместимую с закреплённым
Playwright. Те же шаги уже падали [03.11 на 9d32300](https://github.com/ArtyKurkin/ticket-sandbox/actions/runs/41623480646),
до DNS-правки; текст старых логов не получен. Установка браузера и runner label
в `a4b3e8f` не менялись. Только два браузерных job закреплены на `ubuntu-24.04`.
CI policy разрешает этот GitHub-hosted образ; запреты remote hosts, secrets
и deployment сохраняются и проверяются тестами.

Отдельно выявлена связанная с DNS-правкой регрессия **тестового** генератора
`fullstack_start.py`: замена только `http://web:8000` не переписывала значение
`set $web_upstream web:8000`. Fullstack Web имеет отдельное имя для каждого режима,
алиаса `web` в его сети нет. Генератор теперь заменяет адрес `web:8000` и в
переменной, и в literal URLs. Основной production nginx-конфиг не меняется.
Второй Docker-тест использует настоящий генератор и Web с именем fullstack,
проверяет HTTP/auth/redirect/WebSocket и смену IP без nginx reload.
Ожидание после recreate учитывает отдельные DNS-кеши workers: успешный health
в одном worker ещё не означает обновления auth-кеша в другом.

Проверки исправления: **46 Broker/PTY**, **64 Django**, **26 CI policy** — PASS.
Оба изолированных Docker-сценария — PASS (38,5 с суммарно): fullstack hostname
восстановил HTTP за 8,6 с, основной конфиг — за 9,0 с. В обоих `nginx -t`,
HTTP/auth/redirect, старый/новый WebSocket, `healthy` и неизменность PID nginx
прошли; 8 существовавших контейнеров не изменились.
Отрицательный контроль со старым генератором не получил даже начальный HTTP 200
при том же отдельном hostname; ожидаемый FAIL воспроизведён в disposable lab.

## Безопасное внедрение — только после отдельного разрешения

1. Рассмотреть diff и результаты CI, выполнить lab-тест выше. Не делать общий
   rollout приложения: Web остаётся на `4ab6530`, Worker/Scheduler — на `d4aa79c`.
   Не запускать `compose down`, общий `up`, build, pull, migrate или второй Beat.
2. Read-only preflight: проверить nginx, source bind mount, текущие образы,
   Broker Lite у трёх процессов и ровно один действующий Scheduler. Использовать
   фактические Compose project/files/profiles/runtime overrides текущего запуска;
   не подменять их двумя базовыми файлами. Не печатать полный env с секретами.
3. Сохранить текущий файл **из контейнера** и идентичности сервисов. Получить
   candidate только из рассмотренного коммита/артефакта этой ветки. Сравнить с
   текущим конфигом: допустим только рассматриваемый diff, неожиданные отличия
   требуют разбора. Проверить candidate отдельным disposable `nginx -t`
   на том же immutable image ID. Пример подготовки в Bash на целевом хосте:

```bash
set -euo pipefail
gateway=training-platform-gateway
rollout_dir=$(mktemp -d /tmp/gateway-dns-rollout.XXXXXX)
chmod 700 "$rollout_dir"
gateway_image=$(docker inspect --format '{{.Image}}' "$gateway")
gateway_config=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/etc/nginx/conf.d/default.conf"}}{{.Source}}{{end}}{{end}}' "$gateway")
test -n "$gateway_config"
test -f "$gateway_config"
docker exec "$gateway" nginx -v
docker exec "$gateway" cat /etc/nginx/conf.d/default.conf > "$rollout_dir/before.conf"
cmp "$gateway_config" "$rollout_dir/before.conf"

snapshot() {
  docker ps -aq --filter label=com.docker.compose.project=training-platform |
  while IFS= read -r container_id; do
    docker inspect --format '{{index .Config.Labels "com.docker.compose.service"}} {{.Id}} {{.Image}} {{.State.StartedAt}} {{.RestartCount}}' "$container_id"
  done | sort
}
# Если project label другой, исправить фильтр и проверить полноту списка.
snapshot > "$rollout_dir/identities.before"
cat "$rollout_dir/identities.before"
# Записать рассмотренный candidate в $rollout_dir/candidate.conf.
# Не извлекать весь новый main в production checkout.
test -s "$rollout_dir/candidate.conf"
diff -u "$rollout_dir/before.conf" "$rollout_dir/candidate.conf" || test "$?" = 1
docker run --rm --network none --entrypoint nginx \
  -v "$rollout_dir/candidate.conf:/etc/nginx/conf.d/default.conf:ro" \
  "$gateway_image" -t
```

4. После разрешения применить только nginx-конфиг и выполнить **один graceful
   reload** для первого включения исправления. Это не restart контейнера.
   Для file bind mount запись делается в существующий inode: `mv`, `sed -i`
   и git checkout могут заменить inode, оставив контейнер на старом файле.
   Проверка `cmp` ниже обязательна; если содержимое не совпало — не reload,
   восстановить host-файл и отдельно разобраться с mount.

```bash
if ! cat "$rollout_dir/candidate.conf" > "$gateway_config"; then
  cat "$rollout_dir/before.conf" > "$gateway_config"
  exit 1
fi
if ! docker exec "$gateway" cat /etc/nginx/conf.d/default.conf | cmp - "$rollout_dir/candidate.conf" ||
   ! docker exec "$gateway" nginx -t; then
  cat "$rollout_dir/before.conf" > "$gateway_config"
  exit 1
fi
docker exec "$gateway" nginx -s reload
```

Если проверка до reload не прошла, сразу восстановить `before.conf` записью
в существующий файл. Не оставлять невалидный конфиг для будущего рестарта.
Сохранить candidate в управляемом production source отдельным рассмотренным
изменением, чтобы следующий deployment не вернул старый конфиг.

5. Проверить HTTP и реальные существующие/новые терминальные сессии (DevTools:
   101 на `/terminal/<attempt>/…`, ввод/вывод команд). Использовать разрешённую
   тестовую попытку; не менять production-данные ради проверки этой правки.
6. Пересоздание Web с принудительной сменой IP уже проверяется в lab. На
   production наблюдать следующий **отдельно разрешённый** rollout только Web
   с точным текущим Compose-набором и закреплённым образом. Не пересоздавать Web
   ради этой задачи. Если Docker назначил тот же IP, это не проверка DNS recovery.

## Проверки после внедрения

```bash
docker exec "$gateway" nginx -t
# На внутреннем HTTP-порту обязательно передать HTTPS scheme и разрешённый Host.
curl --fail --silent --show-error -D - \
  -H 'Host: YOUR_PRODUCTION_HOST' -H 'X-Forwarded-Proto: https' \
  http://127.0.0.1:8080/healthz/
docker inspect --format '{{.State.Health.Status}}' "$gateway"
docker inspect --format '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' training-platform-web
docker logs --since 5m "$gateway" 2>&1 | tail -n 80
snapshot > "$rollout_dir/identities.after"
diff -u "$rollout_dir/identities.before" "$rollout_dir/identities.after"
```

Ожидаются 200 и `{"status":"ok","service":"ticket-sandbox"}`, затем `healthy`.
Проверить `/terminal-auth/`, `/terminal-broker-auth/`, `/_terminal_auth`: извне 404.
После первого reload все контейнеры, включая Web, должны иметь прежние
ID/image/StartedAt/RestartCount. При будущем отдельно разрешённом пересоздании
Web меняться может только строка Web; PostgreSQL, Redis, Worker, Scheduler и
Gateway остаются прежними. После смены IP без дополнительных reload HTTP должен
восстановиться, новые терминальные подключения авторизоваться, health вернуться
в `healthy`. Заложить время готовности Web, истечения DNS-кеша и health interval.

## Откат

Вернуть сохранённый конфиг в тот же inode, проверить видимый контейнеру файл
и выполнить graceful reload. Образы, env, Broker-флаги и БД не меняются:

```bash
cat "$rollout_dir/before.conf" > "$gateway_config"
docker exec "$gateway" cat /etc/nginx/conf.d/default.conf | cmp - "$rollout_dir/before.conf"
docker exec "$gateway" nginx -t
docker exec "$gateway" nginx -s reload
```

Повторить health/terminal/identity проверки. Откат возвращает исходное ограничение:
при последующих сменах IP Web снова понадобится ручной nginx reload.
