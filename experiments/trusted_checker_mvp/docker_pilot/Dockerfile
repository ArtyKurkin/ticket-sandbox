# Build context: experiments/trusted_checker_mvp. No network install/build hook.
# Operator supplies an approved Python base by immutable registry digest.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY verifier.py /checker/verifier.py
COPY docker_pilot/worker.py /checker/worker.py
USER 65532:65532
ENV LANG=C LC_ALL=C
ENTRYPOINT ["/usr/local/bin/python", "-I", "-S", "-B", "/checker/worker.py"]
