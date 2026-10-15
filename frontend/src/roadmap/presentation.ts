import { stations } from './data';
import type { ApiStage, RoadmapResponse, StageAction, StageId } from './apiTypes';
import type { Stage } from './types';

export function mapStations(data: RoadmapResponse): Stage[] {
  const byId = new Map(data.stages.map(stage => [stage.id, stage]));
  return stations.map(station => {
    const stage = byId.get(station.id);
    if (!stage) throw new Error(`Missing station ${station.id}`);
    return { ...station, data: stage };
  });
}
export const formatPercent = (percent: number) => percent.toLocaleString('ru-RU', { maximumFractionDigits: 1 });
export const formatDate = (value: string) => new Date(value).toLocaleDateString('ru-RU');
export function canLaunch(stage: ApiStage, demonstration: boolean): boolean {
  return !demonstration && stage.availability === 'enabled' && stage.applicable && stage.state !== null && stage.state !== 'locked';
}
export function canOpenAction(stage: ApiStage, action: StageAction, demonstration: boolean): boolean {
  return !demonstration && stage.availability === 'enabled' && stage.applicable && action.enabled && action.url !== null
    && (action.kind === 'view' || canLaunch(stage, demonstration));
}

const active = (stage: ApiStage) => stage.availability === 'enabled' && stage.applicable && (stage.state === 'completed' || stage.state === 'in_progress');
/** Light only connections with actual active endpoints. Never infer intermediate completions. */
export function segmentLit(from: ApiStage, to: ApiStage): boolean { return active(from) && active(to); }
export function sectorAwake(stages: readonly Stage[], ids: readonly StageId[]): boolean {
  return stages.some(stage => ids.includes(stage.id) && active(stage.data));
}
const demoTitles = ['Программа обучения', 'Ticket Sandbox', 'Карта эскалаций', 'Анализ тикетов', 'Тикеты с проверками', 'Проверки по желанию', 'Тикеты без проверок', 'Выход с ИС'];
/** Separate visual fixture. Never mutate the fetched API response. No rewards or actions. */
export function demoStages(completed: number): Stage[] {
  return stations.map((station, index) => {
    const state = station.order <= completed ? 'completed' : station.order === completed + 1 ? 'in_progress' : 'locked';
    return { ...station, data: {
      id: station.id, order: station.order, title: demoTitles[index], description: 'Демонстрация визуальных эффектов. Данные обучения не изменяются.',
      availability: 'enabled', applicable: true, state, display_status: state, source: 'demo', actions: [],
    } };
  });
}
export const notificationLabels: Record<string, string> = {
  text_revision_required: 'Ответы требуют доработки', text_waiting_for_review: 'Ответы ожидают проверки',
  text_answer_not_submitted: 'Технически выполненные задания без отправленного ответа', unread_mentor_feedback: 'Непрочитанные комментарии наставника',
};
