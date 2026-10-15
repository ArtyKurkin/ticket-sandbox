# Build only on an approved isolated daemon. PYTHON_BASE must include a real,
# operator-reviewed digest; no invented digest or mutable default is supplied.
ARG PYTHON_BASE
FROM ${PYTHON_BASE}
ARG PYTHON_BASE
RUN python -c 'import re,sys; sys.exit(0 if re.fullmatch(r"\S+@sha256:[0-9a-f]{64}",sys.argv[1]) else 1)' "$PYTHON_BASE"
COPY runner.py /checker/runner.py
RUN chmod 0555 /checker && chmod 0444 /checker/runner.py
USER 10001:10001
ENTRYPOINT ["/usr/local/bin/python", "-I", "/checker/runner.py"]
