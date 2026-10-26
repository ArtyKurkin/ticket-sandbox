# Trusted Checker MVP — Real Docker Adapter Pilot

22 октября 2026 · HEAD `4692e09f9cd867a40f3cfeb29355b9d08f2bafde`.

**RUNNER PREPARED. REAL ADAPTER PILOT NOT EXECUTED.**
[real_lab.py](experiments/trusted_checker_mvp/docker_pilot/real_lab.py) использует
неизменённый `DockerPilot.observe()`. Выполнены только local offline tests:
**9 новых + 25 прежних = 34 tests, OK**. Ни SSH, ни Docker daemon не вызывались.
Предыдущий VDS smoke — сообщённое пользователем evidence; он не заменяет запуск
этого adapter. Ни `PASSED`, ни academic/physical acceptance не присваиваются.

## 1. Runner и prerequisites

Три команды: `audit` (read-only Docker metadata), `pin` (те же проверки + новый
private execution file), `observe` (явно разрешённые verifier effects).
Конфигурация только из host-owned файла mode 0600 в private directory 0700 с
доверенными ancestors. Нет `from_env`, SSH, Django imports или result-upload API.
Docker endpoint — только указанный local Unix socket, API 1.45, timeout 1s.

`pin` закрепляет actual full target/network/image/daemon IDs, Start/PID/restart,
endpoint/IP и synthetic environment/run UUID. Attempt/user/ordinal **1/1/1 —
только disposable lab**, никогда не Django records. Existing record не перезаписывается.
Каждый новый case получает новый record/run, тот же run использует тот же artifact
claim. Общий private artifact directory нельзя чистить ради retry.

Перед observe runner повторяет **существующие** `_target`/`_network` predicates
на current metadata и требует quiescent scope: только свой target, без оставшихся
verifier/diagnostic containers. Затем original adapter получает **старый pinned
record**. Restart не становится новым baseline. `--allow-verifier-effects <scope>`
обязателен до APIClient creation и разрешает только owned verifier create/start/remove.
Runner не создаёт/не удаляет сеть или target и не выполняет container exec.

Печатаются `http`, `reason`, `binding`, `task_verdict`, `academic_pass=false`,
`real_pilot_passed=false` и metadata inventory audit. Exit 0 — завершённый matched
или mismatch с чистым inventory; exit 2 — unknown/refusal либо inventory discrepancy.
Это **не shell exit code академического зачёта**. При inventory discrepancy
исторический adapter HTTP result сохраняется, но общий runner exit — 2.

Реальные prerequisites, которые runner проверит на VDS:

| Boundary | Требование |
|---|---|
| Daemon/API | Exact configured daemon ID; доступ local API 1.45; измеренные Version/ApiVersion в audit |
| Target | Full ID, approved image ID, task labels, cap-drop ALL, NNP, без host PID/IPC/net modes и mounts/devices/ports; original adapter predicate |
| Network | `tc-mvp-<scope UUID>`, labels scope/data, internal bridge, IPv6/attachable OFF, exact isolated option и один approved RFC1918 subnet ≤64 addresses |
| Verifier image | Pinned local image ID; audit сообщает availability/volume-loader-env compatibility; original adapter повторно проверяет image и launch profile |
| Records/artifacts | Один operator UID, private directory, bounded exact schema; original adapter O_EXCL run claim |
| Ownership | В scope только target до/после; foreign container ID/state inventory сравнивается, чужие ресурсы не удаляются |

`tc-mvp-lab` без UUID/labels не подходит. Старый smoke target не adopt-ится.
Ниже создаются новые resources. Verifier source/build должны быть одобрены отдельно:
совпадение image ID не доказывает наличие правильных `/checker/worker.py` и probe.

## 2. Перенос вручную

Все команды ниже предназначены **оператору**, Codex их не выполнял. На local machine
из repository root подготовить только Python sources, без Django/.env/credentials:

