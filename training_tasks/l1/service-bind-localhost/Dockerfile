FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y \
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

RUN mkdir -p /opt/customer-app /var/log/customer-app /run/customer-app

COPY files/app_server.py /opt/customer-app/app_server.py
COPY files/app.conf /opt/customer-app/app.conf
COPY files/customer-app /usr/local/bin/customer-app
COPY files/systemctl /usr/local/bin/systemctl
COPY files/start.sh /start.sh
COPY files/check.sh /task/check.sh

RUN chmod +x \
        /opt/customer-app/app_server.py \
        /usr/local/bin/customer-app \
        /usr/local/bin/systemctl \
        /start.sh \
        /task/check.sh

CMD ["/start.sh"]
