import type { ApiStage, Journey, StageId } from './apiTypes';
export type StageStatus = 'completed' | 'current' | 'in_progress' | 'available' | 'locked' | 'coming_soon' | 'not_required';
export type Side = 'right' | 'left' | 'top' | 'bottom';
export type StageArt = 'TrainingArt' | 'SandboxArt' | 'EscalationArt' | 'AuditArt' | 'SupervisedArt' | 'OptionalArt' | 'AutonomousArt' | 'FinalArt';
export interface StationGeometry {
  id: StageId; order: number; preferredSide: Side; position: { x: number; y: number }; art: StageArt;
}
export interface Stage extends StationGeometry { data: ApiStage }
export interface RoadmapProps {
  displayName: string; role: string; canDemo: boolean; actionExternalHosts: readonly string[];
  sandboxUrl: string; achievementsUrl: string; roadmapApiUrl: string; loginUrl: string;
}
/** Presentation only: preserve server status; distinguish the current location from ongoing probation. */
export function stageStatus(stage: Stage, journey: Journey | null): StageStatus {
  const data = stage.data;
  if (data.availability === 'coming_soon') return 'coming_soon';
  if (data.display_status === 'not_required') return 'not_required';
  if (data.state !== 'in_progress') return data.state ?? 'locked';
  const slug = journey?.current_stage?.slug;
  const currentIds: Record<string, StageId> = {
    'training-program': 'training', 'sandbox-candidate': 'sandbox',
    'with-review': 'with_review', 'optional-review': 'optional_review', 'no-review': 'no_review', done: 'probation',
  };
  const currentId = slug ? currentIds[slug] : undefined;
  return (!journey || currentId === stage.id || (!currentId && stage.id === 'training')) ? 'current' : 'in_progress';
}
export const statusLabels: Record<StageStatus, string> = {
  completed: 'Завершён ✓', current: 'Текущий', in_progress: 'В процессе', available: 'Доступен',
  locked: 'Заблокирован', coming_soon: 'COMING SOON', not_required: 'Не требуется',
};
