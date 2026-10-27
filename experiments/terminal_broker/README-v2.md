# Terminal Broker experimental v2

This remains a lab experiment, not a production rollout. The original `terminal_broker_lab.py` and Django code stay unchanged.

Changes: validate queue/task/attempt and exact Docker ID, reject stopped targets, allow up to four concurrent sessions, attempt to close sessions on shutdown, bound forwarding buffers, and eight offline unit tests.

Known blockers to production:
- WebSocket/ttyd resizing does not propagate to the broker PTY (`socat STDIO` has no custom resize protocol).
- The socket is a bearer capability: any process allowed to connect gains a root shell in the pinned container. The ttyd HTTP gateway must authorize each request and avoid session cross-talk.
- Docker CLI on the privileged host still has broad Docker access if the broker is compromised; stronger process isolation / host controls required.
- Generation-aware orchestration must stop the broker and existing Docker exec sessions before removing or recreating an attempt; process crashes and daemon restarts need cleanup.
- Session cleanup under backpressure, errors, SIGTERM, and concurrent clients needs Docker-backed E2E coverage.
- The process must not be launched from the public-facing web worker.

## Local offline tests

`python -m unittest discover -s experiments/terminal_broker -p 'test_*.py' -v`

## Lab smoke (on VDS, after copying terminal_broker.py)

Do not stop the old broker. Use a separate socket directory and an unused port. Example:

```
cd /root/tc-e2e-pilot
TARGET=$(docker inspect ticket-sandbox-l1-service-bind-localhost-1 --format '{{.Id}}')
install -d -m 700 /root/tc-e2e-pilot/terminal-broker-v2
nohup python3 terminal_broker.py \
  --container-id "$TARGET" --attempt 1 --queue l1 --task service-bind-localhost \
  --socket /root/tc-e2e-pilot/terminal-broker-v2/session.sock \
  > /root/tc-e2e-pilot/terminal-broker-v2/broker.log 2>&1 &
echo $! > /root/tc-e2e-pilot/terminal-broker-v2/broker.pid
cat /root/tc-e2e-pilot/terminal-broker-v2/broker.log
```

NOTE: previous lab used an all-root sidecar and a bind-mount of the socket dir. Keep `ttyd` bound only to localhost and use an SSH tunnel. Never expose it on a public interface.
