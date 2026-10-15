ARG PYTHON_BASE
FROM ${PYTHON_BASE}
ARG PYTHON_BASE
RUN python -c 'import re,sys; sys.exit(0 if re.fullmatch(r"\S+@sha256:[0-9a-f]{64}",sys.argv[1]) else 1)' "$PYTHON_BASE"
COPY synthetic_target.py /fixture/server.py
RUN printf '{"bind":"127.0.0.1"}\n' > /fixture/service.json
# Intentionally writable/root fixture, not a trusted runtime.
ENTRYPOINT ["/usr/local/bin/python", "-I", "/fixture/server.py"]
