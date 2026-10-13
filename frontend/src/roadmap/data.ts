import type { Stage } from "./types";

export const stages: readonly Stage[] = [
  {
    "id": "teachbase",
    "order": 1,
    "title": "Программа обучения",
    "description": "Базовый теоретический онбординг: архитектура облака, сетевые протоколы и регламенты поддержки.",
    "metricLabel": "12 из 12 уроков",
    "initialPercent": 100,
    "actionLabel": "Просмотреть материалы",
    "condition": "",
    "preferredSide": "right",
    "position": {
      "x": 156,
      "y": 189
    },
    "art": "TrainingArt"
  },
  {
    "id": "sandbox",
    "order": 2,
    "title": "Ticket Sandbox",
    "description": "Практические задания на изолированных виртуальных серверах с симуляцией обращений клиентов.",
    "metricLabel": "6 из 15 заданий",
    "initialPercent": 40,
    "actionLabel": "Продолжить выполнение",
    "condition": "",
    "preferredSide": "right",
    "position": {
      "x": 348,
      "y": 280
    },
    "art": "SandboxArt"
  },
  {
    "id": "escalation",
    "order": 3,
    "title": "Карта эскалаций",
    "description": "Маршрутизация обращений между L1, L2, L3 и NOC. Открывается после завершения Ticket Sandbox.",
    "metricLabel": "0 из 20 сценариев",
    "initialPercent": 0,
    "actionLabel": "Недоступно",
    "condition": "Завершите этап «Ticket Sandbox»",
    "preferredSide": "bottom",
    "position": {
      "x": 600,
      "y": 154
    },
    "art": "EscalationArt"
  },
  {
    "id": "audit",
    "order": 4,
    "title": "Анализ тикетов",
    "description": "Анализ закрытых обращений на предмет SLA и скрытых ошибок. Открывается после 3-го этапа.",
    "metricLabel": "0 из 10 кейсов",
    "initialPercent": 0,
    "actionLabel": "Недоступно",
    "condition": "Завершите этап «Карта эскалаций»",
    "preferredSide": "left",
    "position": {
      "x": 888,
      "y": 210
    },
    "art": "AuditArt"
  },
  {
    "id": "supervised",
    "order": 5,
    "title": "Тикеты с проверками",
    "description": "Боевая очередь реальных клиентов под наблюдением старшего наставника L2.",
    "metricLabel": "0 из 50 тикетов",
    "initialPercent": 0,
    "actionLabel": "Недоступно",
    "condition": "Завершите этап «Анализ тикетов»",
    "preferredSide": "left",
    "position": {
      "x": 1002,
      "y": 350
    },
    "art": "SupervisedArt"
  },
  {
    "id": "optionalReview",
    "order": 6,
    "title": "Проверки по желанию",
    "description": "Самостоятельная работа с тикетами с возможностью отправлять ответы наставнику на проверку.",
    "metricLabel": "0 из 40 тикетов",
    "initialPercent": 0,
    "actionLabel": "Недоступно",
    "condition": "Завершите этап «Тикеты с проверками»",
    "preferredSide": "top",
    "position": {
      "x": 816,
      "y": 490
    },
    "art": "OptionalArt"
  },
  {
    "id": "autonomous",
    "order": 7,
    "title": "Тикеты без проверок",
    "description": "Самостоятельное решение клиентских инцидентов с выборочным аудитом качества.",
    "metricLabel": "0 из 100 тикетов",
    "initialPercent": 0,
    "actionLabel": "Недоступно",
    "condition": "Завершите этап «Проверки по желанию»",
    "preferredSide": "top",
    "position": {
      "x": 528,
      "y": 532
    },
    "art": "AutonomousArt"
  },
  {
    "id": "final",
    "order": 8,
    "title": "Выход с ИС",
    "description": "Финальная аттестация, сдача квалификационных нормативов и перевод в штат инженеров.",
    "metricLabel": "Испытательный срок",
    "initialPercent": 0,
    "actionLabel": "Финальный рубеж",
    "condition": "Завершите все предшествующие 7 этапов",
    "preferredSide": "right",
    "position": {
      "x": 216,
      "y": 546
    },
    "art": "FinalArt"
  }
];

export const initialProgress = { completed: 1, trophyCount: 2 } as const;
export const demoProgressOptions = [1, 3, 6, 8] as const;
