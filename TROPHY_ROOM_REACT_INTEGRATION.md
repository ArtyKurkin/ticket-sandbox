# Trophy Room React Integration

14 октября 2026. Задача №12, `feature/roadmap-react`.

Trophy Room подключён к существующему Django Achievement API. Одна definition отображается одной карточкой по public UUID; текущий металл берётся из highest_tier. Дизайн тёмной галереи, геометрия медальонов, адаптивность, native dialog и анимации сохранены. Условия/evaluators, Sandbox, TraineeDiary, модель Roadmap и API backend не менялись.

## Файлы

Изменены:

- `react_frontend/views.py` — только Trophy Room bootstrap: достоверный `canDemo=request.user.is_staff`, reverse собственного API и login URL.
- `frontend/src/achievements/TrophyRoom.tsx`, `TrophyCard.tsx`, `TrophyDetails.tsx`, `TrophyFilters.tsx`, `TrophyMedallion.tsx`, `TrophyShell.tsx`, `TrophyUnlockToast.tsx` — реальная коллекция, состояния, история, фильтры, палитра и изолированный demo.
- `frontend/src/achievements/types.ts`, `styles.css`, `README.md`, `data.ts` — nullable tier/progress, API состояния, responsive стили и отдельный тип старых demo fixtures.
- Девять `frontend/src/achievements/art/*.tsx` — только цвета и комментарий о палитре. SVG пути, координаты, transforms, viewBox, filter geometry и offsets градиентов не менялись.
- `frontend/tests/helpers.cjs` — добавлен выбор папки модулей; существующий Roadmap loader по умолчанию сохранён.

Созданы:

- `frontend/src/achievements/api.ts` — валидирующий read-only API client.
- `frontend/src/achievements/useTrophies.ts` — loading/ready/error, retry и отмена запросов.
- `frontend/src/achievements/palette.ts` — четыре металлические и одна нейтральная палитра.
- `frontend/src/achievements/demonstration.ts` — отдельная lazy-loaded демонстрация.
- `frontend/tests/trophies.test.cjs` — проверки API, состояния, истории, палитр, фильтров и demo.
- `frontend/tests/fixtures/trophies/{real,internal,empty,independent_speed-detail,clean_week-detail}.json` — реальные ответы локального Django на синтетических данных; не входят в Vite bundle.
- `react_frontend/test_trophy_integration.py` — server-owned bootstrap и игнорирование попыток включить demo/query URL.
- `docs/trophy-room-integration/*.png` — Chromium screenshots, ссылки ниже.
- Этот отчёт.

Проверка исходных хешей: все `achievements/`, бизнес-сервисы, миграции, Roadmap source и его SVG-маршрут, существующие отчёты и прочие результаты задач 7–11 совпали с начальным состоянием. Изменено 22 существующих исходных/документальных файла в перечисленном scope. Игнорируемый `static/frontend/` пересобран; это не отдельная правка исходников Roadmap. Commit/push/merge/deploy не выполнялись, production не подключалась.

## API и обычный режим

Основной запрос — `GET /api/achievements/me/`. Bootstrap получает URL через Django reverse. Client использует GET, same-origin session cookies, no-store, Accept JSON и AbortSignal. Пути проверяются и ограничены собственным achievements API; browser не вызывает POST, reconcile, source drain или выдачу.

JSON проверяется на структуру, UUID, допустимый status, nullable applicability/highest tier, supported tiers, даты, stats и cursor. Earned без реального highest_tier, дубли public UUID, неизвестный металл и некорректный progress отклоняются как contract error. Один DTO превращается в один медальон; при bronze→platinum его UUID/key сохраняется. Supported tiers не создают отдельные карточки или события.

Статистика `earned`, `applicable_total`, `rarities` отображается непосредственно из сервера и не пересчитывается по отфильтрованной сетке. При progress=null нет полосы, процента карточки или выдуманного процента комнаты. Фильтры работают по реальному status, раскрытому текущему металлу/фиксированной редкости и раскрытой category. Подписи известных категорий переведены для пользователя; смысл и числовые критерии не меняются.

