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

RUN mkdir -p /opt/customer-api /var/log/customer-api

COPY files/backend.py /opt/customer-api/backend.py
COPY files/default /etc/nginx/sites-available/default
COPY files/start.sh /start.sh
COPY files/check.sh /task/check.sh
COPY files/systemctl /usr/local/bin/systemctl

RUN chmod +x \
        /opt/customer-api/backend.py \
        /start.sh \
        /task/check.sh \
        /usr/local/bin/systemctl \
    && ln -sf /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default

CMD ["/start.sh"]