```sh
tar -czf /tmp/tc-mvp-real-lab-src.tgz \
  experiments/trusted_checker_mvp/docker_pilot/adapter.py \
  experiments/trusted_checker_mvp/docker_pilot/worker.py \
  experiments/trusted_checker_mvp/docker_pilot/real_lab.py \
  experiments/trusted_checker_mvp/verifier.py
shasum -a 256 /tmp/tc-mvp-real-lab-src.tgz
read -r TC_VDS_USER  # approved SSH login, not a trainee account
scp -o StrictHostKeyChecking=yes /tmp/tc-mvp-real-lab-src.tgz \
  "${TC_VDS_USER}@${TC_VDS_HOST}:tc-mvp-real-lab-src.tgz"
ssh -o StrictHostKeyChecking=yes "${TC_VDS_USER}@${TC_VDS_HOST}"
```

На VDS — один доверенный operator UID с разрешённым Docker access. Не менять
daemon configuration ради доступа. Сверить archive SHA-256 с local значением.
Следующие блоки выполняются в **одной Bash session**:

```bash
set -euo pipefail
umask 077
sha256sum "$HOME/tc-mvp-real-lab-src.tgz"
TC_SCOPE=$(python3 -c 'import uuid; print(uuid.uuid4())')
TC_ENV=$(python3 -c 'import uuid; print(uuid.uuid4())')
TC_LAB="$HOME/tc-mvp-real-adapter-$TC_SCOPE"
mkdir -m 700 "$TC_LAB"
cd "$TC_LAB"
tar -xzf "$HOME/tc-mvp-real-lab-src.tgz"
python3 -m venv .venv
# Only if package download is approved; alternatively use reviewed local wheels.
.venv/bin/python -m pip install 'docker==7.1.0'
TC_PY="$TC_LAB/.venv/bin/python"
TC_MODULE=experiments.trusted_checker_mvp.docker_pilot.real_lab
mkdir -m 700 "$TC_LAB/artifacts"
TC_SOCKET=/var/run/docker.sock
dc() { docker --host "unix://$TC_SOCKET" "$@"; }
TC_DAEMON=$(dc info --format '{{.ID}}')
TC_TARGET_IMAGE=sha256:d1c3e8c95745dc5984c7498a2a09a1f037c61ef4e7378e3fd058ba3e2209073c
TC_VERIFIER_IMAGE=sha256:7def98b4594a65b064953579f79370ef30b0c9b6225d71b3432df7be95e1a683
dc version
test "$(dc image inspect -f '{{.Id}}' "$TC_TARGET_IMAGE")" = "$TC_TARGET_IMAGE"
test "$(dc image inspect -f '{{.Id}}' "$TC_VERIFIER_IMAGE")" = "$TC_VERIFIER_IMAGE"
dc image inspect -f '{{json .Config.Volumes}} {{json .Config.Env}}' "$TC_VERIFIER_IMAGE"
dc container ls -a --no-trunc > "$TC_LAB/containers-before.txt"
dc network ls --no-trunc > "$TC_LAB/networks-before.txt"
dc network inspect $(dc network ls -q) > "$TC_LAB/networks-before.json"
ip -4 route show table all  # read only; review overlap, including host routes
read -r -p 'Approved unused RFC1918 /28 subnet: ' TC_SUBNET
"$TC_PY" - "$TC_SUBNET" <<'PY'
import ipaddress, sys
n = ipaddress.IPv4Network(sys.argv[1])
assert n.prefixlen == 28 and any(n.subnet_of(ipaddress.IPv4Network(x))
    for x in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
PY
printf 'NEW scope=%s env=%s daemon=%s subnet=%s\n' "$TC_SCOPE" "$TC_ENV" "$TC_DAEMON" "$TC_SUBNET"
printf 'Images: %s %s\n' "$TC_TARGET_IMAGE" "$TC_VERIFIER_IMAGE"
read -r -p 'Authorize NEW disposable network/target; type scope UUID: ' TC_PERMISSION
test "$TC_PERMISSION" = "$TC_SCOPE"
test "$(dc info --format '{{.ID}}')" = "$TC_DAEMON"
```

Остановиться при overlap, отсутствующем image, неверном daemon/API или неясном
scope. Не использовать существующие lab resources в качестве fallback.
Создание Docker network само имеет обычные host networking effects; это именно
показанная отдельно разрешаемая операция. Команд изменения host firewall/routes/
sysctl или existing namespaces здесь нет.

