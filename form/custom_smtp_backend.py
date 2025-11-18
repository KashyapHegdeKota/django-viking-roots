import ssl
from django.core.mail.backends.smtp import EmailBackend

class UnsafeBrevoEmailBackend(EmailBackend):
    """
    Custom SMTP backend that disables SSL certificate verification
    to work around macOS + Python 3.12 certificate issues.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Inject insecure SSL context
        self.ssl_context = ssl._create_unverified_context()