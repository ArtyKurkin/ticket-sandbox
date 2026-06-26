FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y curl vim nano less grep procps iproute2 lsof coreutils \
    && rm -rf /var/lib/apt/lists/*
COPY files/logger.sh /opt/logger/logger.sh
COPY files/start.sh /start.sh
COPY files/check.sh /task/check.sh
RUN chmod +x /opt/logger/logger.sh /start.sh /task/check.sh
CMD ["/start.sh"]