## 3. Новая сеть, target и config

```bash
TC_NETWORK=$(dc network create --driver bridge --internal --ipv6=false \
  --subnet "$TC_SUBNET" \
  --opt com.docker.network.bridge.gateway_mode_ipv4=isolated \
  --label "tc-mvp.scope=$TC_SCOPE" --label tc-mvp.role=data "tc-mvp-$TC_SCOPE")
printf '%s\n' "$TC_NETWORK" > "$TC_LAB/network.id"
TC_TARGET=$(dc run -d --pull=never --cidfile "$TC_LAB/target.id" \
  --name "tc-mvp-target-$TC_SCOPE" --network "$TC_NETWORK" \
  --user 0:0 --cap-drop ALL --security-opt no-new-privileges --ipc private \
  --memory 128m --pids-limit 64 --cpus 0.25 --restart=no --log-driver none \
  --label "tc-mvp.scope=$TC_SCOPE" --label tc-mvp.role=target \
  --label "tc-mvp.environment=$TC_ENV" --label ticket-sandbox.attempt=1 \
  --label ticket-sandbox.queue=l1 --label ticket-sandbox.task=service-bind-localhost \
  --entrypoint /bin/bash "$TC_TARGET_IMAGE" -c \
  'rm -f /run/customer-app/customer-app.pid; /usr/local/bin/customer-app start; exec tail -f /dev/null')
"$TC_PY" - "$TC_LAB/config.json" "$TC_SOCKET" "$TC_LAB/artifacts" "$TC_ENV" \
  "$TC_TARGET" "$TC_DAEMON" "$TC_NETWORK" "$TC_SCOPE" "$TC_SUBNET" \
  "$TC_TARGET_IMAGE" "$TC_VERIFIER_IMAGE" <<'PY'
import json, sys
p, sock, artifacts, env, target, daemon, net, scope, subnet, ti, vi = sys.argv[1:]
with open(p, 'x') as f:
    json.dump(dict(api_socket=sock, artifact_dir=artifacts, environment_uuid=env,
        target_id=target, policy=dict(daemon_id=daemon, network_id=net, scope=scope,
        subnet=subnet, target_image=ti, verifier_image=vi)), f)
PY
"$TC_PY" -m "$TC_MODULE" audit --config "$TC_LAB/config.json" | tee "$TC_LAB/audit.json"
```

Repeatable lab command намеренно не использует `/start.sh`: repository startup
удаляет себя и непригоден для restart scenario. Это только операторская fixture,
не код checker. Mounts/socket/volumes/tmpfs/published ports не добавляются. Cap-drop
ALL compatibility и фактическое содержимое предоставленного target image пока
**не проверены**. Если startup/app paths несовместимы — stop, без ослабления profile.
При create/start failure сохранить `network.id`/`target.id`; не повторять provisioning
вслепую, сначала scoped diagnosis.

## 4. Шесть наблюдений и cleanup accounting

В той же session определить фиксированные helpers. `fixture_case` исполняется
**только вручную оператором внутри своего target** и имитирует действия root trainee;
runner/verifier его не вызывают. Это не independent observation source.

