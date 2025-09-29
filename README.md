# Phyllis Columns Uploader (Flask, Self-hosted WordPress)

Local Flask app to step through scanned columns, show PDF/DOCX, edit text,
and one-click publish to self-hosted WordPress using REST API + Application Passwords.

## Prereqs (macOS)
brew install tesseract poppler
pip install -r requirements.txt

## Configure
Create a .env file with the following:
- SOURCE_ROOT
- WP_BASE (https://phyllisschlafly.com)
- WP_USERNAME, WP_APP_PASSWORD
- WP_AUTHOR_NAME, WP_CATEGORY_NAME (defaults to "Phyllis Schlafly Report Column")
- WP_CATEGORY_ID (defaults to "72"), WP_CATEGORY_SLUG (defaults to "phyllis-schlafly-report-column")
- WP_FEATURED_IMAGE_ID (optional)

## Run
conda activate cols
export FLASK_APP=app.app:app
flask run --port 5055 --reload