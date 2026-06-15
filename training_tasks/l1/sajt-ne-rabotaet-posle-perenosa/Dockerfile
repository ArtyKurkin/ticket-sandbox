FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt update && apt install -y \
    nginx \
    php-fpm \
    php-mysql \
    mysql-server \
    mysql-client \
    nano \
    vim \
    curl \
    procps \
    iproute2 \
    iputils-ping \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

COPY files/start.sh /start.sh
COPY files/check.sh /task/check.sh
COPY files/systemctl /usr/local/bin/systemctl
COPY files/mysqlcheck /usr/local/bin/mysqlcheck
COPY files/index.php /var/www/html/index.php

RUN chmod +x /start.sh
RUN chmod +x /task/check.sh
RUN chmod +x /usr/local/bin/systemctl
RUN chmod +x /usr/local/bin/mysqlcheck

CMD ["/start.sh"]