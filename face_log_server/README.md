# Hikvision Face Log Server

Production-ready Flask server that receives face recognition logs from Hikvision devices and stores them in MySQL.

## Project Structure

```
face_log_server/
├── app.py              # Application entry point
├── config.py           # Configuration (env vars)
├── models.py           # Database models
├── face_api/
│   ├── __init__.py     # Blueprint
│   └── routes.py       # API endpoints
├── logs/               # Rotating logs + incoming.log
├── requirements.txt
├── run_server.bat      # Windows startup script
├── .env.example        # Example env config
└── README.md
```

## Quick Start

1. **Create MySQL database and user:**

```sql
CREATE DATABASE face_logs_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'face_log_user'@'%' IDENTIFIED BY 'your_password';
GRANT ALL ON face_logs_db.* TO 'face_log_user'@'%';
FLUSH PRIVILEGES;
```

2. **Configure environment:**

```bash
copy .env.example .env
# Edit .env with your MySQL credentials
```

3. **Install dependencies:**

```bash
pip install -r requirements.txt
```

4. **Run:**

```bash
python app.py
```

Or use `run_server.bat` (run as Administrator for port 80).

## Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/face-api/receive` | Receive face logs (JSON, XML, raw) |
| GET | `/face-api/logs` | List latest 100 logs |
| GET | `/health` | Health check |

## Hikvision Device Configuration

Configure your Hikvision device to POST to:

```
http://mydomain.com/face-api/receive
```

## Testing (curl)

```bash
# POST JSON
curl -X POST http://localhost/face-api/receive -H "Content-Type: application/json" -d "{\"personName\":\"John Doe\",\"eventTime\":\"2025-02-21T10:30:00\"}"

# GET logs
curl http://localhost/face-api/logs
```

## Windows Server Deployment

1. Install Python 3.10+
2. Run as Administrator for port 80
3. Use a process manager or Windows Task Scheduler for auto-restart
4. Configure firewall to allow port 80
