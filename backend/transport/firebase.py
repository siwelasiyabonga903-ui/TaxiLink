import firebase_admin

from django.conf import settings
from firebase_admin import credentials


def get_firebase_app():
    try:
        return firebase_admin.get_app()
    except ValueError:
        pass

    credentials_path = (
        settings.FIREBASE_CREDENTIALS_PATH
    )

    if not credentials_path:
        return None

    cred = credentials.Certificate(
        credentials_path
    )

    return firebase_admin.initialize_app(
        cred
    )