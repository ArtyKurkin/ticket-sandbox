#!/usr/bin/env bash
set -e

# Создаём пользователя, под которым работает приложение
id appuser >/dev/null 2>&1 || useradd -m -s /bin/bash appuser

mkdir -p /opt/myapp/data /opt/myapp/output

# Конфиг приложения
cat > /opt/myapp/config.ini <<'EOF'
[app]
name = myapp
data_dir = /opt/myapp/data
EOF

# Файл данных
cat > /opt/myapp/data/records.txt <<'EOF'
record-1
record-2
record-3
record-4
EOF

# run.sh уже скопирован Dockerfile'ом в /opt/myapp/run.sh

# === ИМИТАЦИЯ РАСПАКОВКИ TAR ПОД ROOT ===
# Всё принадлежит root (как после tar xf под root)
chown -R root:root /opt/myapp

# ПОЛОМКА 1: run.sh без бита выполнения у "чужого" пользователя?
# Нет — оставим исполняемым, чтобы фокус был на правах данных, а не на +x.
chmod 755 /opt/myapp/run.sh

# ПОЛОМКА 2: конфиг с правами 600 (только владелец-root читает)
chmod 600 /opt/myapp/config.ini

# ПОЛОМКА 3: на директорию data снят бит x (нельзя войти/прочитать содержимое)
chmod 600 /opt/myapp/data
# файл данных сам по себе читаем, но без x на каталоге до него не добраться
chmod 644 /opt/myapp/data/records.txt

# ПОЛОМКА 4: output принадлежит root и закрыт для записи остальным
chown root:root /opt/myapp/output
chmod 755 /opt/myapp/output

rm -f /start.sh
tail -f /dev/null