Неполученная tiered линейка имеет нейтральный медальон и «Уровень не получен», без фиктивной бронзы. Для раскрытой fixed награды допустимо показать известную серверную редкость с замком и статусом «Не получено». Applicability=false показывается как «Не требуется»; null — «Применимость уточняется». Revoked остаётся неполученным и не увеличивает earned. Disputed помечается «Результат требует проверки», сохраняя серверный уровень. Pending events сопровождаются предложением обновить коллекцию позже.

`demoAchievements`, старые проценты, даты 2024 года, вымышленные комментарии и локальное вычисление earned/total удалены из обычного режима. Даты форматируются только из серверных timestamps, не создаются из текущего времени браузера.

## Медальоны

`TrophyMedallion` выбирает геометрию по локальному whitelist art_key:

| Ключ | Геометрия |
|---|---|
| generic / training | MissionArt |
| sandbox / milestone | MilestoneArt |
| quality | ArchitectureArt |
| speed | AutomationArt |
| probation | MasterArt |
| independent | SyncArt |
| Любой будущий неизвестный ключ | Безопасный MissionArt fallback |

Сервер не передаёт SVG/HTML. Object.hasOwn исключает special/prototype keys. React рендерит строки как текст; dangerouslySetInnerHTML не используется.

Геометрия постоянна. Palette задаёт rim/bevel/core stops, светлые грани, средние/тёмные поверхности, тени и accent. Все девять art-компонентов используют CSS variables в градиентах и внутренних металлических элементах. Поэтому повышение меняет **весь металл**, а не только рамку/CSS-класс. Цвета и признаки материала соответствуют исходной концепции: тёплая бронза, холодное серебро, золото, платина с сиренево-голубыми бликами. SVG useId сохранён, ссылки на gradients уникальны.

## Секреты

Источник — secret/revealed из API. Закрытый секрет всегда получает одну нейтральную вопросительную геометрию, placeholder title, без condition/progress/category/metal. Код и UUID не используются для угадывания art или условий. Даже дополнительные секретные metadata в некорректном ответе не попадают в отображение. Такой элемент не участвует в отдельных metal/category фильтрах; доступен только в нейтральных/status фильтрах.

После получения используется раскрытая сервером metadata и настоящий art_key/metal. После revoke тот же UUID снова становится закрытым. История закрытого секрета отсутствует, как в API. Старые загруженные страницы истории удаляются, если очередная страница возвращает скрытый secret.

## Модалка и история

При открытии выполняется `GET /api/achievements/me/<public_id>/`. Состояние коллекции не считается заменой серверной истории. UI показывает current tier, его criterion, все публичные supported tiers, первую настоящую дату выдачи, manual flag и настоящие события.

История сортируется/объединяется по event ID. Показано только полученное с сервера grant/upgrade/revoke/evidence_disputed; bronze→platinum остаётся одним upgrade. Дата события выдачи берётся из recorded_at, не из более ранней даты исходного учебного результата. Причина ручного действия/отзыва отображается текстом. Имя наставника не выдумывается из actor_id.

Пагинация использует next_cursor; «Показать ещё» запрашивает следующую страницу. Повторные event IDs дедуплицируются. Abort защищает от устаревших ответов; новое определение/revision получает новую модалку, старые detail запросы отменяются. Native showModal, Escape, backdrop close, Tab/Shift+Tab trap и возврат к исходной кнопке сохранены. После открытия из demo toast фокус возвращается к устойчивой кнопке демонстрации.

## Наставник и demo

Комната всегда личная — staff тоже читает me. Административных grant/revoke кнопок нет.

