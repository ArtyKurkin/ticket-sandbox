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
        net-tools \
        lsof \
        python3 \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/report-api /var/log/report-api /run/report-api

COPY files/backend.py /opt/report-api/backend.py
COPY files/report-api /usr/local/bin/report-api
COPY files/systemctl /usr/local/bin/systemctl
COPY files/default /etc/nginx/sites-available/default
COPY files/start.sh /start.sh
COPY files/check.sh /task/check.sh

RUN chmod +x \
        /opt/report-api/backend.py \
        /usr/local/bin/report-api \
        /usr/local/bin/systemctl \
        /start.sh \
        /task/check.sh \
    && ln -sf /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default

CMD ["/start.sh"]
