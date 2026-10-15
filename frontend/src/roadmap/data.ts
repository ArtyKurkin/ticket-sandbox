import type { StationGeometry } from './types';

// Approved map geometry and illustrations; learning data comes from Django.
export const stations: readonly StationGeometry[] = [
  {
    "id": "training",
    "order": 1,
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
    "preferredSide": "bottom",
    "position": {
      "x": 600,
      "y": 154
    },
    "art": "EscalationArt"
  },
  {
    "id": "ticket_analysis",
    "order": 4,
    "preferredSide": "left",
    "position": {
      "x": 888,
      "y": 210
    },
    "art": "AuditArt"
  },
  {
    "id": "with_review",
    "order": 5,
    "preferredSide": "left",
    "position": {
      "x": 1002,
      "y": 350
    },
    "art": "SupervisedArt"
  },
  {
    "id": "optional_review",
    "order": 6,
    "preferredSide": "top",
    "position": {
      "x": 816,
      "y": 490
    },
    "art": "OptionalArt"
  },
  {
    "id": "no_review",
    "order": 7,
    "preferredSide": "top",
    "position": {
      "x": 528,
      "y": 532
    },
    "art": "AutonomousArt"
  },
  {
    "id": "probation",
    "order": 8,
    "preferredSide": "right",
    "position": {
      "x": 216,
      "y": 546
    },
    "art": "FinalArt"
  }
];

export const demoProgressOptions = [1, 3, 6, 8] as const;
