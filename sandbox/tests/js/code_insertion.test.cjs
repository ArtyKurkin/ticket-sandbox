const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

function setup(value, start = value.length, end = start, direction = 'none') {
  const form = {
    listeners: [],
    addEventListener(name, callback) { this.listeners.push(callback); },
    checkValidity: () => !field.error && !report.error,
    reportValidity() {},
  };
  function makeField(value) {
    return {
      value, form, listeners: {}, dataset: { requiredMessage: 'Заполни поле' },
      setCustomValidity(message) { this.error = message; },
      addEventListener(name, callback) { this.listeners[name] = callback; },
      dispatchEvent(event) { this.lastEvent = event; this.listeners[event.type]?.(event); },
      focus() { this.focused = true; },
      setRangeText(text, start, end) {
        this.value = this.value.slice(0, start) + text + this.value.slice(end);
      },
      setSelectionRange(start, end, direction) {
        this.selectionStart = start; this.selectionEnd = end; this.selectionDirection = direction;
      },
    };
  }
  const field = makeField(value);
  field.setSelectionRange(start, end, direction);
  const report = makeField('Диагностика');
  const button = {
    hidden: true, dataset: { codeTarget: 'client-answer' },
    addEventListener(name, callback) { this[name] = callback; },
  };
  const document = {
    addEventListener() {},
    getElementById: () => field,
    querySelectorAll(selector) {
      if (selector === '[data-code-target]') return [button];
      if (selector === 'textarea[data-required-message]') return [field, report];
      return [];
    },
  };
  const context = vm.createContext({ document, window: {}, console, Event });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../../../static/js/app.js'), 'utf8'), context);
  context.bindRequiredAnswers();
  context.bindCodeButtons();
  return { context, field, report, button, form };
}

test('inserts tags at the caret and preserves surrounding text', () => {
  const { button, field } = setup('ДоПосле', 2);
  button.click();
  assert.equal(field.value, 'До[code]\n[/code]После');
  assert.equal(field.selectionStart, 9);
  assert.equal(field.selectionEnd, 9);
  assert.equal(field.focused, true);
});

test('empty textarea gets a cursor between the tags', () => {
  const { button, field } = setup('');
  button.click();
  assert.equal(field.value, '[code]\n[/code]');
  assert.equal(field.selectionStart, '[code]\n'.length);
  assert.equal(field.selectionEnd, field.selectionStart);
});

test('wraps multiline selection and keeps it selected with its direction', () => {
  const value = 'До\nnginx -t\nreload\nПосле';
  const selected = 'nginx -t\nreload';
  const { button, field } = setup(value, 3, 3 + selected.length, 'backward');
  button.click();
  assert.equal(field.value, 'До\n[code]\nnginx -t\nreload\n[/code]\nПосле');
  assert.equal(field.value.slice(field.selectionStart, field.selectionEnd), selected);
  assert.equal(field.selectionStart, 10);
  assert.equal(field.selectionDirection, 'backward');
});

test('wraps the whole answer without interpreting HTML', () => {
  const value = '<script>"&"</script>';
  const { button, field } = setup(value, 0, value.length);
  button.click();
  assert.equal(field.value, '[code]\n' + value + '\n[/code]');
  assert.equal(field.value.slice(field.selectionStart, field.selectionEnd), value);
});

test('inserts at the end after focus has left the textarea', () => {
  const { button, field } = setup('Ответ');
  field.focused = false;
  button.click();
  assert.equal(field.value, 'Ответ[code]\n[/code]');
  assert.equal(field.focused, true);
});

test('input event updates existing validity without submitting the form', () => {
  const { button, field, report, form } = setup('');
  assert.equal(field.error, 'Заполни поле');
  let submits = 0;
  form.addEventListener('submit', () => { submits += 1; });
  button.click();
  assert.equal(field.error, '');
  assert.equal(field.lastEvent.type, 'input');
  assert.equal(field.lastEvent.bubbles, true);
  assert.equal(report.value, 'Диагностика');
  assert.equal(submits, 0);
  report.value = '   ';
  report.dispatchEvent(new Event('input'));
  const event = { defaultPrevented: false, preventDefault() { this.defaultPrevented = true; } };
  form.listeners.forEach(callback => callback(event));
  assert.equal(event.defaultPrevented, true);
});

test('code button is enabled only after binding and respects readonly/disabled fields', () => {
  const { button, field } = setup('Ответ');
  assert.equal(button.hidden, false);
  field.readOnly = true;
  button.click();
  assert.equal(field.value, 'Ответ');
  field.readOnly = false;
  field.disabled = true;
  button.click();
  assert.equal(field.value, 'Ответ');
});
