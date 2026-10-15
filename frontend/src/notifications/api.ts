import type { Achievement, Metal, Tier } from '../achievements/types';
import { isPublicId } from '../achievements/api';
import { metalLabels } from '../achievements/types';

export interface NotificationConfig { userId: number; feedUrl: string; claimUrl: string; ackUrl: string; trophyRoomUrl: string; csrfToken: string }
export interface Notification { eventId: number; action: 'grant' | 'upgrade'; publicId: string; title: string; secret: boolean; fromTier: Tier | null; toTier: Tier; recordedAt: string; artKey: string; read: boolean }
export interface Feed { items: Notification[]; unread: number }
export class NotificationError extends Error { constructor(public status: number, message: string) { super(message); } }
const invalid = (): never => { throw new NotificationError(0, 'Не удалось прочитать уведомления.'); };
const obj = (v: unknown): Record<string, unknown> => v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, unknown> : invalid();
const str = (v: unknown) => typeof v === 'string' ? v : invalid();
const number = (v: unknown) => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0 ? v : invalid();
const bool = (v: unknown) => typeof v === 'boolean' ? v : invalid();
function tier(value: unknown): Tier {
  const t = obj(value), code = str(t.code), rank = number(t.rank), rarity = str(t.rarity);
  if (!rank || !Object.hasOwn(metalLabels, rarity)) invalid();
  return { code, rank, rarity: rarity as Metal };
}
export function parseNotification(value: unknown): Notification {
  const n = obj(value), eventId = number(n.event_id), publicId = str(n.public_id), recordedAt = str(n.recorded_at);
  const toTier = tier(n.to_tier), fromTier = n.from_tier === null ? null : tier(n.from_tier);
  if (!eventId || !isPublicId(publicId) || !Number.isFinite(Date.parse(recordedAt)) ||
      !['grant', 'upgrade'].includes(str(n.action)) || (n.action === 'grant' ? fromTier !== null : !fromTier || fromTier.rank >= toTier.rank)) invalid();
  const key = str(n.art_key);
  return { eventId, publicId, recordedAt, action: n.action as Notification['action'], title: str(n.title), secret: bool(n.secret),
    fromTier, toTier, artKey: ['generic','training','sandbox','quality','speed','probation','milestone','independent'].includes(key) ? key : 'generic', read: bool(n.read) };
}
export function parseFeed(value: unknown): Feed {
  const f = obj(value), values = f.items; if (!Array.isArray(values)) return invalid();
  const items = values.map(parseNotification);
  if (new Set(items.map(n => n.eventId)).size !== items.length || items.some(n => n.read)) invalid();
  return { items, unread: number(f.unread_count) };
}
export function asAchievement(n: Notification): Achievement {
  return { id: n.publicId, title: n.title, description: null, status: 'earned', secret: n.secret, revealed: true,
    applicable: true, highestTier: n.toTier, supportedTiers: [n.toTier], revision: 0, earnedAt: n.recordedAt,
    lastUpgradedAt: n.action === 'upgrade' ? n.recordedAt : null, category: null, artKey: n.artKey,
    progress: null, manualGrant: false, dataQuality: 'verified' };
}
function safe(path: string): string {
  if (!/^\/api\/achievements\/me\/notifications\/(?:[1-9]\d*\/(?:claim|ack)\/)?$/.test(path)) invalid();
  return path;
}
export function eventUrl(template: string, id: number): string { if (!Number.isSafeInteger(id) || id < 1) invalid(); return safe(template.replace('{event_id}', String(id))); }
export function safeRoomUrl(path: string): string { if (!path.startsWith('/') || path.startsWith('//') || /[\\\s?#]/.test(path)) invalid(); return path; }
async function request(url: string, csrf: string, signal: AbortSignal, claimToken?: string): Promise<unknown> {
  const controller = new AbortController(), abort = () => controller.abort(); signal.addEventListener('abort', abort, { once: true }); if (signal.aborted) abort();
  const timer = setTimeout(abort, 15000);
  try {
    let response: Response;
    try { response = await fetch(safe(url), { signal: controller.signal, credentials: 'same-origin', cache: 'no-store',
      method: claimToken ? 'POST' : 'GET', headers: { Accept: 'application/json', ...(claimToken ? { 'Content-Type': 'application/json', 'X-CSRFToken': csrf } : {}) },
      ...(claimToken ? { body: JSON.stringify({ claim_token: claimToken }) } : {}) }); }
    catch (error) { if (signal.aborted) throw error; throw new NotificationError(0, 'Нет связи с сервером. Уведомление не отмечено просмотренным.'); }
    if (!response.ok) throw new NotificationError(response.status, response.status === 401 || response.status === 403
      ? 'Сессия недоступна. Войдите снова и повторите проверку.' : response.status === 409 ? 'Уведомление уже открыто в другой вкладке. Проверим состояние снова.' : 'Не удалось подтвердить просмотр. Повторите действие.');
    try { return await response.json(); } catch { return invalid(); }
  } finally { clearTimeout(timer); signal.removeEventListener('abort', abort); }
}
export function createApi(config: NotificationConfig) {
  return {
    feed: async (signal: AbortSignal) => parseFeed(await request(config.feedUrl, '', signal)),
    claim: async (id: number, claimToken: string, signal: AbortSignal) => {
      const r = obj(await request(eventUrl(config.claimUrl, id), config.csrfToken, signal, claimToken));
      if (number(r.event_id ?? obj(r.notification).event_id) !== id) invalid();
      if (bool(r.read)) return null;
      if (str(r.claim_token) !== claimToken) invalid();
      const notification = parseNotification(r.notification); if (notification.read) invalid(); return notification;
    },
    ack: async (id: number, claimToken: string, signal: AbortSignal) => {
      const r = obj(await request(eventUrl(config.ackUrl, id), config.csrfToken, signal, claimToken));
      if (number(r.event_id) !== id || r.read !== true || !Number.isFinite(Date.parse(str(r.read_at)))) invalid();
    },
  };
}
export type NotificationApi = ReturnType<typeof createApi>;
