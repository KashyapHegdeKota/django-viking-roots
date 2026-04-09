#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input

# Fix broken faked migrations
python fix_heritage_tables.py

python manage.py migrate
