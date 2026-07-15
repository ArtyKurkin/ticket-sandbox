FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y nginx curl vim nano less grep procps iproute2 net-tools \
    && rm -rf /var/lib/apt/lists/*
COPY files/index.html /var/www/html/index.html
COPY files/start.sh /start.sh
COPY files/check.sh /task/check.sh
RUN chmod +x /start.sh /task/check.sh
CMD ["/start.sh"]
