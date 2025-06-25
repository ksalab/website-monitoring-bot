# Используем Python 3.10 slim для уменьшения размера образа
FROM python:3.10-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем requirements.txt и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код бота
COPY bot.py .
COPY modules/ modules/
COPY VERSION .

# Создаём директории для данных и логов
RUN mkdir -p /app/data /app/logs

# Устанавливаем права
RUN chown -R nobody:nogroup /app/data /app/logs

# Запускаем бот от пользователя nobody для безопасности
USER nobody

# Команда для запуска бота
CMD ["python", "bot.py"]
