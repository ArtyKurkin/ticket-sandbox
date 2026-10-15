# React Roadmap Integration

Контракт навигации расширен задачей 9: [Roadmap Actions & Navigation](ROADMAP_ACTIONS_NAVIGATION.md). Упоминания пустых actions ниже описывают состояние до этой задачи.

Обычный Data Center Journey теперь получает реальные состояния из существующего Django Roadmap API. Серверная бизнес-логика, модели, Sandbox, TraineeDiary и Trophy Room в этой задаче не изменены. Незакоммиченные файлы задачи 7 сохранены.

## Изменённые файлы

- `react_frontend/views.py` — вместо initialProgress/trophyCount bootstrap передаёт roadmapApiUrl и loginUrl; canDemo по-прежнему вычисляется из request.user.is_staff.
- `react_frontend/tests.py` — проверка новых bootstrap-полей и отсутствия фиктивного прогресса/наград.
- `frontend/src/roadmap/types.ts` — визуальные типы, отделённые от JSON; независимые состояния станций.
- `frontend/src/roadmap/data.ts` — только прежние координаты, иллюстрации и предпочтительные стороны карточек; демонстрационные метрики удалены.
- `frontend/src/roadmap/RoadmapPage.tsx` — загрузка, retry, ошибки, реальный overall и явно включаемое демо.
- `frontend/src/roadmap/RoadmapDemoControls.tsx` — явное возвращение к реальным данным.
- `frontend/src/roadmap/RoadmapCanvas.tsx` — отображение восьми станций по стабильным ID, без completedCount.
- `frontend/src/roadmap/RoadmapStation.tsx` — независимые статусы, COMING SOON/not_required, нейтральный финал прекращённого ИС.
- `frontend/src/roadmap/RoadmapPath.tsx` — прежние SVG-кривые с подсветкой по состояниям конечных станций каждого сегмента.
- `frontend/src/roadmap/LivingDataCenter.tsx` — прежние LED/сектора, активируемые состояниями соседних станций.
- `frontend/src/roadmap/StageDetails.tsx` — реальные задания, снимок Sandbox, доработки, метрики, периоды и readiness; только серверные ссылки.
- `frontend/src/roadmap/styles.css` — локальные стили новых состояний, уведомлений и сообщений API; исходная геометрия сохранена.
- `frontend/src/roadmap/README.md` — описание интеграции и запуска.
- `frontend/tests/roadmap.test.cjs` — сохранены тесты позиционирования, удалён прежний тест демонстрационной линейной модели обычного режима.

Созданы:

- `frontend/src/roadmap/apiTypes.ts` — строгие TypeScript-типы ответа v1.
- `frontend/src/roadmap/api.ts` — runtime-проверка неизвестного JSON, session fetch, HTTP/contract ошибки.
- `frontend/src/roadmap/useRoadmap.ts` — жизненный цикл запроса, AbortController и retry.
- `frontend/src/roadmap/presentation.ts` — сопоставление по ID, безопасное форматирование, подсветка и изолированное демо.
- `frontend/tests/helpers.cjs`, `frontend/tests/roadmap-api.test.cjs` — тесты контракта, API-клиента и рендера; без новых зависимостей.
- `ROADMAP_REACT_INTEGRATION.md`, `docs/roadmap-integration/before/*.png`, `docs/roadmap-integration/after/*.png` — отчёт и 17 скриншотов браузерной проверки.

Generated `static/frontend/` обновлён production-сборкой; каталог уже исключён из Git. Не менялись шаблон, frontend bootstrap entrypoint, SVG art, фон, шрифты, алгоритм positionCard и компоненты Trophy Room.

## Подключение и типы

Django через json_script передаёт профиль и reverse("roadmap_api:me"). React выполняет GET с credentials=same-origin, Accept=application/json, cache=no-store. Успешность HTTP проверяется до JSON. Поддерживаются отмена устаревших запросов и отсутствие обновлений после размонтирования; cleanup вызывает AbortController.abort, оба обработчика результата проверяют signal.aborted.

Только корректный schema_version=1 с восемью уникальными известными станциями используется как Roadmap. Проверяются порядок/ID, значения статусов, числа, nullable поля, даты, метрики, уведомления, evidence, readiness и действия. Серверный overall не пересчитывается, даже если состояния нелинейны. Прогресс форматируется с русской десятичной запятой.

Типы разделены на ModuleAvailability, IndividualState, DisplayStatus, JourneyState, OverallProgress, StageProgress, StageNotification, StageAction, DataQuality, StageEvidence, StagePeriod, Readiness, WeeklyMetric, ApiStage и RoadmapResponse. Геометрия хранится отдельно в StationGeometry. any не используется.

Клиент может загружать `/api/roadmap/trainees/<journey_id>/`, если этот URL передан доверенным Django bootstrap. Текущий серверный view выбирает только me: существующего выбора чужого стажёра на этой странице нет, новый публичный UI и новый route не добавлялись. Staff-права проверяет существующий API.