```bash
fixture_case() {
  dc exec -i "$TC_TARGET" /usr/bin/python3 - "$1" <<'PY'
from pathlib import Path
import subprocess, sys
mode = sys.argv[1]
assert mode in ('good', 'spoof', 'body')
Path('/opt/customer-app/app.conf').write_text(
    'BIND_ADDRESS=' + ('127.0.0.1' if mode == 'spoof' else '0.0.0.0') + '\nPORT=8080\n')
Path('/task/check.sh').write_text('#!/bin/sh\nexit 0\n')
p = Path('/opt/customer-app/app_server.py')
s = p.read_text()
assert 'APP OK: customer service is running' in s or 'APP WRONG: disposable fixture' in s
s = s.replace('APP WRONG: disposable fixture', 'APP OK: customer service is running')
if mode == 'body':
    s = s.replace('APP OK: customer service is running', 'APP WRONG: disposable fixture')
p.write_text(s)
subprocess.run(['/usr/local/bin/customer-app', 'restart'], check=True, timeout=5)
PY
}
pin_case() {
  "$TC_PY" -m "$TC_MODULE" pin --config "$TC_LAB/config.json" \
    --record "$TC_LAB/$1.execution.json" > "$TC_LAB/$1.pin.json"
}
observe_case() {
  local name="$1" code=0
  "$TC_PY" -m "$TC_MODULE" observe --config "$TC_LAB/config.json" \
    --record "$TC_LAB/$name.execution.json" --allow-verifier-effects "$TC_SCOPE" \
    > "$TC_LAB/$name.result.json" || code=$?
  cat "$TC_LAB/$name.result.json"
  test "$code" -eq 0 || test "$code" -eq 2
}
fixture_case good
pin_case matched
observe_case matched
# Replay uses the SAME execution file and SAME artifact directory, no re-pin.
cp "$TC_LAB/matched.result.json" "$TC_LAB/first-match.result.json"
observe_case matched
cp "$TC_LAB/matched.result.json" "$TC_LAB/replay.result.json"
fixture_case spoof
dc exec "$TC_TARGET" /bin/bash /task/check.sh  # operator demonstration only: exit 0
pin_case spoof
observe_case spoof
fixture_case body
pin_case body
observe_case body
fixture_case good
pin_case stale
dc restart --time 2 "$TC_TARGET"
observe_case stale  # NEVER re-pin stale.execution.json after restart
```

Verifier-unavailable: не удалять shared image/tag, нужный старому smoke. Вместо
этого оператор задаёт отдельную policy с заведомо отсутствующим local image ID:

```bash
"$TC_PY" - "$TC_LAB/config.json" "$TC_LAB/missing-image.json" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
c['policy']['verifier_image'] = 'sha256:' + '0' * 64
with open(sys.argv[2], 'x') as f: json.dump(c, f)
PY
"$TC_PY" -m "$TC_MODULE" pin --config "$TC_LAB/missing-image.json" \
  --record "$TC_LAB/unavailable.execution.json" | tee "$TC_LAB/unavailable.pin.json"
"$TC_PY" - "$TC_LAB/unavailable.pin.json" <<'PY'
import json, sys
assert json.load(open(sys.argv[1]))['verifier_image_available'] is False
PY
# If this ID exists, the assertion stops this fault case before effects.
TC_CODE=0
"$TC_PY" -m "$TC_MODULE" observe --config "$TC_LAB/missing-image.json" \
  --record "$TC_LAB/unavailable.execution.json" --allow-verifier-effects "$TC_SCOPE" \
  > "$TC_LAB/unavailable.result.json" || TC_CODE=$?
test "$TC_CODE" -eq 2
cat "$TC_LAB/unavailable.result.json"
"$TC_PY" -m "$TC_MODULE" audit --config "$TC_LAB/config.json" > "$TC_LAB/audit-after.json"
```

| Case | Требуемый исход |
|---|---|
| first-match | matched/http_match, non-null binding, task_verdict unknown |
| replay | unknown/replay, binding null, без нового verifier dispatch |
| spoof | unknown/endpoint_unavailable (допустим timeout при сетевом silent drop), никогда matched |
| body | mismatch/http_mismatch, task_verdict failed; academic flag всё равно false |
| stale | unknown/runtime_changed, binding null; новый runtime не adopt-ится |
| unavailable | unknown/worker_unavailable либо image_unavailable; binding null |
| Каждый observe | remaining_scope_verifier_ids=[], scope_empty_except_target=true, foreign_inventory_unchanged=true |

Для reset с удалённым/replaced full ID runner откажет до effects (`unknown`), не
найдёт replacement по имени. Проверять runtime-change case надо новым ещё не
consumed record: старый уже consumed run закономерно даст replay раньше runtime fence.
`pin` сам по себе не запускает HTTP. Любое отличие от таблицы требует stop/review;
exit 2 не следует автоматически считать ожидаемым отказом без чтения reason/binding.
Inventory — bounded-in-time Docker ID/state observation, не continuous process proof.
Чужие verifiers могут существовать вне scope: требуется их **неизменность**, а не
остановка всех checker containers на VDS.

