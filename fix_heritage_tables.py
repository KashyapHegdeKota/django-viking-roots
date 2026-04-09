import os
import sys
import django

def fix_heritage_tables():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
    django.setup()
    
    from django.db import connection
    
    with connection.cursor() as cursor:
        # Check if heritage_userprofile exists, and create it if not
        try:
            cursor.execute("SELECT 1 FROM heritage_userprofile LIMIT 1;")
            print("Table heritage_userprofile already exists.")
        except Exception:
            print("Table heritage_userprofile is missing. Re-applying heritage migrations.")
            connection.rollback()  # Reset transaction
            
            # Since migrations were "faked" we need to un-fake them
            import subprocess
            subprocess.run([sys.executable, "manage.py", "migrate", "heritage", "zero", "--fake"])
            subprocess.run([sys.executable, "manage.py", "migrate", "heritage"])

if __name__ == "__main__":
    fix_heritage_tables()
