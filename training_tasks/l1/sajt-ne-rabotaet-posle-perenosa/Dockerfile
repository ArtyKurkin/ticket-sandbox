FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y \
        nginx \
        curl \
        vim \
        nano \
        less \
        grep \
        procps \
        iproute2 \
        iputils-ping \
        net-tools \
    && rm -rf /var/lib/apt/lists/*

COPY files/start.sh /start.sh
COPY files/check.sh /task/check.sh
COPY files/systemctl /usr/local/bin/systemctl

RUN chmod +x /start.sh \
    && chmod +x /task/check.sh \
    && chmod +x /usr/local/bin/systemctl

CMD ["/start.sh"]