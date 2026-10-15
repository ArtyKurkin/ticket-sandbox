import type { RefCallback } from 'react';
import type { Stage, StageStatus } from './types';
import { statusLabels } from './types';
import { TrainingArt } from './art/TrainingArt';
import { SandboxArt } from './art/SandboxArt';
import { EscalationArt } from './art/EscalationArt';
import { AuditArt } from './art/AuditArt';
import { SupervisedArt } from './art/SupervisedArt';
import { OptionalArt } from './art/OptionalArt';
import { AutonomousArt } from './art/AutonomousArt';
import { FinalArt } from './art/FinalArt';
const graphics = { TrainingArt, SandboxArt, EscalationArt, AuditArt, SupervisedArt, OptionalArt, AutonomousArt, FinalArt };

export function RoadmapStation({ stage, status, selected, onSelect, elementRef }: {
  stage: Stage; status: StageStatus; selected: boolean;
  onSelect: (stage: Stage) => void; elementRef: RefCallback<HTMLButtonElement>;
}) {
  const Art = graphics[stage.art];
  const final = stage.order === 8;
  const outcome = stage.data.evidence && 'outcome' in stage.data.evidence ? stage.data.evidence.outcome : null;
  const neutralFinal = final && (outcome === 'terminated' || outcome === 'insufficient_data');
  const label = outcome === 'terminated' ? 'ИС прекращён' : outcome === 'insufficient_data' ? 'Результат отсутствует' : statusLabels[status];
  return <button type="button" ref={elementRef} className={`rm-station rm-${status} ${final ? 'rm-final' : ''} ${selected ? 'rm-selected' : ''} ${neutralFinal ? 'rm-neutral-final' : ''}`}
    style={{ left: `${stage.position.x / 12}%`, top: `${stage.position.y / 7}%` }}
    aria-label={`Этап ${stage.order}: ${stage.data.title}. ${label}`}
    aria-expanded={selected} aria-controls={selected ? 'rm-stage-details' : undefined}
    data-stage={stage.id} data-status={status} onClick={() => onSelect(stage)}>
    <span className="rm-station-orbit"><span className="rm-radar" /><span className="rm-station-box"><Art />
      <span className="rm-stage-number">{String(stage.order).padStart(2, '0')}</span>
      {status === 'completed' && <span className="rm-stage-badge rm-check" aria-hidden="true">✓</span>}
      {status === 'locked' && !final && <span className="rm-stage-badge rm-lock" aria-hidden="true"><svg viewBox="0 0 20 20" fill="currentColor"><path d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z" /></svg></span>}
    </span></span>
    <span className="rm-station-label"><strong>{status === 'current' && <i aria-hidden="true" />}{stage.data.title}</strong>
      {status !== 'current' && <small>{final && status === 'locked' && !neutralFinal ? 'Финишная цель ✦' : label}</small>}
    </span>
  </button>;
}
