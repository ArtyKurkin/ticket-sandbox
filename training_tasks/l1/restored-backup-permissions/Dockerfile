FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y curl vim nano less grep procps coreutils \
    && rm -rf /var/lib/apt/lists/*
COPY files/run.sh /opt/myapp/run.sh
COPY files/start.sh /start.sh
COPY files/check.sh /task/check.sh
RUN chmod +x /start.sh /task/check.sh
CMD ["/start.sh"]
