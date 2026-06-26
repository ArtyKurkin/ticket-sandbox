FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y python3 curl vim nano less grep procps iproute2 lsof net-tools \
    && rm -rf /var/lib/apt/lists/*
COPY files/app_server.py /opt/app/app_server.py
COPY files/start-app.sh /opt/app/start-app.sh
COPY files/start.sh /start.sh
COPY files/check.sh /task/check.sh
RUN chmod +x /opt/app/start-app.sh /start.sh /task/check.sh /opt/app/app_server.py
CMD ["/start.sh"]
