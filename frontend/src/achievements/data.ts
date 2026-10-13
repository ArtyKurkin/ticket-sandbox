import type { Achievement } from "./types";

// Temporary Google Stitch fixture. No backend persistence.
export const demoAchievements: readonly Achievement[] = [
  {
    "id": "1",
    "title": "Старт миссии",
    "description": "Успешный старт программы онбординга: архитектура облачных дата-центров, сетевые стандарты и регламенты первой линии поддержки Timeweb Cloud.",
    "metal": "bronze",
    "status": "earned",
    "progress": {
      "percent": 100,
      "label": "12 / 12 уроков (100%)"
    },
    "condition": "Завершите Этап 01: «Программа обучения»",
    "earnedAt": "24.10.2024",
    "secret": false,
    "manualGrant": false,
    "mentorComment": null,
    "art": "MissionArt"
  },
  {
    "id": "2",
    "title": "Архитектор",
    "description": "Успешное проектирование отказоустойчивой архитектуры распределённых кластеров и мастерство развёртывания балансировщиков нагрузки.",
    "metal": "silver",
    "status": "earned",
    "progress": {
      "percent": 100,
      "label": "Подтверждено наставником (100%)"
    },
    "condition": "Сдайте практический кейс по архитектуре облака",
    "earnedAt": "28.10.2024",
    "secret": false,
    "manualGrant": true,
    "mentorComment": {
      "text": "«Превосходная работа с топологией сети и изоляцией контуров: стажёр безупречно собрал тестовый стенд с нулевым downtime.»",
      "author": "Артём Горбунов (Senior L2 Engineer)"
    },
    "art": "ArchitectureArt"
  },
  {
    "id": "3",
    "title": "Чистый код",
    "description": "Создание эталонных скриптов автоматизации развёртывания инфраструктуры (Terraform / Ansible) без замечаний ревьюера.",
    "metal": "gold",
    "status": "locked",
    "progress": {
      "summary": "Прогресс 75%",
      "percent": 75,
      "label": "3 из 4 модулей (75%)"
    },
    "condition": "Пройти 4 модуля автоматизации с QA Score 100%",
    "earnedAt": null,
    "secret": false,
    "manualGrant": false,
    "mentorComment": null,
    "art": "AutomationArt"
  },
  {
    "id": "4",
    "title": "Первый рубеж",
    "description": "Успешное разрешение первого критического инцидента в симуляторе Ticket Sandbox с подтверждением валидатора тестов.",
    "metal": "bronze",
    "status": "earned",
    "progress": {
      "percent": 100,
      "label": "15 из 15 тикетов (100%)"
    },
    "condition": "Закройте 15 тикетов в симуляторе Sandbox",
    "earnedAt": "01.11.2024",
    "secret": false,
    "manualGrant": false,
    "mentorComment": null,
    "art": "MilestoneArt"
  },
  {
    "id": "5",
    "title": "Синхронизация",
    "description": "Настройка репликации баз данных PostgreSQL / MySQL без задержек транзакций в условиях пиковой эмуляции трафика.",
    "metal": "silver",
    "status": "locked",
    "progress": {
      "summary": "В процессе",
      "percent": 30,
      "label": "В процессе проверки наставником"
    },
    "condition": "Синхронизируйте кластер при нагрузке 10 000 RPS",
    "earnedAt": null,
    "secret": false,
    "manualGrant": true,
    "mentorComment": null,
    "art": "SyncArt"
  },
  {
    "id": "6",
    "title": "Страж ядра",
    "description": "Отражение симулированной DDoS-атаки L7 и оперативная настройка правил WAF с нулевой потерей легитимных клиентских запросов.",
    "metal": "gold",
    "status": "earned",
    "progress": {
      "percent": 100,
      "label": "Успешно защищено (100%)"
    },
    "condition": "Защитите ядро сервиса от 3 типов атак",
    "earnedAt": "05.11.2024",
    "secret": false,
    "manualGrant": true,
    "mentorComment": {
      "text": "«Быстрая реакция на аномалии в логах Nginx и грамотная фильтрация вредоносных паттернов спасли инфраструктуру.»",
      "author": "Михаил Ильин (Lead DevOps Architect)"
    },
    "art": "GuardianArt"
  },
  {
    "id": "7",
    "title": "Гроссмейстер",
    "description": "Финальная аттестация: успешное окончание испытательного срока, сдача грейда L1 и сбор всех ключевых наград онбординга Timeweb Cloud.",
    "metal": "platinum",
    "status": "locked",
    "progress": {
      "summary": "Финальный трофей",
      "percent": 62.5,
      "label": "5 из 8 этапов завершено (62%)"
    },
    "condition": "Пройдите все 8 этапов программы стажировки",
    "earnedAt": null,
    "secret": false,
    "manualGrant": false,
    "mentorComment": null,
    "art": "MasterArt"
  },
  {
    "id": "8",
    "title": "Секретный протокол",
    "description": "Это достижение скрыто. Условие станет известно только после его фактического выполнения в учебной консоли.",
    "metal": "bronze",
    "status": "locked",
    "progress": {
      "percent": 0,
      "label": "???"
    },
    "condition": "Условие засекречено",
    "earnedAt": null,
    "secret": true,
    "manualGrant": false,
    "mentorComment": null,
    "art": "SecretProtocolArt"
  },
  {
    "id": "9",
    "title": "Теневой рубеж",
    "description": "Это достижение скрыто. Условие станет известно только после его фактического выполнения в боевом дежурстве.",
    "metal": "silver",
    "status": "locked",
    "progress": {
      "percent": 0,
      "label": "???"
    },
    "condition": "Условие засекречено",
    "earnedAt": null,
    "secret": true,
    "manualGrant": false,
    "mentorComment": null,
    "art": "SecretFrontierArt"
  }
];

export const demoUnlock = { achievementId: "3", progressLabel: "4 из 4 модулей (100%)", description: "Золотая награда за эталонную автоматизацию" };
