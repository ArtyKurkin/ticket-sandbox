/* Trusted staff client. No awarding rules or local achievement storage. */
export const metals = { bronze: 'Бронза', silver: 'Серебро', gold: 'Золото', platinum: 'Платина' };
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
export class AchievementApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}
const invalid = () => { throw new AchievementApiError(0, 'Не удалось прочитать ответ сервера.'); };
const object = v => v && typeof v === 'object' && !Array.isArray(v) ? v : invalid();
const string = v => typeof v === 'string' ? v : invalid();
const count = v => Number.isSafeInteger(v) && v >= 0 ? v : invalid();
const boolean = v => typeof v === 'boolean' ? v : invalid();
const date = v => v === null ? null : typeof v === 'string' && Number.isFinite(Date.parse(v)) ? v : invalid();
const metal = v => Object.hasOwn(metals, v) ? v : invalid();
function tier(v, supported = false) {
  const t = object(v); const result = { code: string(t.code), rank: count(t.rank), rarity: metal(t.rarity) };
  if (!result.rank) invalid();
  return supported ? { ...result, criterion: string(t.criterion), automatic: boolean(t.automatic) } : result;
}
export function parseItem(value) {
  const a = object(value);
  if (!uuid.test(string(a.public_id)) || !['earned', 'locked', 'revoked'].includes(a.status) || !Array.isArray(a.supported_tiers)) invalid();
  const tiers = a.supported_tiers.map(t => tier(t, true));
  const current = a.highest_tier === null ? null : tier(a.highest_tier);
  if ((a.status === 'earned') !== (current !== null) || new Set(tiers.map(t => t.code)).size !== tiers.length) invalid();
  if (current && !tiers.some(t => t.code === current.code && t.rank === current.rank && t.rarity === current.rarity)) invalid();
  return { ...a, public_id: a.public_id, title: string(a.title), description: a.description === null ? null : string(a.description),
    status: a.status, highest_tier: current, supported_tiers: tiers, revision: count(a.revision),
    applicable: a.applicable === null ? null : boolean(a.applicable), secret: boolean(a.secret), revealed: boolean(a.revealed),
    earned_at: date(a.earned_at), last_upgraded_at: date(a.last_upgraded_at), manual: boolean(a.manual),
    data_quality: string(a.data_quality), auto_grant_blocked: boolean(a.auto_grant_blocked) };
}
export function parseCatalogue(value) {
  const c = object(value); if (!Array.isArray(c.items)) invalid();
  const items = c.items.map(parseItem);
  if (new Set(items.map(a => a.public_id)).size !== items.length) invalid();
  return { items, earned: count(object(c.stats).earned), total: count(c.stats.applicable_total), pending: count(c.pending_source_events) };
}
export function parseDetail(value) {
  const d = object(value); if (!Array.isArray(d.history)) invalid();
  const history = d.history.map(v => {
    const e = object(v);
    if (!['grant', 'upgrade', 'revoke', 'evidence_disputed'].includes(e.action)) invalid();
    return { ...e, id: count(e.id), action: e.action, from_tier: e.from_tier === null ? null : string(e.from_tier),
      to_tier: e.to_tier === null ? null : string(e.to_tier), recorded_at: date(e.recorded_at), occurred_at: date(e.occurred_at),
      actor_name: e.actor_name === null ? null : string(e.actor_name), actor_id: e.actor_id === null ? null : count(e.actor_id),
      reason: string(e.reason), manual: boolean(e.manual) };
  });
  if (new Set(history.map(e => e.id)).size !== history.length) invalid();
  const next = d.next_cursor === null ? null : count(d.next_cursor);
  if (next !== null && (!history.length || next === 0 || next !== history.at(-1).id)) invalid();
  return { achievement: parseItem(d.achievement), history, next_cursor: next };
}
export function mergeEvents(before, after) { return [...new Map([...before, ...after].map(e => [e.id, e])).values()].sort((a, b) => a.id - b.id); }
export function higherTiers(a) { return a.supported_tiers.filter(t => t.rank > (a.highest_tier?.rank ?? 0)); }
export function eligibleDefinitions(items) { return items.filter(a => higherTiers(a).length); }
export function endpoint(template, id) {
  if (!uuid.test(id)) invalid();
  const path = template.replace('{public_id}', id);
  if (!/^\/api\/achievements\/users\/\d+\/(?:[a-f0-9-]{36}\/(?:grant\/|revoke\/)?)?(?:\?cursor=\d+)?$/i.test(path)) invalid();
  return path;
}
export async function request(url, { method = 'GET', body = null, csrf = '', signal = null } = {}) {
  if (!/^\/api\/achievements\/users\/\d+\/(?:[a-f0-9-]{36}\/(?:grant\/|revoke\/)?)?(?:\?cursor=\d+)?$/i.test(url)) invalid();
  const controller = new AbortController();
  const abort = () => controller.abort(); signal?.addEventListener('abort', abort, { once: true }); if (signal?.aborted) abort();
  const timeout = setTimeout(abort, 20000);
  try {
    let response;
    try {
      response = await fetch(url, { method, signal: controller.signal, credentials: 'same-origin', cache: 'no-store',
        headers: { Accept: 'application/json', ...(method === 'POST' ? { 'Content-Type': 'application/json', 'X-CSRFToken': csrf } : {}) },
        ...(body ? { body: JSON.stringify(body) } : {}) });
    } catch { throw new AchievementApiError(0, method === 'POST' ? 'Ответ не получен. Операция могла сохраниться; проверьте состояние или повторите ту же операцию.' : 'Нет связи с сервером. Повторите загрузку.'); }
    if (!response.ok) {
      const messages = { 400: 'Проверьте уровень и обязательную причину.', 401: 'Сессия завершилась. Войдите снова.',
        403: 'Нет прав или проверка CSRF не пройдена. Обновите страницу после входа.', 404: 'Сотрудник или награда больше недоступны.',
        409: 'Состояние награды изменилось. Проверьте обновлённые данные.' };
      throw new AchievementApiError(response.status, messages[response.status] ?? (method === 'POST' ? 'Сервер не подтвердил результат. Проверьте состояние операции.' : 'Достижения временно недоступны.'));
    }
    try { return await response.json(); } catch { return invalid(); }
  } finally { clearTimeout(timeout); signal?.removeEventListener('abort', abort); }
}
export class Operation {
  constructor(action, item, tierCode, reason, operationId) {
    if (!['grant', 'revoke'].includes(action) || !reason.trim() || reason.length > 10000 || !operationId) invalid();
    if (action === 'grant' && !higherTiers(item).some(t => t.code === tierCode)) invalid();
    if (action === 'revoke' && !item.highest_tier) invalid();
    this.action = action; this.id = item.public_id;
    this.body = Object.freeze({ reason: reason.trim(), operation_id: operationId, expected_revision: item.revision,
      ...(action === 'grant' ? { tier: tierCode } : {}) });
    this.inFlight = false;
  }
  async send(url, csrf) {
    if (this.inFlight) throw new AchievementApiError(0, 'Операция уже отправляется.');
    this.inFlight = true;
    try {
      const result = object(await request(url, { method: 'POST', body: this.body, csrf }));
      if (!['grant', 'upgrade', 'revoke', 'duplicate', 'no_op'].includes(result.action)) invalid();
      count(result.revision); if (result.event_id !== null) count(result.event_id);
      return result;
    } finally { this.inFlight = false; }
  }
}
export function formatDate(v) { return v ? new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(v)) : '—'; }
export function eventLabel(e) {
  const name = code => metals[code] ?? code ?? '—';
  return e.action === 'grant' ? `Получение: ${name(e.to_tier)}` : e.action === 'upgrade' ? `${name(e.from_tier)} → ${name(e.to_tier)}` : e.action === 'revoke' ? 'Отзыв награды' : 'Спорное доказательство';
}

export function historyReason(e) {
  return e.action === 'evidence_disputed' && !e.manual
    ? 'Данные, на основании которых выдана награда, изменились. Проверь результат и при необходимости отзови награду.'
    : e.reason;
}
export function detailDescription(a) {
  return a.description?.trim().toLocaleLowerCase('ru') === a.title.trim().toLocaleLowerCase('ru') ? null : a.description;
}
export const manualRegrantMessage = 'После отзыва награду можно выдать повторно только вручную.';
