export type StageStatus = 'completed' | 'current' | 'locked';
export type Side = 'right' | 'left' | 'top' | 'bottom';
export type StageArt = 'TrainingArt' | 'SandboxArt' | 'EscalationArt' | 'AuditArt' | 'SupervisedArt' | 'OptionalArt' | 'AutonomousArt' | 'FinalArt';
export interface Stage {
  id: string; order: number; title: string; description: string;
  metricLabel: string; initialPercent: number; actionLabel: string; condition: string;
  preferredSide: Side; position: { x: number; y: number }; art: StageArt;
}
export interface RoadmapProps {
  displayName: string; role: string; canDemo: boolean;
  sandboxUrl: string; achievementsUrl: string;
  initialProgress: { completed: number; trophyCount: number };
}
export function stageStatus(stage: Stage, completed: number): StageStatus {
  return stage.order <= completed ? 'completed' : stage.order === completed + 1 ? 'current' : 'locked';
}
export const statusLabels: Record<StageStatus, string> = {
  completed: 'Завершён ✓', current: 'Текущий', locked: 'Заблокирован',
};
