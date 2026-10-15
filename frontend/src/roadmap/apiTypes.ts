export const stageIds = ['training', 'sandbox', 'escalation', 'ticket_analysis', 'with_review', 'optional_review', 'no_review', 'probation'] as const;
export type StageId = typeof stageIds[number];
export type ModuleAvailability = 'enabled' | 'coming_soon';
export type IndividualState = 'locked' | 'available' | 'in_progress' | 'completed';
export type DisplayStatus = IndividualState | 'coming_soon' | 'not_required';
export type JourneyState = 'not_started' | 'active' | 'success' | 'terminated' | 'insufficient_data';
export interface DataQuality {
  code: string; description?: string; stage?: StageId;
  attempt_id?: number; user_id?: number; task_id?: number;
}
export interface StageAction {
  code: string; label: string; url: string | null; enabled: boolean;
  kind: 'learning' | 'view'; external: boolean; reason?: string;
}
export interface StageProgress {
  completed: number; total: number; unit: 'tasks'; basis: 'technical'; scope: 'current_catalog';
}
export interface StageNotification { code: string; count: number; blocking: boolean }
export interface SandboxCompletion { id: number | null; completed_at: string | null; task_ids: number[]; total: number }
export interface StagePeriod { history_id: number; started_at: string; ended_at: string | null; duration_days: number }
export interface Readiness {
  state: 'ready' | 'almost_ready' | 'not_ready' | 'completed'; label: string;
  reasons: { code: string; label: string; description: string }[]; next_stage_id: number | null;
}
export type StageEvidence =
  | { event_id: number | null; action: 'confirmed' | 'revoked' | null; recorded_at: string | null; actor_id: number | null }
  | { completed: boolean; code: string; transition_id: number | null }
  | { outcome: JourneyState };
export interface ApiStage {
  id: StageId; order: number; title: string; availability: ModuleAvailability; applicable: boolean;
  state: IndividualState | null; display_status: DisplayStatus; source: string; description: string;
  actions: StageAction[]; action_notice?: string; badge?: string; progress?: StageProgress; completion?: SandboxCompletion;
  notifications?: StageNotification[]; data_quality?: DataQuality[]; evidence?: StageEvidence;
  periods?: StagePeriod[]; readiness?: Readiness;
}
export interface WeeklyMetric {
  week_number: number; week_start_date: string | null;
  speed_tickets_per_hour: string | null; quality_percent: number | null;
}
export interface Journey {
  id: number | null; state: JourneyState; entry_type: 'new_hire' | 'internal_transfer' | null;
  scheme: 'legacy' | 'unified' | null;
  current_stage?: { id: number; slug: string; title: string; started_at: string };
  probation_outcome?: JourneyState; completed_at?: string | null;
  metrics?: WeeklyMetric[]; fixed_quality_percent?: number | null;
}
export interface OverallProgress {
  completed_count: number; applicable_count: number; exempt_count: number;
  percent: number; adaptation_progress_percent: number | null;
}
export interface RoadmapResponse {
  schema_version: 1; requirements_version: number; journey: Journey;
  overall: OverallProgress; stages: ApiStage[]; data_quality: DataQuality[];
}
