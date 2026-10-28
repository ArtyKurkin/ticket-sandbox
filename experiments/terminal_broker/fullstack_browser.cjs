const fs = require('node:fs');
const crypto = require('node:crypto');
const path = require('node:path');
const { chromium } = require('playwright');
const { terminal, command, output, quitFullscreen } = require('./browser_terminal.cjs');
const { reportFailure, loadPrivateConfig } = require('./ci_diagnostics.cjs');
const modes = loadPrivateConfig(process.argv[2]);
const out = process.argv[3];
fs.mkdirSync(out, { recursive: true });
const results = [];
let stage = 'startup';
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function control(mode, action = 'state', extra = {}) {
  const response = await fetch(mode.webOrigin + '/__tb2_test__/', { method: 'POST',
    headers: { Authorization: 'Bearer ' + mode.control, 'Content-Type': 'application/json', Connection: 'close' },
    body: JSON.stringify({ action, ...extra }) });
  if (!response.ok) throw new Error('Control HTTP ' + response.status);
  const state = await response.json();
  if (state.database !== 'postgresql' || state.eager) throw new Error('Not real PostgreSQL/Celery');
  return state;
}
async function waitReady(mode, previousGeneration = null) {
  for (let i = 0; i < 240; i++) {
    const state = await control(mode);
    const failed = state.attempts.find(a => a.environment_status === 'error');
    if (failed) throw new Error('Environment failed: ' + failed.error);
    if (state.attempts.every(a => a.environment_status === 'ready') &&
        (!previousGeneration || state.attempts[0].generation !== previousGeneration)) return state;
    await pause(500);
  }
  throw new Error('Timed out waiting for actual Celery environment');
}
async function action(context, mode, role, actionName) {
  const response = await context.request.post(mode.gatewayOrigin + `/attempts/${mode.attempts[role]}/${actionName}/`, {
    form: { operation_id: crypto.randomUUID() }, headers: { 'X-CSRFToken': mode.csrf }, maxRedirects: 0 });
  if (response.status() !== 302) throw new Error('Production action rejected: ' + actionName + ' ' + response.status());
}
async function browserContext(browser, mode, role) {
  const context = await browser.newContext({ viewport: { width: 1000, height: 700 } });
  await context.addCookies([
    { name: 'sessionid', value: mode[role], url: mode.gatewayOrigin },
    { name: 'csrftoken', value: mode.csrf, url: mode.gatewayOrigin },
  ]);
  return context;
}
(async () => {
  const browser = await chromium.launch({ headless: true,
    ...(process.env.TB_CHROME ? { executablePath: process.env.TB_CHROME } : {}) });
  try {
    for (const mode of modes) {
      stage = mode.mode + ': start through Django HTTP and Celery';
      const owner = await browserContext(browser, mode, 'owner');
      const outsider = await browserContext(browser, mode, 'outsider');
      await action(owner, mode, 'owner', 'start');
      await action(outsider, mode, 'outsider', 'start');
      const started = await waitReady(mode);
      const first = started.attempts[0];
      const other = started.attempts[1];
      if (first.generation === other.generation || first.container_id === other.container_id) throw new Error('Attempts share environment identity');
      const denied = await owner.request.get(mode.gatewayOrigin + other.url);
      if (denied.status() !== 403) throw new Error('Foreign attempt authorized');
      for (const endpoint of ['/terminal-auth/', '/terminal-broker-auth/', '/_terminal_auth']) {
        const response = await owner.request.get(mode.gatewayOrigin + endpoint);
        if (response.status() !== 404) throw new Error('Internal auth endpoint exposed at gateway');
        if (response.headers()['x-terminal-authorization']) throw new Error('Gateway leaked Basic credential');
      }
      stage = mode.mode + ': browser PTY';
      const one = await terminal(owner, mode.gatewayOrigin + first.url);
      const two = await terminal(owner, mode.gatewayOrigin + first.url);
      await command(one, "printf 'SIZE_'; stty size");
      await output(one, 'SIZE_[0-9]+ [0-9]+');
      const beforeSize = (await one.evaluate(() => window.__tbOutput)).match(/SIZE_([0-9]+ [0-9]+)/)[1];
      await one.setViewportSize({ width: 1300, height: 850 });
      await command(one, "printf 'AFTER_'; stty size");
      await output(one, 'AFTER_[0-9]+ [0-9]+');
      const afterSize = (await one.evaluate(() => window.__tbOutput)).match(/AFTER_([0-9]+ [0-9]+)/)[1];
      if (beforeSize === afterSize) throw new Error('Resize failed');
      await command(one, 'sleep 30');
      await pause(200);
      await one.keyboard.press('Control+c');
      await command(one, "printf 'CTRL_%s\\n' OK");
      await output(one, 'CTRL_OK', 3000);
      await command(one, 'top');
      await output(one, 'Tasks:');
      await one.setViewportSize({ width: 1200, height: 800 });
      await pause(300);
      await quitFullscreen(one);
      await command(one, "printf 'TOP_%s\\n' OK");
      await output(one, 'TOP_OK');
      await two.close();
      await command(one, "printf 'INDEPENDENT_%s\\n' OK");
      await output(one, 'INDEPENDENT_OK');
      stage = mode.mode + ': broker SIGKILL and recovery';
      await command(one, 'trap "" HUP TERM');
      await control(mode, 'broker-cycle');
      let cycle;
      for (let i=0; i<120; i++) {
        cycle=(await control(mode)).broker_cycle;
        if(cycle?.recovered) break;
        await pause(500);
      }
      if(!cycle?.recovered) throw new Error('Broker SIGKILL recovery failed');
      await one.close();
      const afterCrash = await terminal(owner, mode.gatewayOrigin + first.url);
      stage = mode.mode + ': Celery restart';
      const oldSocket = afterCrash.__tbSockets[0];
      if (!oldSocket || oldSocket.isClosed()) throw new Error('Old session was not connected before restart');
      await action(owner, mode, 'owner', 'restart');
      const restarted = await waitReady(mode, first.generation);
      const next = restarted.attempts[0];
      if (next.container_id === first.container_id || next.generation === first.generation || next.restart_count !== 1) throw new Error('Restart did not replace the environment');
      if (!next.events.some(e => e.kind === 'reset' && e.phase === 'finished' && e.outcome === 'success')) throw new Error('No successful restart ledger event');
      for (let i = 0; i < 50 && !oldSocket.isClosed(); i++) await pause(100);
      if (!oldSocket.isClosed()) throw new Error('Old WebSocket survived environment restart');
      await afterCrash.close();
      const fresh = await terminal(owner, mode.gatewayOrigin + next.url);
      await fresh.screenshot({ path: path.join(out, mode.mode + '-new-generation.png') });
      stage = mode.mode + ': active security review';
      // Lite: daemon-like work belongs to the task lifetime, not the tab.
      await command(fresh, "printf 'SHELL_PID=%s\\n' $$");
      await output(fresh, 'SHELL_PID=[0-9]+');
      const interactivePid=Number((await fresh.evaluate(()=>window.__tbOutput)).match(/SHELL_PID=([0-9]+)/)[1]);
      await command(fresh, "env -i PATH=/usr/bin:/bin bash -c 'trap \"\" HUP TERM; exec sleep 600' & printf 'ESCAPE_PID=%s\\n' \"$!\"");
      await output(fresh, 'ESCAPE_PID=[0-9]+');
      const escapedPid = Number((await fresh.evaluate(() => window.__tbOutput)).match(/ESCAPE_PID=([0-9]+)/)[1]);
      await fresh.close();
      await control(mode, 'security', { escaped_pid: escapedPid, interactive_pid: interactivePid });
      let security = null;
      for (let i = 0; i < 120; i++) {
        security = (await control(mode)).security;
        if (security) break;
        await pause(500);
      }
      if (!security || !security.authorizationChecksPassed || !security.backgroundSurvivesTabClose || !security.interactiveExecExited) throw new Error('Lite security/session probes did not complete');
      fs.writeFileSync(path.join(out, mode.mode + '-security.json'), JSON.stringify(security, null, 2));
      stage = mode.mode + ': cleanup through real Celery worker';
      await control(mode, 'cleanup');
      let cleaned = null;
      for (let i = 0; i < 120; i++) {
        cleaned = await control(mode);
        if (cleaned.attempts.every(a => a.environment_status === 'idle' && !a.container_name && !a.terminal_name)) break;
        await pause(500);
      }
      if (!cleaned.attempts.every(a => a.environment_status === 'idle' && !a.container_name && !a.terminal_name)) throw new Error('Celery cleanup incomplete');
      if ((await owner.request.get(mode.gatewayOrigin + next.url)).status() !== 403) throw new Error('Deleted environment still authorized');
      const killed=cleaned.faults.filter(x=>x.kind==='worker-SIGKILL-after-create');
      const duplicates=cleaned.faults.filter(x=>x.kind==='duplicate-delivery');
      if(killed.length!==2 || duplicates.length<3) throw new Error('Worker loss / duplicate fault injection did not execute');
      await fresh.close();
      await owner.close(); await outsider.close();
      results.push({ mode: mode.mode, passed: true, database: started.database, eager: started.eager,
        queue: started.queue, original: first, replacement: next, foreignAttempt: other,
        beforeSize, afterSize, cleaned: cleaned.attempts, security, workerFaults: cleaned.faults, brokerSIGKILLRecovery: cycle,
        checks: ['actual-start-view', 'real-Celery-start', 'PostgreSQL', 'Redis', 'two-attempt-isolation',
          'parallel-PTY', 'resize', 'Ctrl+C', 'internal-endpoints-hidden', 'real-Celery-restart',
          'old-session-revoked', 'generation-and-Docker-ID-replaced', 'real-Celery-cleanup'] });
      fs.writeFileSync(path.join(out, 'fullstack.json'), JSON.stringify(results, null, 2));
      console.log(mode.mode + ': real PostgreSQL/Redis/Celery PASS');
    }
  } catch (error) {
    let index = 0;
    for (const context of browser.contexts()) for (const page of context.pages()) {
      await page.screenshot({ path: path.join(out, 'failure-' + index++ + '.png') }).catch(() => {});
      fs.writeFileSync(path.join(out, 'failure-' + index + '.json'), JSON.stringify({ url: page.url(),
        output: await page.evaluate(() => window.__tbOutput || ''),
        sockets: (page.__tbSockets || []).map(socket => ({ url: socket.url(), closed: socket.isClosed() })) }, null, 2));
    }
    throw error;
  } finally { await browser.close(); }
})().catch(error => {
  const safe = reportFailure(stage + ': ' + error.message, modes.flatMap(mode => [mode.control, mode.owner, mode.outsider, mode.csrf]));
  fs.writeFileSync(path.join(out, 'fullstack.json'), JSON.stringify([...results, { passed: false, stage, error: safe }], null, 2));
  process.exitCode = 1;
});
