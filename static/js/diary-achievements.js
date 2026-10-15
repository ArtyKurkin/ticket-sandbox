import { AchievementApiError, Operation, detailDescription, eligibleDefinitions, endpoint, eventLabel, formatDate, higherTiers, historyReason, manualRegrantMessage, mergeEvents, metals, parseCatalogue, parseDetail, request } from './diary-achievement-api.js';

const configNode = document.getElementById('diary-achievement-config');
const panel = document.getElementById('diary-achievement-panel');
if (configNode && panel) {
  const config = JSON.parse(configNode.textContent);
  if (config.canManage === true) initialise(config, panel);
}
function node(tag, text = '', className = '') { const n = document.createElement(tag); n.textContent = text; if (className) n.className = className; return n; }
function button(text, handler, className = 'button secondary') { const b = node('button', text, className); b.type = 'button'; b.addEventListener('click', handler); return b; }
function initialise(config, panel) {
  const q = selector => panel.querySelector(selector);
  const actionDialog = document.querySelector('[data-da-action]');
  const detailDialog = document.querySelector('[data-da-detail]');
  const form = actionDialog.querySelector('form');
  const aq = selector => actionDialog.querySelector(selector);
  const dq = selector => detailDialog.querySelector(selector);
  let items = [], loaded = false, loadController = null, detailController = null;
  let detail = null, detailId = null, draftAction = 'grant', draftItem = null, operation = null, busy = false, recovery = false;
  const returns = new WeakMap();
  const notice = (text, target = q('[data-da-notice]')) => { target.textContent = text; target.hidden = !text; };
  function close(dialog) {
    if (dialog === actionDialog && busy) return;
    if (dialog === detailDialog) detailController?.abort();
    dialog.close(); const previous = returns.get(dialog); if (previous?.isConnected) previous.focus();
  }
  function open(dialog) {
    returns.set(dialog, document.activeElement); dialog.showModal(); dialog.querySelector('button')?.focus();
  }
  for (const dialog of [actionDialog, detailDialog]) {
    dialog.querySelectorAll('[data-da-close]').forEach(b => b.addEventListener('click', () => close(dialog)));
    dialog.addEventListener('cancel', e => { e.preventDefault(); close(dialog); });
    dialog.addEventListener('click', e => { if (e.target === dialog) { const r = dialog.getBoundingClientRect(); if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) close(dialog); } });
    dialog.addEventListener('keydown', e => {
      if (e.key !== 'Tab') return;
      const controls = [...dialog.querySelectorAll('button:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href]')].filter(n => n.getClientRects().length);
      const first = controls[0], last = controls.at(-1);
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
    });
  }
  function stateError(error, target, retry) {
    target.replaceChildren(node('p', error.message ?? 'Не удалось загрузить достижения.'));
    if (error.status === 401) { const a = node('a', 'Войти'); a.href = config.loginUrl; target.append(a); }
    target.append(button('Повторить загрузку', retry));
  }
  function render() {
    const list = q('[data-da-list]'); list.replaceChildren();
    const shown = items.filter(a => q('[data-da-show-all]').checked || a.applicable !== false || a.status !== 'locked');
    for (const a of shown) {
      const row = node('div', '', 'da-row'); row.dataset.achievementId = a.public_id;
      const icon = node('span', a.highest_tier ? '✦' : '◇', `da-medal ${a.highest_tier ? `da-${a.highest_tier.rarity}` : ''}`); icon.setAttribute('aria-hidden', 'true');
      const text = node('div'); text.append(node('h3', a.title));
      const status = a.status === 'earned' ? `${a.manual ? 'Ручная выдача' : 'Автоматическая выдача'}` : a.status === 'revoked' ? 'Отозвана' : a.applicable === false ? 'Не требуется' : a.applicable === null ? 'Применимость уточняется' : 'Не получена';
      const statusLine = node('p', '', 'da-status-line');
      if (a.highest_tier) statusLine.append(node('span', metals[a.highest_tier.rarity], `da-level da-level-${a.highest_tier.rarity}`));
      statusLine.append(node('span', `${status}${a.secret ? ' · Секретная' : ''}`)); text.append(statusLine);
      if (a.earned_at) text.append(node('p', `Первая выдача: ${formatDate(a.earned_at)}${a.last_upgraded_at ? ` · Повышение: ${formatDate(a.last_upgraded_at)}` : ''}`));
      if (a.data_quality === 'disputed') text.append(node('p', 'Результат требует проверки. Уровень сохранён.', 'da-disputed'));
      if (a.auto_grant_blocked) text.append(node('p', manualRegrantMessage, 'da-warning'));
      const actions = node('div', '', 'da-actions'); actions.append(button('История', () => openDetail(a)));
      if (higherTiers(a).length) actions.append(button(a.highest_tier ? 'Повысить' : a.status === 'revoked' ? 'Выдать повторно' : 'Выдать', () => openAction('grant', a)));
      if (a.highest_tier) actions.append(button('Отозвать', () => openAction('revoke', a)));
      row.append(icon, text, actions); list.append(row);
    }
    if (!shown.length) list.append(node('p', 'Наград для выбранного отображения нет.'));
    q('[data-da-grant]').disabled = !eligibleDefinitions(items).length;
  }
  async function load() {
    loadController?.abort(); const controller = new AbortController(); loadController = controller;
    loaded = false; q('[data-da-state]').replaceChildren(node('p', 'Загружаем достижения…'));
    q('[data-da-list]').replaceChildren(); q('[data-da-grant]').disabled = true; q('[data-da-controls]').hidden = true;
    try {
      const data = parseCatalogue(await request(config.collectionUrl, { signal: controller.signal }));
      if (controller.signal.aborted) return false;
      items = data.items; loaded = true; q('[data-da-state]').replaceChildren(); q('[data-da-controls]').hidden = false;
      q('[data-da-summary]').textContent = `Получено: ${data.earned} · Применимых: ${data.total}`;
      if (data.pending) q('[data-da-state]').append(node('p', 'Некоторые результаты ещё обрабатываются.'));
      render(); return true;
    } catch (error) { if (!controller.signal.aborted) stateError(error, q('[data-da-state]'), () => void load()); return false; }
  }
  function selectTab(name, push = true) {
    document.getElementById('diary-adaptation-panel').hidden = name === 'achievements'; panel.hidden = name !== 'achievements';
    document.querySelectorAll('[data-diary-tab]').forEach(a => { if (a.dataset.diaryTab === name) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
    if (push) { const url = new URL(location.href); url.searchParams.set('tab', name); history.pushState(null, '', url); }
    if (name === 'achievements' && !loaded) void load();
  }
  document.querySelectorAll('[data-diary-tab]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); selectTab(a.dataset.diaryTab); }));
  window.addEventListener('popstate', () => selectTab(new URL(location.href).searchParams.get('tab') === 'achievements' ? 'achievements' : 'adaptation', false));
  q('[data-da-refresh]').addEventListener('click', () => void load()); q('[data-da-show-all]').addEventListener('change', render);
  q('[data-da-grant]').addEventListener('click', () => openAction('grant'));

  function renderDetail() {
    const a = detail.achievement; document.getElementById('da-detail-title').textContent = a.title;
    const content = dq('[data-da-detail-content]'); content.replaceChildren();
    const description = detailDescription(a); if (description) content.append(node('p', description));
    content.append(node('p', `Текущий уровень: ${a.highest_tier ? metals[a.highest_tier.rarity] : 'Не получен'}`));
    if (a.earned_at) content.append(node('p', `Первая выдача: ${formatDate(a.earned_at)}`));
    if (a.last_upgraded_at) content.append(node('p', `Последнее повышение: ${formatDate(a.last_upgraded_at)}`));
    if (a.auto_grant_blocked) content.append(node('p', manualRegrantMessage, 'da-warning'));
    if (a.data_quality === 'disputed') content.append(node('p', 'Данные для этой награды нужно проверить. Текущий уровень сохранён.', 'da-disputed'));
    const events = dq('[data-da-history]'); events.replaceChildren();
    for (const e of detail.history) {
      const li = node('li'); li.dataset.eventId = e.id;
      const time = node('time', formatDate(e.recorded_at)); time.dateTime = e.recorded_at;
      li.append(time, node('strong', eventLabel(e)), node('small', e.actor_name ? `Автор: ${e.actor_name}${e.manual ? ' · Ручное решение' : ''}` : 'Автоматический сервис'));
      const reason = historyReason(e); if (reason) li.append(node('p', reason)); events.append(li);
    }
    if (!detail.history.length) events.append(node('li', 'Выдач пока нет.'));
    dq('[data-da-more]').hidden = detail.next_cursor === null; dq('[data-da-more]').disabled = false;
  }
  async function loadDetail(cursor = null) {
    detailController?.abort(); const controller = new AbortController(); detailController = controller;
    const targetId = detailId; dq('[data-da-detail-state]').replaceChildren(node('p', 'Загружаем историю…')); dq('[data-da-more]').disabled = true;
    try {
      const path = endpoint(config.detailUrl, targetId) + (cursor ? `?cursor=${cursor}` : '');
      const page = parseDetail(await request(path, { signal: controller.signal }));
      if (controller.signal.aborted || detailId !== targetId) return;
      if (page.achievement.public_id !== targetId || (cursor && page.next_cursor && page.next_cursor <= cursor)) throw new AchievementApiError(0, 'Некорректная страница истории.');
      detail = { ...page, history: cursor && detail ? mergeEvents(detail.history, page.history) : page.history };
      dq('[data-da-detail-state]').replaceChildren(); renderDetail();
    } catch (error) {
      if (controller.signal.aborted) return;
      if ([401, 403, 404].includes(error.status)) { detail = null; dq('[data-da-detail-content]').replaceChildren(); dq('[data-da-history]').replaceChildren(); dq('[data-da-more]').hidden = true; }
      else dq('[data-da-more]').disabled = false;
      stateError(error, dq('[data-da-detail-state]'), () => void loadDetail(cursor));
    }
  }
  function openDetail(a) {
    detail = null; detailId = a.public_id; document.getElementById('da-detail-title').textContent = a.title;
    dq('[data-da-detail-content]').replaceChildren(); dq('[data-da-history]').replaceChildren(); dq('[data-da-more]').hidden = true;
    open(detailDialog); void loadDetail();
  }
  dq('[data-da-more]').addEventListener('click', () => { if (detail?.next_cursor) void loadDetail(detail.next_cursor); });

  function resetAction() {
    operation = null; recovery = false;
    aq('[data-da-confirm]').hidden = true; aq('[data-da-edit]').hidden = false;
    aq('[data-da-recovery]').hidden = true; aq('[data-da-conflict]').hidden = true;
    notice('', aq('[data-da-action-state]')); form.querySelectorAll('button, select, textarea').forEach(n => n.disabled = false);
  }
  function selectedDefinition() { return items.find(a => a.public_id === form.elements.definition.value); }
  function levels() {
    draftItem = selectedDefinition(); const select = form.elements.tier; select.replaceChildren();
    for (const t of draftItem ? higherTiers(draftItem) : []) { const option = node('option', metals[t.rarity]); option.value = t.code; select.append(option); }
    tierNote();
  }
  function tierNote() {
    const notes = [];
    if (draftItem?.applicable === false) notes.push('Награда не требуется текущей программе. Ручная выдача будет явным исключением.');
    if (draftItem?.auto_grant_blocked) notes.push(manualRegrantMessage);
    const tier = draftItem?.supported_tiers.find(t => t.code === form.elements.tier.value);
    if (tier?.automatic === false) notes.push('Автоматическая выдача этого уровня не поддерживается. Решение будет отмечено как ручное.');
    aq('[data-da-rule-note]').textContent = notes.join(' '); aq('[data-da-rule-note]').hidden = !notes.length;
  }
  function openAction(action, a = null) {
    if (!loaded || busy) return;
    resetAction(); form.reset(); draftAction = action;
    const choices = action === 'grant' ? eligibleDefinitions(items) : [a];
    const select = form.elements.definition; select.replaceChildren();
    for (const item of choices) { const option = node('option', item.title); option.value = item.public_id; select.append(option); }
    if (a) select.value = a.public_id;
    select.disabled = action === 'revoke'; aq('[data-da-tier-field]').hidden = action === 'revoke'; form.elements.tier.required = action === 'grant';
    levels(); document.getElementById('da-action-title').textContent = action === 'revoke' ? 'Отозвать награду' : a?.highest_tier ? 'Повысить уровень' : 'Выдать награду';
    aq('[data-da-submit]').textContent = action === 'revoke' ? 'Подтвердить отзыв' : 'Подтвердить выдачу';
    aq('[data-da-revoke-warning]').hidden = action !== 'revoke'; open(actionDialog);
  }
  form.elements.definition.addEventListener('change', levels); form.elements.tier.addEventListener('change', tierNote);
  form.addEventListener('submit', e => {
    e.preventDefault(); if (busy || recovery || !form.reportValidity()) return;
    const a = selectedDefinition(); const reason = form.elements.reason.value.trim();
    if (!a || !reason) { notice('Укажите причину решения.', aq('[data-da-action-state]')); return; }
    draftItem = a;
    aq('[data-da-confirm-text]').textContent = `${config.userName}: ${draftAction === 'revoke' ? 'отзыв' : a.highest_tier ? 'повышение' : 'выдача'} «${a.title}»${draftAction === 'grant' ? ` — ${metals[a.supported_tiers.find(t => t.code === form.elements.tier.value)?.rarity]}` : ''}.`;
    aq('[data-da-confirm-reason]').textContent = reason;
    aq('[data-da-edit]').hidden = true; aq('[data-da-confirm]').hidden = false; aq('[data-da-submit]').focus();
  });
  aq('[data-da-back]').addEventListener('click', () => { if (!busy && !recovery) { aq('[data-da-confirm]').hidden = true; aq('[data-da-edit]').hidden = false; form.elements.reason.focus(); } });
  function csrf() { return document.querySelector('input[name=csrfmiddlewaretoken]')?.value ?? ''; }
  async function submit() {
    if (busy || config.canManage !== true) return;
    busy = true; form.querySelectorAll('button, select, textarea').forEach(n => n.disabled = true); actionDialog.querySelector('[data-da-close]').disabled = true;
    notice('Сохраняем решение…', aq('[data-da-action-state]'));
    try {
      if (!operation) {
        const id = crypto.randomUUID ? crypto.randomUUID() : [...crypto.getRandomValues(new Uint8Array(16))].map(v => v.toString(16).padStart(2, '0')).join('');
        operation = new Operation(draftAction, draftItem, form.elements.tier.value, form.elements.reason.value, id);
      }
      const result = await operation.send(endpoint(operation.action === 'grant' ? config.grantUrl : config.revokeUrl, operation.id), csrf());
      busy = false; recovery = false; close(actionDialog);
      const message = { grant: 'Награда выдана.', upgrade: 'Уровень награды повышен.', revoke: `Награда отозвана. ${manualRegrantMessage}`, duplicate: 'Операция уже обработана. Повторного события нет.', no_op: 'Текущий уровень не изменился.' }[result.action];
      notice(message); const updated = await load(); if (!updated) notice(`${message} Не удалось обновить список; повторите загрузку.`);
      q('[data-da-refresh]').focus();
    } catch (error) {
      busy = false;
      if (error.status === 409) {
        operation = null; recovery = false; aq('[data-da-confirm]').hidden = true; aq('[data-da-edit]').hidden = true;
        notice(error.message, aq('[data-da-action-state]')); aq('[data-da-conflict]').hidden = false;
        const updated = await load(); aq('[data-da-reopen]').disabled = !updated;
        if (!updated) notice('Конфликт. Не удалось прочитать новые данные; повторите загрузку списка, затем откройте действие заново.', aq('[data-da-action-state]'));
      } else if (error.status === 0 || error.status >= 500) {
        recovery = true; aq('[data-da-recovery]').hidden = false; aq('[data-da-confirm]').hidden = true;
        notice(error.message, aq('[data-da-action-state]'));
      } else {
        operation = null; recovery = false; notice(error.message, aq('[data-da-action-state]'));
        aq('[data-da-confirm]').hidden = true; aq('[data-da-edit]').hidden = [401, 403, 404].includes(error.status);
        if (error.status === 401) { const link = node('a', 'Войти'); link.href = config.loginUrl; aq('[data-da-action-state]').append(link); }
      }
    } finally {
      busy = false; actionDialog.querySelector('[data-da-close]').disabled = false;
      for (const b of actionDialog.querySelectorAll('button')) b.disabled = false;
      if (!aq('[data-da-conflict]').hidden) aq('[data-da-reopen]').disabled = !loaded;
      if (!recovery) { form.elements.reason.disabled = false; form.elements.tier.disabled = false; form.elements.definition.disabled = draftAction === 'revoke'; }
    }
  }
  aq('[data-da-submit]').addEventListener('click', () => void submit()); aq('[data-da-retry]').addEventListener('click', () => void submit());
  aq('[data-da-check]').addEventListener('click', async () => { const updated = await load(); notice(updated ? 'Список обновлён. Закройте окно для просмотра результата или повторите исходную операцию с тем же ID.' : 'Не удалось проверить состояние. Исходная операция сохранена для безопасного повторения.', aq('[data-da-action-state]')); });
  aq('[data-da-reopen]').addEventListener('click', () => { const a = items.find(a => a.public_id === draftItem?.public_id); if (!loaded || !a || (draftAction === 'revoke' && !a.highest_tier)) { close(actionDialog); return; } close(actionDialog); openAction(draftAction, draftAction === 'revoke' || higherTiers(a).length ? a : null); });
  if (!panel.hidden) void load();
}
