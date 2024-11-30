import json


def get_cookies_from_file():
    with open('scrapers/data/cookies.json') as f:
        cookies_list = json.load(f)

    cookies_kv = {}
    for cookie in cookies_list:
        cookies_kv[cookie['name']] = cookie['value']

    return cookies_kv


cookies = get_cookies_from_file()


def get_cookies(**kwargs):
    return cookies
