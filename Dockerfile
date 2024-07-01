# Используем образ joyzoursky/python-chromedriver
FROM joyzoursky/python-chromedriver:3.9

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install -r requirements.txt

# Копируем код приложения в контейнер
COPY . /app

WORKDIR /app

# Устанавливаем переменные окружения
ENV TELEGRAM_TOKEN=<your_telegram_token>
ENV DB_NAME=<your_db_name>
ENV DB_USER=<your_db_user>
ENV DB_PASSWORD=<your_db_password>
ENV DB_HOST=<your_db_host>
ENV DB_PORT=<your_db_port>

# Запускаем приложение
CMD ["python", "main.py"]
