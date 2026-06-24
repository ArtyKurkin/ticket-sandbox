FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y \
        nginx \
        php-fpm \
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
COPY files/index.php /var/www/html/index.php
COPY files/systemctl /usr/local/bin/systemctl

RUN chmod +x /start.sh /task/check.sh /usr/local/bin/systemctl

CMD ["/start.sh"]
