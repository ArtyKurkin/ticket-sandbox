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
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /var/www/customer /etc/nginx/ssl

COPY files/index.html /var/www/customer/index.html
COPY files/default /etc/nginx/sites-available/default
COPY files/systemctl /usr/local/bin/systemctl
COPY files/start.sh /start.sh
COPY files/check.sh /task/check.sh

RUN chmod +x /usr/local/bin/systemctl /start.sh /task/check.sh \
    && openssl req -x509 -nodes -newkey rsa:2048 -days 3650 \
        -keyout /etc/nginx/ssl/customer.key \
        -out /etc/nginx/ssl/customer.crt \
        -subj "/CN=customer.example.test" >/dev/null 2>&1

CMD ["/start.sh"]
