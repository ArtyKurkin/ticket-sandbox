// CI annotations are readable without downloading private/raw runner logs.
function safeMessage(message, secrets = []) {
  let text = String(message);
  for (const secret of secrets.filter(value => typeof value === 'string' && value.length > 0)) {
    text = text.split(secret).join('[redacted]');
  }
  return text.replace(/\b(?:Bearer|Basic)\s+[^\s]+/gi, '[authorization redacted]')
    .replace(/\b[0-9a-f]{32,}\b/gi, '[id redacted]')
    .replace(/(https?:\/\/[^\s/:]+:)[^@\s]+@/gi, '$1[redacted]@')
    .slice(0, 4000);
}
function reportFailure(message, secrets = []) {
  const safe = safeMessage(message, secrets);
  console.error(safe);
  if (process.env.GITHUB_ACTIONS === 'true') {
    const escaped = safe.replace(/%/g, '%25').replace(/\r/g, '%0D').replace(/\n/g, '%0A');
    console.error('::error title=Terminal Broker E2E::' + escaped);
  }
  return safe;
}
module.exports = { safeMessage, reportFailure };