Загрузка и ошибка показывают понятное сообщение без демонстрационных значений. Временную ошибку можно повторить без полной перезагрузки; 401 предлагает вход, 403 сообщает об отсутствии доступа, 404 — об отсутствии адаптации, неправильный JSON/версия — о неподдерживаемом контракте. Если journey.state=not_started, показываются все восемь станций и объяснение; фиктивный персональный процент и трофеи отсутствуют.

## Все восемь станций

| № | ID | Поведение |
|---|---|---|
| 01 | training | Ручное подтверждение определяется только серверным state. Сама по себе последующая рабочая станция не даёт галочку. Для внутреннего перевода — not_required по API. |
| 02 | sandbox | state отражает сохранённое техническое завершение; progress показывает текущий каталог, completion — исторический снимок. Текстовые уведомления независимы. Никаких вычислений технического зачёта в React. |
| 03 | escalation | coming_soon по API: серо-голубая станция, моноширинная плашка, информационная карточка с серверным описанием; без замка и запуска. |
| 04 | ticket_analysis | Аналогично 03; доступность не зашита в React по ID. Включение через API-флаги переводит компонент в обычное состояние. |
| 05 | with_review | Серверное завершение/текущая работа, реальные периоды, доступные метрики и readiness; подсветка фактической текущей позиции. |
| 06 | optional_review | Аналогично 05; возврат не дорисовывает прежние завершения. |
| 07 | no_review | Аналогично 05; число обработанных тикетов не выдумывается. |
| 08 | probation | Серверные success/active/terminated/insufficient_data. Прекращение даёт нейтральный финал без успешной галочки/поздравления; нахождение на done само по себе не даёт успеха. |

«Не требуется» отличается от COMING SOON: нейтральный серый цвет и grayscale иллюстрация, собственная подпись и объяснение; без замка, галочки и награды. Применимость не выводится из entry_type на клиенте.

Текущий рабочий этап визуально выделяется по серверной current_stage и individual state. Это сопоставление названий/slug для визуальной позиции, не расчёт бизнес-успеха. Общий временной прогресс адаптации не смешивается с overall Roadmap.

Фоновая линия SVG всегда непрерывна. Яркий сегмент появляется только при активных обеих конечных станциях (completed/in_progress, enabled, applicable). Через COMING SOON, not_required и отсутствующее завершение остаётся приглушённый маршрут; это не блокирует реальный рабочий этап. Нелинейные этапы не выводятся из индекса completed_count.

Рабочие карточки показывают последние доступные метрики с номером недели, явно обозначают зафиксированное качество и берут рекомендации из readiness. Неизвестные показатели не заменяются нулём. Даты и длительность берутся из periods; никакие пороги скорости/качества не повторяются в React.

## Примеры фактического отображения

Браузер использовал существующий API и только синтетические записи временной SQLite:

- Внешний найм: **2 из 6 этапов · 33,3%**. Обучение подтверждено, сохранено завершение Sandbox с текущими заданиями **3/3**, три ответа требуют доработки и три комментария непрочитаны. Sandbox completed; текущий этап 05 выделен, 03/04 COMING SOON.
- Внутренний перевод: **1 из 4 этапов · 25%**. 01/02 «Не требуется», 03/04 COMING SOON, 05 completed, текущий 06 выделен.
- Возврат 05 → 06 → 05: 05 текущий, 06 не помечается завершённым, яркий сегмент 05–06 отсутствует.
- Legacy с пропуском 06: текущий 07 сохранён, пропущенные завершения не дорисованы.
- Прекращение ИС: финал нейтральный, успешная галочка отсутствует.
- Успешный внутренний ИС: **4 из 4 этапов · 100%**, финальная станция completed.

Staff-демо использует отдельные локальные состояния 1/8, 3/8, 6/8, 8/8 и надпись «Демонстрация». Процент не выдаётся за реальный, награды отсутствуют. Кнопка «Реальные данные» возвращает исходный ответ API, включая COMING SOON; запросов записи и дополнительных запросов при переключении демо нет.

## Визуальная проверка

Снимки сделаны до изменений и после интеграции в доступном Chromium. Сравнение включает фактические изображения и DOM-проверку неизменности CSS-координат восьми станций и всех SVG path d. Во всех четырёх размерах проверены все восемь карточек: data-intersections=0. Нет внешнего горизонтального переполнения; существующая внутренняя прокрутка сохранена. Enter, Space, Escape и закрытие снаружи проверены реальными браузерными событиями. Проверка с prefers-reduced-motion=reduce выполнена, правила отключения анимаций сохранены.

