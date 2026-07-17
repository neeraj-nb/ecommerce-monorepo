import requests
from django.conf import settings

USER_SERVICE_URL = settings.USER_SERVICE_URL
PRODUCT_SERVICE_URL = settings.PRODUCT_SERVICE_URL


def fetch_user_data(user_id, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = requests.get(f"{USER_SERVICE_URL}/users/{user_id}/", headers=headers, timeout=5)
    response.raise_for_status()
    return response.json()


def fetch_product_data(product_id, token=None):
    """Read a product's current data from product-service.

    Used to snapshot name/price onto a cart line at add time. This is a
    synchronous *read* (queries are fine to do inline); the stock *mutation*
    stays asynchronous and event-driven via the inventory saga.
    """
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = requests.get(
        f"{PRODUCT_SERVICE_URL}/products/{product_id}/", headers=headers, timeout=5
    )
    response.raise_for_status()
    return response.json()

# TODO: Change this such that authentication is handled by api gateway and userid is injected to request.
# TODO (event-driven upgrade): replace fetch_product_data with a local product
# read-model kept in sync via product.created/updated events, to drop the
# synchronous dependency on product-service at cart time.
