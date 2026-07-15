FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y python3 curl vim nano less grep procps iproute2 net-tools \
    && rm -rf /var/lib/apt/lists/*
COPY files/db_stub.py /opt/app/db_stub.py
COPY files/check_db_connection.sh /opt/app/check_db_connection.sh
COPY files/start.sh /start.sh
COPY files/check.sh /task/check.sh
RUN chmod +x /opt/app/db_stub.py /opt/app/check_db_connection.sh /start.sh /task/check.sh
CMD ["/start.sh"]
