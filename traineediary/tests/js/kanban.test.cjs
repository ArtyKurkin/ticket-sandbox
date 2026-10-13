const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

function loadKanban() {
  const context = vm.createContext({
    document: { addEventListener() {} },
    window: { addEventListener() {} },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../../../static/js/kanban.js'), 'utf8'), context);
  return context;
}

function card(scheme = 'unified', entryType = 'new_hire') {
  return { dataset: { stageScheme: scheme, entryType } };
}

function target(scheme = 'unified', extra = {}) {
  return { dataset: {
    stageScheme: scheme, stageActive: 'true',
    appliesNewHire: 'true', appliesInternalTransfer: 'true', ...extra,
  } };
}

test('drag targets respect scheme, activity and entry type', () => {
  const context = loadKanban();
  assert.equal(context.isStageTargetAllowed(card(), target()), true);
  assert.equal(context.isStageTargetAllowed(card('legacy'), target('legacy')), true);
  assert.equal(context.isStageTargetAllowed(card('legacy'), target('unified')), false);
  assert.equal(context.isStageTargetAllowed(card(), target('legacy')), false);
  assert.equal(context.isStageTargetAllowed(card(), target('unified', { stageActive: 'false' })), false);
  assert.equal(context.isStageTargetAllowed(card('unified', 'internal_transfer'), target('unified', { appliesInternalTransfer: 'false' })), false);
  assert.equal(context.isStageTargetAllowed(card(), target('unified', { appliesInternalTransfer: 'false' })), true);
});

test('pointer handling uses the scrolling board containing each card', () => {
  const context = loadKanban();
  const calls = [];
  context.startPointerDrag = (...args) => calls.push(args);
  const legacyBoard = { name: 'legacy' };
  const unifiedBoard = { name: 'unified' };
  function draggable(board) {
    const item = { closest: selector => selector === '.kanban-board' ? board : null };
    item.addEventListener = (_, callback) => { item.pointerDown = callback; };
    return item;
  }
  const legacy = draggable(legacyBoard);
  const unified = draggable(unifiedBoard);
  const container = { querySelectorAll: () => [legacy, unified] };
  context.attachDragHandlers(container);
  legacy.pointerDown({});
  unified.pointerDown({});
  assert.equal(calls[0][3], legacyBoard);
  assert.equal(calls[1][3], unifiedBoard);
});

test('forbidden drop cannot open the dialog or redirect to probation completion', () => {
  const context = loadKanban();
  const errors = [];
  context.showMoveError = message => errors.push(message);
  context.document.getElementById = () => { throw new Error('Dialog should not be accessed'); };
  context.window.location = { assign() { throw new Error('Redirect should not occur'); } };
  const destination = target('legacy', { requiresCompletion: 'true', stageId: '9' });
  context.openStageMoveDialog(card('unified'), destination);
  assert.equal(errors.length, 1);
});


test('fragment refresh keeps each scheme board scroll position', async () => {
  const context = loadKanban();
  const section = (scheme, scrollLeft) => ({
    dataset: { kanbanScheme: scheme },
    board: { scrollLeft },
    querySelector() { return this.board; },
  });
  const before = [section('legacy', 120), section('unified', 350)];
  const after = [section('legacy', 0), section('unified', 0)];
  let refreshed = false;
  const container = {
    dataset: { refreshUrl: '/diary/fragment/' },
    querySelectorAll(selector) {
      if (selector === '[data-kanban-scheme]') return refreshed ? after : before;
      return [];
    },
    set innerHTML(html) { assert.equal(html, '<updated>'); refreshed = true; },
  };
  context.fetch = async () => ({ ok: true, text: async () => '<updated>' });
  await context.refreshKanbanBoard(container);
  assert.equal(after[0].board.scrollLeft, 120);
  assert.equal(after[1].board.scrollLeft, 350);
});
