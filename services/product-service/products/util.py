import requests
from django.conf import settings

USER_SERVICE_URL = settings.USER_SERVICE_URL

def fetch_user_data(user_id, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = requests.get(f"{USER_SERVICE_URL}/users/{user_id}/", headers=headers)
    response.raise_for_status()
    return response.json()

# TODO: Change this such that authentication is handled by api gateway and userid is injected to request.