## 5. Проверки безопасности вручную

Host-side target safety predicates и actual worker launch/exit profile проверяются
неизменённым adapter; сохранить result/artifact и `audit*.json`. Дополнительно:

```bash
dc inspect -f '{{json .Mounts}} {{json .HostConfig.Binds}} {{json .HostConfig.CapDrop}} {{json .HostConfig.SecurityOpt}} {{.HostConfig.Privileged}} {{.HostConfig.PidMode}} {{.HostConfig.NetworkMode}}' "$TC_TARGET"
dc exec "$TC_TARGET" /usr/bin/python3 -c 'from pathlib import Path; print("docker_socket_present", Path("/var/run/docker.sock").exists()); print("\n".join(x for x in Path("/proc/self/status").read_text().splitlines() if x.startswith(("CapEff:","NoNewPrivs:"))))'
dc container ls -a --no-trunc --filter "label=tc-mvp.scope=$TC_SCOPE"
dc network inspect "$TC_NETWORK"
```

Ожидания: mounts/binds пусты, privileged false, CapDrop ALL, NNP, private PID/net,
socket отсутствует, CapEff=0, NoNewPrivs=1. Target-side Python/status — diagnostic
fixture readback, не attestation от hostile root. Это не тест всех kernel escapes
или доказательство невозможности privilege escalation вообще.

Для **control-plane reachability** нужны operator-approved numeric endpoints
данной lab и positive host baseline: существующий test control listener должен
быть доступен с host, но недоступен из task netns. Если listener отсутствует или
endpoint не разрешён для проверки — свойство остаётся unverified. Не сканировать
старую lab, production/DB/terminal адреса без отдельного scope. Пример для **одного**
одобренного существующего lab control endpoint:

```bash
read -r -p 'Approved lab control IPv4: ' TC_CONTROL_IP
read -r -p 'Approved lab control TCP port: ' TC_CONTROL_PORT
"$TC_PY" - "$TC_CONTROL_IP" "$TC_CONTROL_PORT" <<'PY'
import ipaddress, socket, sys
address = str(ipaddress.IPv4Address(sys.argv[1])); port = int(sys.argv[2]); assert 1 <= port <= 65535
with socket.create_connection((address, port), timeout=1): pass
print('host baseline reachable')
PY
read -r -p 'Authorize one scoped diagnostic container; type scope UUID: ' TC_PERMISSION
test "$TC_PERMISSION" = "$TC_SCOPE"
dc run --rm --pull=never --name "tc-mvp-diagnostic-$TC_SCOPE" \
  --network "container:$TC_TARGET" --user 0:0 --read-only --cap-drop ALL \
  --security-opt no-new-privileges --memory 64m --pids-limit 16 --cpus 0.25 \
  --label "tc-mvp.scope=$TC_SCOPE" --label tc-mvp.role=diagnostic \
  --entrypoint /usr/local/bin/python "$TC_VERIFIER_IMAGE" -I -S -B -c \
  'import ipaddress,socket,sys; a=str(ipaddress.IPv4Address(sys.argv[1])); p=int(sys.argv[2]); assert 1<=p<=65535
try:
 s=socket.create_connection((a,p),timeout=1)
except OSError:
 print("task netns control connect denied")
else:
 s.close(); raise SystemExit("UNEXPECTED CONTROL REACHABILITY")' "$TC_CONTROL_IP" "$TC_CONTROL_PORT"
"$TC_PY" -m "$TC_MODULE" audit --config "$TC_LAB/config.json"
```

