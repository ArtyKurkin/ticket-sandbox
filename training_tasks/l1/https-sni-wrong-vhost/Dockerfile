FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y \
        nginx \
        curl \
        openssl \
        vim \
        nano \
        less \
        grep \
        procps \
        iproute2 \
        net-tools \
        libc-bin \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p \
        /var/www/legacy \
        /var/www/portal \
        /etc/nginx/ssl

COPY files/legacy-index.html /var/www/legacy/index.html
COPY files/portal-index.html /var/www/portal/index.html
COPY files/https-sites.conf /etc/nginx/sites-available/https-sites.conf
COPY files/start.sh /start.sh
COPY files/check.sh /task/check.sh
COPY files/systemctl /usr/local/bin/systemctl

RUN rm -f /etc/nginx/sites-enabled/default \
    && ln -s /etc/nginx/sites-available/https-sites.conf /etc/nginx/sites-enabled/https-sites.conf \
    && chmod +x /start.sh /task/check.sh /usr/local/bin/systemctl \
    && openssl req -x509 -nodes -newkey rsa:2048 -days 3650 \
        -keyout /etc/nginx/ssl/legacy.key \
        -out /etc/nginx/ssl/legacy.crt \
        -subj "/CN=legacy.example.test" >/dev/null 2>&1 \
    && openssl req -x509 -nodes -newkey rsa:2048 -days 3650 \
        -keyout /etc/nginx/ssl/portal.key \
        -out /etc/nginx/ssl/portal.crt \
        -subj "/CN=portal.example.test" >/dev/null 2>&1

CMD ["/start.sh"]
