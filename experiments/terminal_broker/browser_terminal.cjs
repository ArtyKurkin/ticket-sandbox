async function output(page, pattern, timeout = 10000) {
  await page.waitForFunction(source => new RegExp(source).test(window.__tbOutput || ''), pattern, { timeout });
}
async function command(page, text) {
  await page.locator('.xterm-helper-textarea').focus();
  await page.keyboard.type(text);
  await page.keyboard.press('Enter');
}
async function terminal(context, url) {
  const page = await context.newPage();
  page.__tbSockets = [];
  page.on('websocket', socket => page.__tbSockets.push(socket));
  await page.addInitScript(() => {
    window.__tbOutput = '';
    const Original = window.WebSocket;
    window.WebSocket = class extends Original {
      constructor(...args) {
        super(...args);
        this.addEventListener('message', async event => {
          const bytes = typeof event.data === 'string' ? new TextEncoder().encode(event.data)
            : new Uint8Array(event.data instanceof Blob ? await event.data.arrayBuffer() : event.data);
          if (bytes[0] === 48) window.__tbOutput += new TextDecoder().decode(bytes.slice(1));
        });
      }
    };
  });
  await page.goto(url);
  // xterm's helper textarea can have a zero-sized box while remaining focusable.
  await page.locator('.xterm-helper-textarea').waitFor({ state: 'attached' });
  // Do not type before the ttyd child has switched its PTY to raw mode; that
  // switch flushes input which arrived during startup.
  await page.waitForFunction(() => (window.__tbOutput || '').length > 0, null, { timeout: 10000 });
  await command(page, "printf 'TB_%s\\n' READY");
  await output(page, 'TB_READY');
  return page;
}
module.exports = { output, command, terminal };