Diagnostic использует protected image/code и ту же task network namespace,
без mounts/socket/capabilities; task tools не участвуют. Он проверяет конкретный
TCP flow, не весь control plane, filesystem/process isolation или все виды traffic.
Отдельно review фактические task → daemon/host/terminal endpoints. Сама dedicated
bridge и `internal=true` не являются доказательством denial. В `isolated` mode Docker
не назначает IP bridge interface; это уменьшает поверхность, но не заменяет probes.
[Docker gateway modes](https://docs.docker.com/engine/network/port-publishing/#gateway-modes),
[bridge semantics](https://docs.docker.com/engine/network/drivers/bridge/),
[container run flags](https://docs.docker.com/reference/cli/docker/container/run/).
Повторить positive host baseline после negative probe: остановившийся listener
не должен давать ложное evidence network denial. Для отсутствующих/неразрешённых
endpoints сохранить `unverified`, не подменять это результатом «доступ запрещён».

## 6. Scoped cleanup

Runner удаляет только свой verifier через original adapter. При cleanup_unknown
или оставшемся worker — **stop**, сохранить claim/result; оператор сначала сверяет
full worker ID из artifact, exact run/execution UUID/scope/image/name. Не удалять
контейнер лишь по role label и не запускать prune/cleanup-all. Ниже — normal cleanup
только нового target/network после successful quiescent audit:

```bash
"$TC_PY" -m "$TC_MODULE" audit --config "$TC_LAB/config.json"
test "$(dc info --format '{{.ID}}')" = "$TC_DAEMON"
test "$(dc inspect -f '{{.Id}}' "$TC_TARGET")" = "$TC_TARGET"
test "$(dc inspect -f '{{.Image}}' "$TC_TARGET")" = "$TC_TARGET_IMAGE"
test "$(dc inspect -f '{{index .Config.Labels "tc-mvp.scope"}}' "$TC_TARGET")" = "$TC_SCOPE"
test "$(dc inspect -f '{{index .Config.Labels "tc-mvp.environment"}}' "$TC_TARGET")" = "$TC_ENV"
test "$(dc network inspect -f '{{.Id}}' "$TC_NETWORK")" = "$TC_NETWORK"
test "$(dc network inspect -f '{{.Name}}' "$TC_NETWORK")" = "tc-mvp-$TC_SCOPE"
test "$(dc network inspect -f '{{index .Labels "tc-mvp.scope"}}' "$TC_NETWORK")" = "$TC_SCOPE"
read -r -p 'Remove ONLY recorded new target/network; type scope UUID: ' TC_PERMISSION
test "$TC_PERMISSION" = "$TC_SCOPE"
dc rm -f "$TC_TARGET"
test "$(dc network inspect -f '{{len .Containers}}' "$TC_NETWORK")" = 0
dc network rm "$TC_NETWORK"
dc container ls -a --no-trunc > "$TC_LAB/containers-after-cleanup.txt"
dc network ls --no-trunc > "$TC_LAB/networks-after-cleanup.txt"
```

Сохранить private records/artifacts/output; не удалять их для повторения одного
run. Сравнить foreign inventories с исходными. Старые `tc-mvp-lab`, smoke targets,
images, H1/H2 и старая сетевая лаборатория не входят в cleanup authority.

## 7. Что выполнено здесь

Созданы runner, [9 offline runner tests](experiments/trusted_checker_mvp/docker_pilot/test_real_lab.py)
и этот runbook. [Лог](experiments/trusted_checker_mvp/docker_pilot/real_lab_tests.txt):
**34 tests, OK, 0.270s**, без skips/failures/errors/ResourceWarning. Проверены explicit
permission до APIClient, original adapter positive/replay, stale restart без repin,
old network/unsafe target refusal, unavailable image, private/changed record refusal,
unresolved own worker и foreign inventory discrepancy. Все Docker calls — fake SDK;
TCP/socket/network/container effects отсутствуют.

Целостность [516 baseline files](experiments/trusted_checker_mvp/docker_pilot/real_lab_integrity.json)
проверяется отдельно; прежние adapter/worker/probe, Django integration, H1/H2,
RR01–RR05, reports и physical gates не редактировались. Полные Django/H1 suites не
перезапускались: их исходники не менялись. Не было build/pull, реального APIClient,
SSH/VDS, academic writes, host mutations, commit/push/rebase/deploy.

**На VDS ещё предстоит всё из разделов 2–6:** measured prerequisites, real adapter
observations, negative cases, ownership cleanup и lab security probes. `bind`,
`process`, `network_isolation` остаются unverified даже у HTTP match. После получения
реальных outputs нужен короткий review; этот документ не объявляет real pilot PASSED.
