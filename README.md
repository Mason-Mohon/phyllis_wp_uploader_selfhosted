# Phyllis Columns Uploader (Flask, Self-hosted WordPress)

Local Flask app to step through scanned columns, show PDF/DOCX, edit text,
and one-click publish to self-hosted WordPress using REST API + Application Passwords.

## Prereqs (macOS)
brew install tesseract poppler
pip install -r requirements.txt

## Configure
Copy .env.example to .env and fill:
- SOURCE_ROOT
- WP_BASE (https://phyllisschlafly.com)
- WP_USERNAME, WP_APP_PASSWORD
- WP_AUTHOR_NAME, WP_CATEGORY_NAME

## Run
export FLASK_APP=app.app:app
flask run --port 5055 --reload