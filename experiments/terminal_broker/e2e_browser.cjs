/* Run with NODE_PATH pointing to a Playwright install. Chrome or chromium required.
 * Input: private session.json created by e2e_runtime, output: screenshots/report.
 * This test uses a real browser, real ttyd WebSockets, nginx and Django auth.
 */
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const { terminal, command, output } = require('./browser_terminal.cjs');
const { reportFailure, loadPrivateConfig } = require('./ci_diagnostics.cjs');
const session = loadPrivateConfig(process.argv[2]);
const out = process.argv[3];
fs.mkdirSync(out, { recursive: true });
const controlOrigin = process.env.TB_CONTROL_ORIGIN || 'http://127.0.0.1:29180';
const origins = { host_port: 'http://127.0.0.1:29182', docker_network: 'http://127.0.0.1:29181' };
const results = [];
let stage = 'startup';
fs.writeFileSync(path.join(out, 'results.json'), '[]');
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function control(mode, action) {
  const response = await fetch(controlOrigin + '/__e2e__/action', {
    method: 'POST', headers: { Authorization: 'Bearer ' + session.control },
    body: JSON.stringify({ mode, action }),
  });
  if (!response.ok) throw new Error('Control operation failed: ' + action + ' ' + await response.text());
  return response.json();
}
async function census(mode, count) {
  for (let i = 0; i < 60; i++) {
    const stats = await control(mode, 'stats');
    if (!stats.pid1Running || !stats.foreignRunning) throw new Error('Cleanup killed PID 1 or a foreign process');
    if (stats.brokerErrors) throw new Error('Broker reported a cleanup error (automatic recovery must not mask it)');
    if (stats.pids.length === count) return stats;
    await sleep(250);
  }
  throw new Error('Unexpected owned process count: expected ' + count);
}
(async () => {
  const browser = await chromium.launch({ headless: true,
    ...(process.env.TB_CHROME ? { executablePath: process.env.TB_CHROME } : {}) });
  try {
    for (const mode of ['host_port', 'docker_network']) {
      stage = mode + ': authorization and parallel shells';
      const origin = origins[mode];
      const context = await browser.newContext({ viewport: { width: 1000, height: 700 } });
      await context.addCookies([{ name: 'sessionid', value: session.owner, url: origin }]);
      const stranger = await browser.newContext();
      await stranger.addCookies([{ name: 'sessionid', value: session.outsider, url: origin }]);
      const denied = await stranger.request.get(origin + session.paths[mode]);
      if (denied.status() !== 403) throw new Error('Foreign attempt accepted: ' + denied.status());
      await stranger.close();
      const one = await terminal(context, origin + session.paths[mode]);
      const two = await terminal(context, origin + session.paths[mode]);
      const before = await census(mode, 2);
      await command(one, "printf 'PID_%s\\n' $$");
      await command(two, "printf 'PID_%s\\n' $$");
      await output(one, 'PID_[0-9]+');
      await output(two, 'PID_[0-9]+');
      const pid1 = (await one.evaluate(() => window.__tbOutput)).match(/PID_([0-9]+)/)[1];
      const pid2 = (await two.evaluate(() => window.__tbOutput)).match(/PID_([0-9]+)/)[1];
      if (pid1 === pid2) throw new Error('PTY sessions share a Bash');
      await command(one, "printf '\\nSIZE_'; stty size");
      await output(one, 'SIZE_[0-9]+ [0-9]+');
      const initial = (await one.evaluate(() => window.__tbOutput)).match(/SIZE_([0-9]+ [0-9]+)/)[1];
      await command(one, "trap 'printf \"WIN_%s\\n\" CHANGED' WINCH");
      await one.setViewportSize({ width: 1300, height: 850 });
      await output(one, 'WIN_CHANGED');
      await command(one, "printf '\\nRESIZED_'; stty size");
      await output(one, 'RESIZED_[0-9]+ [0-9]+');
      const resized = (await one.evaluate(() => window.__tbOutput)).match(/RESIZED_([0-9]+ [0-9]+)/)[1];
      if (initial === resized) throw new Error('Browser resize did not reach task PTY');
      await command(one, 'sleep 30');
      await sleep(200);
      await one.keyboard.press('Control+c');
      await command(one, "printf 'CTRL_%s\\n' OK");
      await output(one, 'CTRL_OK', 3000);
      await command(one, 'top');
      await output(one, 'Tasks:');
      await one.setViewportSize({ width: 1100, height: 760 });
      await sleep(500);
      await one.screenshot({ path: path.join(out, mode + '-top.png') });
      await one.keyboard.press('q');
      await command(one, "printf 'FULLSCREEN_%s\\n' OK");
      await output(one, 'FULLSCREEN_OK');
      stage = mode + ': closing independent tabs';
      await two.close();
      await census(mode, 1);
      await sleep(500);
      await command(one, "printf 'REMAINING_%s\\n' ALIVE");
      await output(one, 'REMAINING_ALIVE');
      await one.close();
      await census(mode, 0);
      const reconnect = await terminal(context, origin + session.paths[mode]);
      stage = mode + ': creating HUP-resistant orphan';
      await census(mode, 1);
      await command(reconnect, "trap '' HUP TERM; sleep 60 &");
      await census(mode, 2);
      await control(mode, 'kill');
      stage = mode + ': orphan census after SIGKILL';
      const orphaned = await control(mode, 'stats');
      if (orphaned.pids.length === 0) throw new Error('Fault injection left no orphan to recover');
      await control(mode, 'restart-broker');
      stage = mode + ': recovery';
      await census(mode, 0);
      await reconnect.close();
      const recovered = await terminal(context, origin + session.paths[mode]);
      await census(mode, 1);
      await control(mode, 'revoke');
      stage = mode + ': restart revocation';
      await census(mode, 0);
      const revoked = await context.request.get(origin + session.paths[mode]);
      if (revoked.status() !== 403) throw new Error('Restart did not revoke access');
      await recovered.close();
      await control(mode, 'allow');
      const last = await terminal(context, origin + session.paths[mode]);
      await control(mode, 'replace-generation');
      stage = mode + ': generation revocation';
      await census(mode, 0);
      await last.close();
      await context.close();
      results.push({ mode, passed: true, initialSize: initial, resizedSize: resized,
        independentPids: [pid1, pid2], initialOwnedProcesses: before.pids.length,
        checks: ['foreign-user-denied', 'parallel-PTY', 'browser-resize', 'SIGWINCH', 'Ctrl+C',
          'top', 'browser-close-cleanup', 'reconnect', 'SIGKILL-recovery', 'restart-revocation', 'generation-revocation'] });
      fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(results, null, 2));
      console.log(mode + ': PASS');
    }
  } finally { await browser.close(); }
})().catch(error => {
  const safe = reportFailure(stage + ': ' + error.message, [session.control, session.owner, session.outsider]);
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify([...results, { passed: false, stage, error: safe }], null, 2));
  process.exitCode = 1;
});
