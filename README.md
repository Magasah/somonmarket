# Somon Market

Telegram WebApp маркетплейс игровых аккаунтов (FastAPI + aiogram 3 + SPA).

---

## Деплой на сервере (Bothost / VPS с Python)

### 1. Клонировать репозиторий

```bash
git clone https://github.com/Magasah/somonmarket.git
cd somonmarket
```

### 2. Создать виртуальное окружение и установить зависимости

```bash
python3 -m venv .venv
source .venv/bin/activate      # Linux/macOS
# или на Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Создать `.env` файл

```bash
cp .env.example .env
nano .env   # или любой текстовый редактор
```

Заполнить `.env`:

```env
BOT_TOKEN=ваш_токен_от_BotFather
ADMIN_ID=ваш_telegram_id
ADMIN_IDS=id1,id2
WEBAPP_URL=https://ваш-домен-или-ngrok.com
WEB_APP_URL=https://ваш-домен-или-ngrok.com
ADMIN_SECRET=ваш_секретный_ключ_админа
```

> `WEBAPP_URL` — публичный HTTPS адрес, по которому Telegram откроет WebApp.  
> На Bothost это обычно выдаётся автоматически. Если используется ngrok: `https://xxxx.ngrok-free.app`

### 4. Запустить FastAPI сервер

```bash
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 5. Запустить Telegram бота (в отдельном терминале/процессе)

```bash
source .venv/bin/activate
python bot.py
```

### 6. Запустить оба процесса через PM2 (рекомендуется на VPS)

```bash
# Установить PM2
npm install pm2 -g

# Запустить FastAPI
pm2 start "uvicorn main:app --host 0.0.0.0 --port 8000" --name somon-api

# Запустить бота
pm2 start "python bot.py" --name somon-bot --interpreter python3

# Автозапуск при перезагрузке
pm2 save
pm2 startup
```

### 7. Проверить работу

```bash
curl http://localhost:8000/api/health
# Ответ: {"status":"Somon Market Backend is running!"}
```

---

## Структура проекта

```
├── main.py              # FastAPI backend (все API эндпоинты)
├── bot.py               # Telegram бот (aiogram 3)
├── requirements.txt     # Python зависимости
├── .env.example         # Шаблон переменных окружения
├── database/            # SQLAlchemy модели и DB утилиты
├── handlers/            # Обработчики бота
├── services/            # Broadcaster (SSE уведомления)
├── templates/           # HTML шаблоны (SPA + Admin)
│   ├── index.html       # Основной SPA (Telegram WebApp)
│   └── admin.html       # Панель администратора
├── static/              # CSS, JS, иконки игр
└── uploads/faces/       # Загруженные фото (KYC верификация)
```

---

## API эндпоинты

| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/api/health` | Проверка работы сервера |
| POST | `/api/users/register` | Регистрация пользователя |
| GET | `/api/users/{user_id}` | Данные пользователя |
| POST | `/api/items` | Создать объявление |
| GET | `/api/items` | Список активных товаров |
| DELETE | `/api/items/{id}` | Удалить товар |
| POST | `/api/orders` | Создать заказ (купить товар) |
| POST | `/api/orders/{id}/confirm` | Подтвердить получение |
| POST | `/api/orders/{id}/dispute` | Открыть спор |
| POST | `/api/reviews` | Оставить отзыв |
| GET | `/api/admin/stats` | Статистика (X-Admin-Token) |

---

## Переменные окружения

| Переменная | Описание |
|-----------|----------|
| `BOT_TOKEN` | Токен Telegram бота от @BotFather |
| `ADMIN_ID` | Telegram ID главного администратора |
| `ADMIN_IDS` | Telegram ID всех администраторов (через запятую) |
| `WEBAPP_URL` | Публичный HTTPS URL WebApp |
| `ADMIN_SECRET` | Токен для доступа к /api/admin/* |
