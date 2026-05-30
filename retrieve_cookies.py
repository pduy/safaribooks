import json

# See: https://github.com/lorenzodifuccia/safaribooks/issues/358

try:
    from safaribooks import COOKIES_FILE
except ImportError:
    COOKIES_FILE = "cookies.json"

try:
    import browser_cookie3
except ImportError:
    raise ImportError("Please install browser_cookie3: uv sync")

def get_oreilly_cookies():
    cj = browser_cookie3.load()
    cookies = {}
    for c in cj:
        # Only keep O'Reilly domain cookies
        domain = getattr(c, 'domain', '') or ''
        if 'oreilly' in domain:
            cookies[c.name] = c.value
    return cookies

def main():
    cookies = get_oreilly_cookies()
    if not cookies:
        print("No O'Reilly cookies found. Make sure you're logged into")
        print("https://learning.oreilly.com in your browser.")
        return
    with open(COOKIES_FILE, "w") as f:
        json.dump(cookies, f)
    print(f"Saved {len(cookies)} cookies to {COOKIES_FILE}")

if __name__ == "__main__":
    main()