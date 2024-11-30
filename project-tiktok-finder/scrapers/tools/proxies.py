import json

PROXY = {}

with open("scrapers/data/proxies.json", "r") as f:
    PROXY = json.load(f)


def get_proxies():
    return [PROXY]
