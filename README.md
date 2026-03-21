# THPocker Board

Покерный турнирный борд на Flask. Отображает таймер уровней, блайнды, количество игроков и статистику фишек в реальном времени.

## Локальный запуск

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

mkdir -p logs

python app.py
```

Приложение доступно на http://localhost:5000

## Настройка

В [app.py](app.py) перед деплоем замените:

```python
app.secret_key = 'super_secret_key'   # сгенерируйте случайную строку
ADMIN_PASSWORD = 'admin123'            # установите надёжный пароль
TIMEZONE_OFFSET = 4                    # UTC+N для вашего города
```

## Деплой на сервер

### 1. Первый деплой

**Клонируйте репозиторий на сервере:**
```bash
cd /var/www
sudo git clone https://github.com/vvo1d/thpocker_board.git
sudo chown -R www-data:www-data /var/www/thpocker_board
```

**Создайте папку для логов** (обязательно, иначе приложение не запустится):
```bash
sudo mkdir -p /var/www/thpocker_board/logs
sudo chown www-data:www-data /var/www/thpocker_board/logs
```

**Установите зависимости:**
```bash
cd /var/www/thpocker_board
sudo -u www-data python3 -m venv venv
sudo -u www-data venv/bin/pip install -r requirements.txt
```

**Настройте systemd сервис:**
```bash
sudo cp thpocker_board.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable thpocker_board
sudo systemctl start thpocker_board
```

**Настройте Nginx:**
```bash
sudo cp nginx.conf /etc/nginx/sites-available/thpocker_board
sudo ln -s /etc/nginx/sites-available/thpocker_board /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx
```

### 2. Обновление

```bash
cd /var/www/thpocker_board
sudo git pull
sudo systemctl restart thpocker_board
```

### 3. Диагностика

```bash
# Статус сервиса
sudo systemctl status thpocker_board

# Логи
sudo journalctl -u thpocker_board -n 50 --no-pager

# Если порт 8000 занят другим процессом
sudo fuser -k 8000/tcp
sudo systemctl restart thpocker_board
```

## Страницы

| URL | Описание |
|-----|----------|
| `/` | Борд для телевизора/клиентов |
| `/admin` | Панель управления турниром |
| `/structure` | Структура уровней |
