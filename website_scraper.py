import requests
from bs4 import BeautifulSoup

def enrich_from_website(startups):
    for s in startups:
        if not s["website"] or s["description"]:
            continue
        try:
            html = requests.get(s["website"], timeout=5).text
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(" ", strip=True)
            s["description"] = text[:300]
        except Exception:
            pass
    return startups