| Размер | До интеграции | После интеграции |
|---|---|---|
| 1920×1080 | [Исходный](docs/roadmap-integration/before/1920x1080.png) | [Внешний найм](docs/roadmap-integration/after/external-1920x1080.png) |
| 1600×1280 | [Исходный](docs/roadmap-integration/before/1600x1280.png) | [Внешний найм](docs/roadmap-integration/after/external-1600x1280.png) |
| 1440×900 | [Исходный](docs/roadmap-integration/before/1440x900.png) | [Внешний найм](docs/roadmap-integration/after/external-1440x900.png) |
| 390×844 | [Исходный](docs/roadmap-integration/before/390x844.png) | [Внешний найм](docs/roadmap-integration/after/external-390x844.png) |

Дополнительные состояния: [COMING SOON](docs/roadmap-integration/after/coming-soon-1440x900.png), [внутренний перевод](docs/roadmap-integration/after/internal-1440x900.png), [прекращение](docs/roadmap-integration/after/terminated-1440x900.png), [успех](docs/roadmap-integration/after/success-1440x900.png), [возврат](docs/roadmap-integration/after/return-1440x900.png), [legacy](docs/roadmap-integration/after/legacy-1440x900.png), [staff-демо](docs/roadmap-integration/after/staff-demo-1440x900.png), [загрузка](docs/roadmap-integration/after/loading-1440x900.png), [ошибка](docs/roadmap-integration/after/error-1440x900.png).

Изменения относительно исходного дизайна ограничены новым содержимым: реальный счётчик вместо 1/8, удаление трофеев, отдельная строка состояния адаптации, новые плашки, уведомления/метрики и явный переключатель демо. Toolbar может занимать меньше строк без старых демо/трофеев. Карточки с большим количеством реальных данных выше прежних и используют существующий резерв прокручиваемого пространства. Фон, SVG, маршрут, шрифты, координаты, отступы основных элементов и positionCard не переработаны. Pixel-perfect соответствие не утверждается: содержание и состояния намеренно отличаются.

## Проверки и ограничения

Проверено 14 октября 2026:

| Проверка | Результат |
|---|---|
| npm run typecheck --prefix frontend | OK |
| npm run build --prefix frontend | Production Vite build, OK |
| npm test --prefix frontend | 24 теста, OK; включая отмену после размонтирования и сохранение снимка при диагностике |
| Django system checks | 0 ошибок |
| Django regression: react_frontend, roadmap, traineediary, sandbox progress/completions | 281 тест, OK; 1 skip — PostgreSQL row-lock тест, уже проверенный в задаче 7 |
| Повтор React integration после финальной Vite-сборки | 11 тестов, OK |
| Chromium: четыре размера, восемь карточек в каждом | 32 карточки, без пересечений; координаты и SVG-кривые совпадают |
| Chromium: реальные API-сценарии | Внешний/внутренний, not_started, legacy, возврат, успех/прекращение — OK |
| Chromium: loading, 503, retry без навигации, 401, неподдерживаемая версия | OK; без демонстрационного fallback |
| Chromium: staff-демо, переключение в реальный режим | OK; только GET запросы, никаких подтверждений/наград |
| Chromium: Runtime.exceptionThrown | 0 ошибок |
| git diff --check | OK |

Найденное ограничение API: все actions пока пустые. Поэтому карточка Sandbox не придумывает URL; существующая боковая ссылка остаётся. При появлении server actions с label/url клиент покажет их для применимого enabled и незаблокированного этапа. Ссылки действий допускаются только как локальные пути того же origin, без javascript/data/внешних адресов. Для будущих провайдеров и новых полей прогресса потребуется согласованный контракт API.

Публичный выбор чужого стажёра и UI ручного подтверждения не создавались. GET не меняет историю, снимки или комментарии. Ошибки не скрываются демонстрационным прогрессом. Backend достижений отсутствует; в Roadmap нет счётчика наград. Trophy Room сохранён. Браузерный тестовый сервер и Chromium с отдельным профилем остановлены после проверок. Production не читалась и не мигрировалась. Commit, push, merge и деплой не выполнялись; ветка feature/roadmap-react сохранена.

## Локальный запуск

Для уже настроенной локальной базы:

```sh
npm run build --prefix frontend
DEBUG=True .venv/bin/python manage.py runserver
```

После входа открыть `http://127.0.0.1:8000/roadmap/`. `npm ci --prefix frontend` нужен только если зависимости ещё не установлены. Staff создаёт адаптацию через существующую панель TraineeDiary; без адаптации отображается not_started. Завершения поступают из существующих механизмов, а не из демо.

Для новой изолированной SQLite (не выполнять с production-настройками):

```sh
export DEBUG=True DB_ENGINE=django.db.backends.sqlite3 SENTRY_DSN=''
export DB_NAME="$(mktemp -t roadmap-integration)"
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py seed_stages
.venv/bin/python manage.py createsuperuser
npm run build --prefix frontend
.venv/bin/python manage.py runserver
```

Для повторной проверки: npm test, npm run typecheck и `manage.py test react_frontend roadmap` с явно выбранной тестовой БД. На этом этапе работа завершена; система достижений требует отдельного задания.
