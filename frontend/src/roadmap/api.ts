import { stageIds, type RoadmapResponse } from './apiTypes';

export class RoadmapError extends Error {
  constructor(public readonly kind: 'network' | 'server' | 'unauthorized' | 'forbidden' | 'not_found' | 'contract', message: string) {
    super(message);
  }
}
const fail = (): never => { throw new RoadmapError('contract', 'Ответ Roadmap имеет неподдерживаемый формат.'); };
function record(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return fail();
  return value as Record<string, unknown>;
}
const string = (v: unknown) => typeof v === 'string' || fail();
const boolean = (v: unknown) => typeof v === 'boolean' || fail();
const number = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) && v >= 0) || fail();
const integer = (v: unknown) => (number(v) && Number.isInteger(v)) || fail();
const nullable = (v: unknown, check: (v: unknown) => unknown) => v === null || check(v);
const oneOf = (v: unknown, options: readonly unknown[]) => options.includes(v) || fail();
function array(v: unknown, check: (v: unknown) => unknown) {
  if (!Array.isArray(v)) return fail();
  v.forEach(check);
}
const optional = (r: Record<string, unknown>, key: string, check: (v: unknown) => unknown) => r[key] === undefined || check(r[key]);
const journeyStates = ['not_started', 'active', 'success', 'terminated', 'insufficient_data'];
const states = ['locked', 'available', 'in_progress', 'completed'];
const percentage = (v: unknown) => (number(v) && (v as number) <= 100) || fail();
const date = (v: unknown) => (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}(?:T.*)?$/.test(v) && Number.isFinite(Date.parse(v))) || fail();
function quality(value: unknown) {
  const r = record(value); string(r.code);
  optional(r, 'description', string); optional(r, 'stage', v => oneOf(v, stageIds));
  for (const key of ['attempt_id', 'user_id', 'task_id']) optional(r, key, integer);
}
export function safeActionUrl(value: string, external = false, allowedExternalHosts: readonly string[] = []): boolean {
  if (/[\u0000-\u0020\u007f\\]/.test(value)) return false;
  try {
    const url = new URL(value, 'https://roadmap.invalid');
    if (external) return /^https:\/\//i.test(value) && url.protocol === 'https:' && !url.username && !url.password && !url.port && allowedExternalHosts.includes(url.hostname.toLowerCase());
    return value.startsWith('/') && !value.startsWith('//') && url.origin === 'https://roadmap.invalid';
  } catch { return false; }
}

