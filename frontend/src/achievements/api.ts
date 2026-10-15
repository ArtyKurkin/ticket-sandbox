import type { Achievement, AchievementEvent, Metal, Tier, TrophyCollection, TrophyDetail } from './types';
import { metalLabels } from './types';

export type ErrorKind = 'unauthorized' | 'forbidden' | 'not_found' | 'server' | 'network' | 'contract';
export class TrophyError extends Error { constructor(public kind: ErrorKind, message: string) { super(message); } }
const bad = (): never => { throw new TrophyError('contract', 'Не удалось прочитать достижения. Повторите загрузку.'); };
const record = (v: unknown): Record<string, unknown> => v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, unknown> : bad();
const str = (v: unknown): string => typeof v === 'string' ? v : bad();
const bool = (v: unknown): boolean => typeof v === 'boolean' ? v : bad();
const count = (v: unknown): number => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0 ? v : bad();
const nullableString = (v: unknown): string | null => v === null ? null : str(v);
const date = (v: unknown): string | null => v === null ? null : typeof v === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(v) && Number.isFinite(Date.parse(v)) ? v : bad();
const list = (v: unknown): unknown[] => Array.isArray(v) ? v : bad();
const metal = (v: unknown): Metal => typeof v === 'string' && Object.hasOwn(metalLabels, v) ? v as Metal : bad();
export const isPublicId = (v: string): boolean => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
function tier(v: unknown, supported = false): Tier {
  const t = record(v);
  const result = { code: str(t.code), rank: count(t.rank), rarity: metal(t.rarity) };
  if (!result.rank) bad();
  return supported ? { ...result, criterion: str(t.criterion), automatic: bool(t.automatic) } : result;
}
export function parseAchievement(value: unknown): Achievement {
  const a = record(value);
  const id = str(a.public_id);
  if (!isPublicId(id)) bad();
  if (!['earned', 'locked', 'revoked'].includes(str(a.status))) bad();
  const status = a.status as Achievement['status'];
  const secret = bool(a.secret), revealed = bool(a.revealed);
  const applicable = a.applicable === null ? null : bool(a.applicable);
  const highestTier = a.highest_tier === null ? null : tier(a.highest_tier);
  if ((status === 'earned') !== (highestTier !== null) || (secret && revealed !== (status === 'earned'))) bad();
  const base = { id, status, secret, revealed, applicable, highestTier,
    revision: count(a.revision), earnedAt: date(a.earned_at), lastUpgradedAt: date(a.last_upgraded_at) };
  if (secret && !revealed) {
    return { ...base, title: 'Секретное достижение', description: null, supportedTiers: [], category: null,
      artKey: 'generic', progress: null, manualGrant: false, dataQuality: 'not_evaluated' };
  }
  const supportedTiers = list(a.supported_tiers).map(t => tier(t, true));
  if (new Set(supportedTiers.map(t => t.code)).size !== supportedTiers.length) bad();
  if (highestTier && !supportedTiers.some(t => t.code === highestTier.code && t.rarity === highestTier.rarity && t.rank === highestTier.rank)) bad();
  let progress = null;
  if (a.progress !== null) {
    const p = record(a.progress);
    if (typeof p.percent !== 'number' || !Number.isFinite(p.percent) || p.percent < 0 || p.percent > 100) bad();
    progress = { percent: p.percent as number, label: str(p.label), ...(p.summary === undefined ? {} : { summary: str(p.summary) }) };
  }
  return { ...base, title: str(a.title), description: nullableString(a.description),
    supportedTiers, category: str(a.category), artKey: str(a.art_key), progress,
    manualGrant: bool(a.manual), dataQuality: str(a.data_quality) };
}
export function parseCollection(value: unknown): TrophyCollection {
  const c = record(value), stats = record(c.stats), rarities = record(stats.rarities);
  const items = list(c.items).map(parseAchievement);
  if (new Set(items.map(a => a.id)).size !== items.length) bad();
  return { items, pendingEvents: count(c.pending_source_events), stats: {
    earned: count(stats.earned), applicable_total: count(stats.applicable_total),
    rarities: { bronze: count(rarities.bronze), silver: count(rarities.silver), gold: count(rarities.gold), platinum: count(rarities.platinum) },
  } };
}
export function parseDetail(value: unknown): TrophyDetail {
  const d = record(value), achievement = parseAchievement(d.achievement);
  const history = list(d.history).map(value => {
    const e = record(value);
    if (!['grant', 'upgrade', 'revoke', 'evidence_disputed'].includes(str(e.action))) bad();
    const occurred = date(e.occurred_at), recorded = date(e.recorded_at);
    if (!occurred || !recorded || count(e.id) === 0) bad();
    return { id: count(e.id), action: e.action as AchievementEvent['action'],
      from_tier: nullableString(e.from_tier), to_tier: nullableString(e.to_tier),
      occurred_at: occurred!, recorded_at: recorded!, source: str(e.source), manual: bool(e.manual),
      actor_id: e.actor_id === null ? null : count(e.actor_id), reason: str(e.reason), rule_version: count(e.rule_version) };
  });
  if (new Set(history.map(e => e.id)).size !== history.length) bad();
  if (achievement.secret && !achievement.revealed && history.length) bad();
  const nextCursor = d.next_cursor === null ? null : count(d.next_cursor);
  if (nextCursor !== null && (nextCursor === 0 || !history.length || nextCursor !== history[history.length - 1].id)) bad();
  return { achievement, history, nextCursor };
}
export function mergeHistory(previous: readonly AchievementEvent[], incoming: readonly AchievementEvent[]): AchievementEvent[] {
  return [...new Map([...previous, ...incoming].map(e => [e.id, e])).values()].sort((a, b) => a.id - b.id);
}
function safeEndpoint(path: string): string {
  if (!/^\/api\/achievements\/me\/(?:[0-9a-f-]{36}\/)?(?:\?cursor=\d+)?$/i.test(path)) bad();
  return path;
}
async function read(path: string, signal: AbortSignal): Promise<unknown> {
  let response: Response;
  try { response = await fetch(safeEndpoint(path), { method: 'GET', credentials: 'same-origin', cache: 'no-store', signal, headers: { Accept: 'application/json' } }); }
  catch (error) {
    if ((error as Error).name === 'AbortError' || error instanceof TrophyError) throw error;
    throw new TrophyError('network', 'Нет связи с сервером. Повторите загрузку.');
  }
  if (!response.ok) {
    const kinds: Record<number, ErrorKind> = { 401: 'unauthorized', 403: 'forbidden', 404: 'not_found' };
    const messages: Record<number, string> = { 401: 'Сессия завершилась. Войдите снова.', 403: 'Нет доступа к достижениям.', 404: 'Это достижение больше недоступно.' };
    throw new TrophyError(kinds[response.status] ?? 'server', messages[response.status] ?? 'Достижения временно недоступны. Повторите загрузку.');
  }
  try { return await response.json(); } catch { return bad(); }
}
export async function loadCollection(url: string, signal: AbortSignal): Promise<TrophyCollection> { return parseCollection(await read(url, signal)); }
export async function loadDetail(url: string, id: string, cursor: number | null, signal: AbortSignal): Promise<TrophyDetail> {
  if (!isPublicId(id) || (cursor !== null && (!Number.isSafeInteger(cursor) || cursor <= 0))) bad();
  const detail = parseDetail(await read(`${url}${id}/${cursor === null ? '' : `?cursor=${cursor}`}`, signal));
  if (detail.achievement.id !== id || (cursor !== null && detail.nextCursor !== null && detail.nextCursor <= cursor)) bad();
  return detail;
}
