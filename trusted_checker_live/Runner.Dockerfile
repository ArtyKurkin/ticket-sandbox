# Build only after explicit operator approval. Supply an approved Ubuntu digest.
ARG PYTHON_BASE
FROM ${PYTHON_BASE}
ARG PYTHON_BASE
ARG CHECKER_SOURCE_SHA256
LABEL tc-shadow.checker-source=${CHECKER_SOURCE_SHA256}
RUN printf '%s' "$PYTHON_BASE" | grep -Eq '^[^ ]+@sha256:[0-9a-f]{64}$'
RUN apt-get update && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /checker /scratch && chmod 0555 /checker /scratch
COPY runner.py /checker/service_bind_peer.py
RUN printf '%s  /checker/service_bind_peer.py\n' "$CHECKER_SOURCE_SHA256" | sha256sum -c - \
    && chmod 0444 /checker/service_bind_peer.py
USER 10001:10001
WORKDIR /scratch
ENTRYPOINT ["/usr/bin/python3", "-I", "/checker/service_bind_peer.py"]
