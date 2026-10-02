const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

function setup(answer, report) {
  const listeners = [];
  let removed = false;
  const form = {
    dataset: {},
    addEventListener: (name, callback) => listeners.push(callback),
    checkValidity: () => fields.every(field => !field.error),
    reportValidity() { this.reported = true; },
  };
  const fields = [answer, report].map(value => ({
    value, form, dataset: { requiredMessage: 'Заполни поле' }, handlers: {},
    setCustomValidity(message) { this.error = message; },
    addEventListener(name, callback) { this.handlers[name] = callback; },
  }));
  const button = {
    disabled: false, dataset: {}, classList: { add() {} },
    closest: () => form, querySelector: selector => selector === '.button-spinner' ? {} : null,
  };
  const document = {
    addEventListener() {},
    querySelectorAll(selector) {
      if (selector === 'textarea[data-required-message]') return fields;
      if (selector === 'form') return [form];
      if (selector === 'button[data-loading-text]') return [button];
      if (selector === 'iframe') return [{ remove() { removed = true; } }];
      return [];
    },
  };
  const context = vm.createContext({ document, window: {}, console });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../../../static/js/app.js'), 'utf8'), context);
  context.bindRequiredAnswers();
  context.removeTerminalFramesBeforeSubmit();
  context.bindLoadingButtons();
  function submit() {
    const event = { defaultPrevented: false, preventDefault() { this.defaultPrevented = true; } };
    listeners.forEach(callback => callback(event));
    return event;
  }
  return { fields, form, button, submit, removed: () => removed };
}

for (const values of [['Ответ клиенту', ''], ['', 'Диагностика'], ['Ответ', '  \n ']]) {
  test(`invalid form retains text and blocks submit: ${JSON.stringify(values)}`, () => {
    const state = setup(...values);
    assert.equal(state.submit().defaultPrevented, true);
    assert.deepEqual(state.fields.map(field => field.value), values);
    assert.equal(state.button.disabled, false);
    assert.equal(state.removed(), false);
    assert.equal(state.form.reported, true);
  });
}

test('correcting an empty field allows the next submit', () => {
  const state = setup('Ответ клиенту', '');
  state.fields[1].value = 'Диагностика';
  state.fields[1].handlers.input();
  assert.equal(state.submit().defaultPrevented, false);
  assert.equal(state.button.disabled, true);
  assert.equal(state.removed(), true);
});