canDemo приходит только из Django is_staff, а не из role text или query-параметров. Управление скрыто у обычного пользователя; обработчики отдельно проверяют строгий canDemo===true. Demo загружается отдельным Vite chunk только после явного переключения staff. Его items/stats/selection/toast отделены от API state; сверху указано «Демонстрационный режим» и пояснение, что настоящие выдачи не меняются. Unlock выполняет только React update, не POST, не создаёт дату и не изменяет Django. Возврат очищает demo toast и возвращает реальную коллекцию. Ошибка загрузки demo chunk не подменяет реальную коллекцию.

## Уведомления: честное ограничение текущего API

В обычном режиме toast **пока не запускаются**. Collection DTO не содержит event ID/action последней выдачи; revision меняется также при отзыве и спорном доказательстве. Нельзя достоверно вывести новый grant/upgrade из загрузки, фильтра или открытия history. Initial load, повторный snapshot, retry, details и выход из demo не порождают уведомлений. Компонент анимации и glow сохранён для явно помеченной демонстрации.

Минимальное будущее расширение, **не реализованное этой задачей**: opaque/event cursor в collection и отдельная read-only доставка новых user-owned событий с event ID, action и definition public UUID. Первая загрузка устанавливает baseline без toast; последующие grant/upgrade дедуплицируются по ID и подтверждаются текущим DTO. Нужны server-side secret redaction и проверка актуального revoke state. Такая доставка не должна выдавать награды или создавать синтетическую историю. В текущем контракте новых backend полей/эндпоинтов не добавлено.

## Ошибки

Есть loading, пустой каталог, пустой результат фильтра, 401 с login link, 403, исчезнувшее definition/404, 500/server, сеть и malformed JSON. Ошибка API не показывает demo fixtures или прежнее успешное состояние. Retry — явный GET. Ошибка следующей страницы истории сохраняет уже успешно прочитанные события; 401/403/404 убирает detail/history. Кнопка «Обновить» позволяет получить новый серверный максимум без перезагрузки страницы. Polling и административные операции не добавлены.

## Проверки

| Проверка | Результат |
|---|---|
| Frontend tests | **46/46 OK**, включая прежние Roadmap проверки |
| TypeScript typecheck | OK; также выполняется production build |
| Vite production build | OK, отдельный lazy demonstration chunk |
| Django achievements + react_frontend + roadmap | **125 тестов, OK**, 8 существующих PostgreSQL-specific skips |
| Django system checks | 0 ошибок |
| makemigrations --check --dry-run | No changes detected; backend schema не менялась |
| git diff --check | OK |
| Chromium 1440×900 / 1280×800 / 768×1024 / 390×844 | OK: без horizontal overflow, медальоны не обрезаны, dialog внутри viewport |
| Native keyboard / focus | Escape, Shift+Tab loop и возврат к карточке — OK |
| History pagination | 50 + 3 настоящих события, 53 уникальных IDs — OK |
| Level refresh | 11 прежних UUID, одна speed карточка bronze→platinum, ровно grant+upgrade — OK |
| Secret receive/revoke | Раскрытие/повторное скрытие того же UUID — OK |
| Staff demo | Отдельное состояние, возврат исходных stats, UI API requests только GET — OK |
| Error/retry Chromium | Loading, empty, 401/403/500, offline, detail 404 и успешный повтор — OK |
| Ordinary toast | Отсутствует при load/filter/details/retry/upgrade refresh/demo exit — OK |

Основные screenshots сделаны через **настоящий Django API в обычном режиме** на новой `/tmp/trophy12.sqlite3`, а не через demo или production. Автоматические базовые награды проверены на синтетических Roadmap/Sandbox/metric фактах. Четыре сравнительные палитры и раскрытие секрета проверялись через существующий staff manual service на отдельных синтетических пользователях, с явно записанными тестовыми причинами/source=manual. Это не свидетельство результатов реальных сотрудников или полной недели. Автоматические Sandbox silver/gold/platinum и clean_week не включались. Ошибки HTTP/сети и пустой каталог дополнительно проверены локальным перехватом браузерных ответов; эти снимки обозначают UI error/empty состояния.

