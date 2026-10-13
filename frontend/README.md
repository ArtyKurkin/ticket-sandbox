# React Islands в Training Platform

Django сохраняет маршрутизацию, авторизацию, роли, API и бизнес-логику.
React монтируется только в явно добавленные `data-react-island` контейнеры.
Техническая страница: `/internal/react-readiness/`, доступна после обычного входа Django.
Она имеет отдельный минимальный шаблон без внешних runtime-зависимостей.

## Локальный запуск

Нужен Node.js 22.12+ (в CI/Docker используется Node 22) и существующее Python-окружение проекта.

```sh
cd frontend
npm ci
npm run typecheck
npm run build
npm run dev
```

`dev` — Vite build в watch-режиме. В другом терминале из корня запустите
Django по существующей инструкции проекта с `DEBUG=True`:

```sh
python manage.py runserver
```

Войдите через `/login/`, откройте `/internal/react-readiness/`.
После изменений дождитесь сборки и обновите страницу. HMR/dev server не используется.
В watch-режиме typecheck выполняйте отдельно.

## Production

```sh
npm ci --prefix frontend
npm run build --prefix frontend
python manage.py collectstatic --noinput
```

Vite создаёт `static/frontend/manifest.json` и hashed assets. Каталог сборки
и node_modules не коммитятся; package-lock.json коммитится.
Django tag `vite_assets` читает manifest из исходной статики при DEBUG=True,
из collected storage при DEBUG=False, подключает JS, CSS и static imports.
Отсутствующая сборка вызывает явную ошибку, без fallback на dev server.
Относительный Vite base сохраняет внутренние пути chunks и изображений.
WhiteNoise сохраняет оригинальные Vite hashed файлы и создаёт свои hashed
версии; Django storage разрешает URL верхнего уровня. Не включайте
WHITENOISE_KEEP_ONLY_HASHED_FILES: внутренние JS imports могут использовать
исходные имена Vite. При релизах сохраняйте старые assets для открытых вкладок.
Для будущих JS dynamic imports проверяйте полную цепочку файлов после collectstatic.

## Новые компоненты

Размещайте компоненты в `src/roadmap`, `src/achievements`, общий UI в
`src/shared/ui`, типы в `src/types`. Сейчас доменные каталоги пустые.
Добавляйте явное сопоставление контейнера и компонента в `src/main.tsx`;
для больших интерфейсов можно добавить отдельные Vite entry и передать
их имя в `{% vite_assets "src/another-entry.tsx" %}`.
Новые Django страницы защищайте существующими permission checks и login_required.
Начальные данные передавайте через Django `json_script`, не через HTML интерполяцию JS.

`src/api/client.ts` разрешает только same-origin запросы, использует сессию
и X-CSRFToken для изменяющих запросов. Шаблон должен содержать meta csrf-token
с Django csrf_token. API самостоятельно проверяет роли и разрешения.
Не передавайте секреты в VITE_*: эти переменные доступны браузеру.

## CI/CD и проверки

CI устанавливает Node 22, выполняет npm ci, typecheck/build, production
collectstatic и тесты react_frontend до существующих проверок.
Docker использует отдельный Node build stage, копирует результат перед
collectstatic; Node не нужен в Python runtime. Существующий deploy job и
его условие main не изменены. Эта задача не запускает деплой.

```sh
python manage.py check
python manage.py test react_frontend
```

Тесты требуют предварительной frontend сборки и тестовой БД.

Схема manifest следует официальной документации Vite:
https://vite.dev/guide/backend-integration
