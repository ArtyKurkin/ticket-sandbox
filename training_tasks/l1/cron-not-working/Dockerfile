FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y \
        cron \
        curl \
        vim \
        nano \
        less \
        grep \
        procps \
        iproute2 \
        net-tools \
    && rm -rf /var/lib/apt/lists/*

COPY files/start.sh /start.sh
COPY files/check.sh /task/check.sh
COPY files/update_data.sh /opt/app/update_data.sh

RUN chmod +x /start.sh /task/check.sh /opt/app/update_data.sh

CMD ["/start.sh"]