Тесты не запускали Docker-сценарии или production backfill. Полный Django suite из задачи 11 не выдаётся за новый полный прогон; здесь выполнен затронутый набор из 125 тестов. Preview server и отдельный Chromium профиль после проверки остановлены.

## Скриншоты

| Обычная галерея | История на том же разрешении |
|---|---|
| [1440×900](docs/trophy-room-integration/real-1440x900.png) | [История 1440×900](docs/trophy-room-integration/history-1440x900.png) |
| [1280×800](docs/trophy-room-integration/real-1280x800.png) | [История 1280×800](docs/trophy-room-integration/history-1280x800.png) |
| [768×1024](docs/trophy-room-integration/real-768x1024.png) | [История 768×1024](docs/trophy-room-integration/history-768x1024.png) |
| [390×844](docs/trophy-room-integration/real-390x844.png) | [История 390×844](docs/trophy-room-integration/history-390x844.png) |

Одна и та же геометрия speed медальона, разные серверные уровни:

| Бронза | Серебро | Золото | Платина |
|---|---|---|---|
| [Снимок](docs/trophy-room-integration/medal-bronze.png) | [Снимок](docs/trophy-room-integration/medal-silver.png) | [Снимок](docs/trophy-room-integration/medal-gold.png) | [Снимок](docs/trophy-room-integration/medal-platinum.png) |

Дополнительные состояния:

- [Один медальон после повышения](docs/trophy-room-integration/one-medallion-after-upgrade.png), [bronze→platinum без промежуточных событий](docs/trophy-room-integration/bronze-to-platinum-history.png).
- [Закрытый секрет](docs/trophy-room-integration/secret-locked.png), [ручная тестовая выдача секрета](docs/trophy-room-integration/secret-earned-manual.png), [секрет после отзыва](docs/trophy-room-integration/secret-revoked.png).
- [Неприменимые награды внутреннего сотрудника](docs/trophy-room-integration/internal.png), [нет полученных наград](docs/trophy-room-integration/no-awards.png), [53 события истории](docs/trophy-room-integration/paginated-history.png).
- [Staff demo с пометкой](docs/trophy-room-integration/staff-demo.png).
- [Loading](docs/trophy-room-integration/loading.png), [empty catalogue](docs/trophy-room-integration/empty-catalogue.png), [401](docs/trophy-room-integration/error-401.png), [403](docs/trophy-room-integration/error-403.png), [500](docs/trophy-room-integration/error-500.png), [ошибка сети](docs/trophy-room-integration/error-network.png), [detail 404](docs/trophy-room-integration/detail-404.png).

## Локальная проверка и оставшиеся ограничения

На выбранной локальной БД с применёнными backend migrations:

```sh
npm test --prefix frontend
npm run typecheck --prefix frontend
npm run build --prefix frontend
# Используйте настройки своей локальной БД; для изолированных тестов:
DEBUG=True DB_ENGINE=django.db.backends.sqlite3 DB_NAME=:memory: SENTRY_DSN='' .venv/bin/python manage.py check
DEBUG=True DB_ENGINE=django.db.backends.sqlite3 DB_NAME=:memory: SENTRY_DSN='' .venv/bin/python manage.py test achievements react_frontend roadmap --noinput
```

В обычной комнате обновление результатов запускается вручную. Будущие push/poll/event feed, полноценный staff grant/revoke UI и расширенные server eligibility/progress относятся к отдельным задачам. Коллекция пока отдаётся целиком; пагинация есть у history. Backend применимость, denominator и disputed/regrant policy сохранены. Если активная ручная/историческая награда стала неприменимой текущему контексту, frontend сохраняет earned по API; общие counts не переопределяются клиентом. Полная покрытая неделя и scored/timed курс не выдумываются.

Реализация завершена. К следующей задаче переход не выполнялся.
