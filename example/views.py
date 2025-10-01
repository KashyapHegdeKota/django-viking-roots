# example/views.py
from datetime import datetime

from django.http import HttpResponse

# indexing
def index(request):
    now = datetime.now()
    html = f'''
    <html>
        <body>
            <h1>Hello from Vercel!</h1>
            <p>The current time is { now }.</p>
        </body>
    </html>
    '''
    return HttpResponse(html)

def hello_world(request):
    return HttpResponse("Hello, World!")