# Terminal Broker 1.0 — experimental

Laboratory prototype of an interactive terminal without mounting
the Docker socket into the ttyd container.

Verified:
- Unix socket connection
- Pinned Docker container ID
- Interactive Bash input/output
- ttyd image without Docker CLI
- ttyd container without Docker socket

Not yet verified:
- Browser WebSocket terminal operation
- PTY window resizing
- Session revocation on environment restart
- Per-attempt socket authorization
- Concurrent sessions and reliable cleanup

Not production-ready. Do not replace the existing Django terminal
until the remaining checks and integration tests pass.
