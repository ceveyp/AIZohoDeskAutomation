import requests
import json
import sys

from app.apparel_magic.client import ApparelMagicClient
from app.apparel_magic.client_async import AsyncApparelMagicClient
from app.settings import get_settings

settings = get_settings()

HEADERS = {"X-API-Key": settings.ii_product_search_api_key}

def search(query, limit=10):
    resp = requests.get(
        f"{settings.ii_hostname}/api/products/search",
        params={"q": query, "limit": limit},
        headers=HEADERS,
    )
    if resp.status_code != 200:
        print(f"ERROR {resp.status_code}: {resp.text}")
        return []
    results = resp.json()
    print(f'Search: "{query}" — {len(results)} result(s)')
    for i, r in enumerate(results, 1):
        print(f"  {i}. [{r['product_id']}] {r['description']}")
    print()
    return results

if __name__ == "__main__":
    pass
    # query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "hoodie"
    # search(query)
    # AsyncApparelMagicClient().
