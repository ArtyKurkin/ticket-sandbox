# Ticket Sandbox: local HTTP smoke PoC

Из repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -W error::ResourceWarning -m unittest experiments.trusted_checker_mvp.test_mvp -v
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -W error::ResourceWarning -m experiments.trusted_checker_mvp.demo
```

Нужны права на **собственные loopback sockets** и запуск локального Python.
Fixtures выбирают свободные ephemeral ports через ОС; порт 8080 существующих
приложений не используется. Если выбранный порт занят между reservation и bind,
test явно падает: чужие listeners не удаляются, fallback на другой target нет.
Tests запускаются последовательно. Новых зависимостей нет.

`local.py` запускает `verifier.py` отдельным процессом. Fixed task verifier
сам выполняет GET `/`, проверяет HTTP 200 и exact task body. Он не вызывает
check.sh/curl/ip и не принимает результат из HTTP body. `LocalControl` — только
trusted in-memory запись demo; у неё нет сетевого API. `demo.py` использует
owned server fixture из `test_mvp.py`, а не service из trainee image.

Это **smoke test, не контейнерная изоляция**: parent/fixture/verifier работают
с правами текущего пользователя, без hostile root container. Host-controlled
ephemeral endpoint не доказывает task port 8080, named service или bind внутри
netns. Эти поля всегда `unverified`; `task_verdict` никогда не `passed`,
`academic_pass=false`. Не использовать PoC как checker реального root trainee
на общем UID/host. Production endpoint adapter намеренно отсутствует.

13 tests проверяют подмену скрипта/tools/JSON, реальные loopback ответы,
неверные body/status/port, unavailable, timeout/reap, replay и смену generation.
Container-to-checker/control-plane network denial здесь **не проверяется**;
проверяется лишь отсутствие ingress API в этой программе и невозможность
использовать HTTP response как control request.

[Полный design](../../TRUSTED_CHECKER_MVP_SIMPLIFICATION.md) содержит trust
boundary, comparison A/B и отдельный production integration plan.

Evidence: [tests.log](tests.log), [demo-result.json](demo-result.json),
[integrity.json](integrity.json). Result — пример исторического наблюдения,
не принимаемый вход API и не reusable receipt. Времена tests не Docker benchmark.