/** Validate the actual v1 payload before trusting it. Geometry never comes from JSON. */
export function parseRoadmap(value: unknown, allowedExternalHosts: readonly string[] = []): RoadmapResponse {
  const r = record(value);
  oneOf(r.schema_version, [1]); integer(r.requirements_version);
  const journey = record(r.journey);
  nullable(journey.id, integer); oneOf(journey.state, journeyStates);
  nullable(journey.entry_type, v => oneOf(v, ['new_hire', 'internal_transfer']));
  nullable(journey.scheme, v => oneOf(v, ['legacy', 'unified']));
  optional(journey, 'current_stage', v => { const s = record(v); integer(s.id); string(s.slug); string(s.title); date(s.started_at); });
  optional(journey, 'probation_outcome', v => oneOf(v, journeyStates));
  optional(journey, 'completed_at', v => nullable(v, date));
  optional(journey, 'fixed_quality_percent', v => nullable(v, percentage));
  optional(journey, 'metrics', v => array(v, item => {
    const m = record(item); integer(m.week_number); nullable(m.week_start_date, date);
    nullable(m.quality_percent, percentage);
    nullable(m.speed_tickets_per_hour, v => (typeof v === 'string' && /^\d+(?:\.\d+)?$/.test(v)) || fail());
  }));
  if (journey.state === 'not_started') {
    if (journey.id !== null || journey.entry_type !== null || journey.scheme !== null) fail();
  } else if (journey.id === null || journey.entry_type === null || journey.scheme === null || !journey.current_stage) fail();
  const overall = record(r.overall);
  for (const key of ['completed_count', 'applicable_count', 'exempt_count']) integer(overall[key]);
  percentage(overall.percent); nullable(overall.adaptation_progress_percent, percentage);
  if ((overall.completed_count as number) > (overall.applicable_count as number)) fail();
  array(r.data_quality, quality);
  const ids = new Set<unknown>();
  array(r.stages, value => {
    const s = record(value); oneOf(s.id, stageIds);
    if (ids.has(s.id)) fail(); ids.add(s.id);
    if (s.order !== stageIds.indexOf(s.id as typeof stageIds[number]) + 1) fail();
    string(s.title); string(s.description); string(s.source);
    oneOf(s.availability, ['enabled', 'coming_soon']); boolean(s.applicable);
    nullable(s.state, v => oneOf(v, states)); oneOf(s.display_status, [...states, 'coming_soon', 'not_required']);
    optional(s, 'badge', string);
    const actionCodes = new Set<unknown>();
    array(s.actions, value => {
      const a = record(value); string(a.code); string(a.label); boolean(a.enabled); boolean(a.external);
      oneOf(a.kind, ['learning', 'view']); optional(a, 'reason', string);
      if (actionCodes.has(a.code)) fail(); actionCodes.add(a.code);
      if (a.url === null) { if (a.enabled) fail(); }
      else if (typeof a.url !== 'string' || !safeActionUrl(a.url, a.external as boolean, allowedExternalHosts)) fail();
      if (!a.enabled && (typeof a.reason !== 'string' || !a.reason)) fail();
    });
    optional(s, 'action_notice', string);
    if (s.availability === 'coming_soon' && (s.state !== null || s.display_status !== 'coming_soon' || (s.actions as unknown[]).length)) fail();
    if (!s.applicable && s.state !== null) fail();
    if (s.applicable && s.availability === 'enabled' && (s.state === null || s.display_status !== s.state)) fail();
    optional(s, 'progress', value => { const p = record(value); integer(p.completed); integer(p.total); if ((p.completed as number) > (p.total as number)) fail(); oneOf(p.unit, ['tasks']); oneOf(p.basis, ['technical']); oneOf(p.scope, ['current_catalog']); });
    optional(s, 'completion', value => { const c = record(value); nullable(c.id, integer); nullable(c.completed_at, date); integer(c.total); array(c.task_ids, integer); });
    optional(s, 'notifications', value => array(value, value => { const n = record(value); string(n.code); integer(n.count); boolean(n.blocking); }));
    optional(s, 'data_quality', value => array(value, quality));
    optional(s, 'periods', value => array(value, value => { const p = record(value); integer(p.history_id); date(p.started_at); nullable(p.ended_at, date); integer(p.duration_days); }));
    optional(s, 'readiness', value => { const ready = record(value); oneOf(ready.state, ['ready', 'almost_ready', 'not_ready', 'completed']); string(ready.label); nullable(ready.next_stage_id, integer); array(ready.reasons, value => { const reason = record(value); string(reason.code); string(reason.label); string(reason.description); }); });
    optional(s, 'evidence', value => {
      const e = record(value);
      if ('event_id' in e) { nullable(e.event_id, integer); nullable(e.action, v => oneOf(v, ['confirmed', 'revoked'])); nullable(e.recorded_at, date); nullable(e.actor_id, integer); }
      else if ('completed' in e) { boolean(e.completed); string(e.code); nullable(e.transition_id, integer); }
      else oneOf(e.outcome, journeyStates);
    });
  });
  if (ids.size !== stageIds.length) fail();
  return r as unknown as RoadmapResponse;
}

export async function loadRoadmap(url: string, signal: AbortSignal, allowedExternalHosts: readonly string[] = []): Promise<RoadmapResponse> {
  let response: Response;
  try { response = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal, cache: 'no-store' }); }
  catch (error) { if (signal.aborted) throw error; throw new RoadmapError('network', 'Не удалось загрузить Roadmap. Проверьте соединение и повторите попытку.'); }
  if (response.status === 401 || response.redirected) throw new RoadmapError('unauthorized', 'Сессия завершена. Войдите снова.');
  if (response.status === 403) throw new RoadmapError('forbidden', 'Нет доступа к этой адаптации.');
  if (response.status === 404) throw new RoadmapError('not_found', 'Адаптация не найдена.');
  if (!response.ok) throw new RoadmapError('server', 'Roadmap временно недоступен. Повторите попытку.');
  let payload: unknown;
  try { payload = await response.json(); } catch { throw new RoadmapError('contract', 'Сервер вернул некорректный ответ Roadmap.'); }
  return parseRoadmap(payload, allowedExternalHosts);
}
