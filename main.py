import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from app import create_app
from config import Config

app = create_app(Config)

if __name__ == "__main__":
    # Run the application
    port = int(os.getenv('PORT', 8000))
    debug = os.getenv('FLASK_ENV', 'development') == 'development'

    print(f"Starting SmartScheduler backend...")
    print(f"Backend URL: http://localhost:{port}")
    print(f"Frontend URL: {app.config.get('FRONTEND_BASE_URL')}")

    # Check if email is configured
    if app.config.get('MAIL_SERVER'):
        print(f"Email configured: {app.config.get('MAIL_SERVER')}:{app.config.get('MAIL_PORT')}")
    else:
        print("WARNING: Email server not configured. Email verification will not work.")

    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug
    )
