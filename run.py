from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / '.env')
except ImportError:
    pass

from waitress import serve
from app import create_app
import logging

# logs papkasini yaratish (Render va boshqa muhitlarda mavjud bo'lmasa)
logs_dir = Path(__file__).resolve().parent / 'logs'
logs_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(logs_dir / 'app.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

app = create_app()

# Nashr faqat qo'lda: flask release (markazda yangi versiya yaratilmaydi ishga tushganda).
if __name__ == '__main__':
    try:
        from app.services.sse_client import start_sse_client
        start_sse_client(app)
    except Exception as e:
        logging.getLogger(__name__).warning("SSE client ishga tushmadi: %s", e)

    serve(app, host="0.0.0.0", port=80)
