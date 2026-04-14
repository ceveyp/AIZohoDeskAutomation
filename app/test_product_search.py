from app.settings import get_settings

import requests

settings = get_settings()

HEADERS = {"X-API-Key": settings.ii_product_search_api_key}


def search(q=None, team=None, category=None, color=None, season=None, in_stock=None, limit=20):
    params = {}
    if q: params["q"] = q
    if team: params["team"] = team
    if category: params["category"] = category
    if color: params["color"] = color
    if season: params["season"] = season
    if in_stock is True:
        params["in_stock"] = "true"
    elif in_stock is False:
        params["in_stock"] = "false"
    if limit: params["limit"] = limit

    resp = requests.get(
        f"{settings.ii_hostname}/api/products/search",
        params=params,
        headers=HEADERS,
    )
    if resp.status_code != 200:
        print(f"ERROR {resp.status_code}: {resp.text}")
        return []
    results = resp.json()
    filters = " | ".join(f"{k}={v}" for k, v in params.items() if k != "limit")
    print(f'Search: {filters} — {len(results)} result(s)')
    for i, r in enumerate(results, 1):
        title = r.get("web_title") or r["description"]
        print(f"  {i}. [{r['product_id']}] {title}")
    print()
    return results


if __name__ == "__main__":
    print("=== Text search ===")
    search(q="hoodie", limit=5)

    print("=== Team search ===")
    search(team="Mississippi State", limit=5)

    print("=== Team + category ===")
    search(team="Mississippi State", category="hoodie", limit=5)

    print("=== Team + in stock ===")
    search(team="Alabama", in_stock=True, limit=5)

    print("=== Color search ===")
    search(color="burnt orange", category="hoodie", limit=5)

    print("=== Season search ===")
    search(season="Fall 25", limit=5)
