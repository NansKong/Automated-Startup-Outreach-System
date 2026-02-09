"""
Y Combinator India startups scraper - Optimized for 50+ results.
Uses official YC API and directory scraping.
"""

import requests
import json
import time
from typing import List, Dict
from base import normalize_startup, logger, clean_text

YC_API_URL = "https://api.ycombinator.com/v0.1/companies"
YC_DIRECTORY_URL = "https://www.ycombinator.com/companies"
BATCHES = ["W24", "S23", "W23", "S22", "W22", "S21", "W21", "S20", "W20"]


def fetch_yc_api(location: str = "india", limit: int = 50) -> List[Dict]:
    """
    Fetch from Y Combinator's public API.
    """
    startups = []
    offset = 0
    
    while len(startups) < limit:
        params = {
            "location": location,
            "offset": offset,
            "limit": 50
        }
        
        try:
            res = requests.get(
                YC_API_URL,
                params=params,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0",
                    "Accept": "application/json"
                },
                timeout=15
            )
            
            if res.status_code != 200:
                break
            
            data = res.json()
            companies = data.get("companies", [])
            
            if not companies:
                break
            
            for company in companies:
                try:
                    # Filter for India specifically
                    locations = company.get("locations", [])
                    is_india = any(
                        "india" in loc.get("country", "").lower() or 
                        "india" in loc.get("city", "").lower()
                        for loc in locations
                    )
                    
                    if not is_india and location == "india":
                        continue
                    
                    website = company.get("website", "") or company.get("url", "")
                    if website and not website.startswith("http"):
                        website = "https://" + website
                    
                    startups.append(normalize_startup(
                        company_name=company.get("name", ""),
                        website=website,
                        description=company.get("description", "") or company.get("one_liner", ""),
                        source=f"yc_{company.get('batch', 'unknown')}",
                        confidence="high",
                        location=", ".join([f"{loc.get('city', '')}, {loc.get('country', '')}" for loc in locations]),
                        funding_stage="seed" if "S" in company.get("batch", "") else "series_a",
                        industry=", ".join(company.get("industries", []))
                    ))
                    
                    if len(startups) >= limit:
                        break
                        
                except Exception as e:
                    logger.debug(f"Company parse error: {e}")
                    continue
            
            offset += len(companies)
            time.sleep(0.3)
            
            if len(companies) < 50:
                break
                
        except Exception as e:
            logger.error(f"YC API error: {e}")
            break
    
    return startups


def scrape_yc_directory_by_batch(limit: int = 50) -> List[Dict]:
    """
    Scrape YC directory by batch for India companies.
    """
    from bs4 import BeautifulSoup
    
    startups = []
    
    for batch in BATCHES:
        if len(startups) >= limit:
            break
            
        url = f"{YC_DIRECTORY_URL}?batch={batch}&location=India"
        page = 1
        
        while len(startups) < limit:
            paginated_url = f"{url}&page={page}"
            
            try:
                res = requests.get(
                    paginated_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.0"
                    },
                    timeout=10
                )
                
                if res.status_code != 200:
                    break
                
                soup = BeautifulSoup(res.text, "html.parser")
                
                # Look for JSON data in script tags (Next.js)
                scripts = soup.find_all("script", type="application/json")
                companies = []
                
                for script in scripts:
                    try:
                        data = json.loads(script.string)
                        # Navigate through Next.js data structure
                        if "props" in data and "pageProps" in data["props"]:
                            companies = data["props"]["pageProps"].get("companies", [])
                            break
                    except:
                        continue
                
                # Fallback to HTML parsing
                if not companies:
                    cards = soup.select("[data-testid='company-card'], .company-card, ._company")
                    for card in cards:
                        name_elem = card.select_one("h3, h4, .company-name")
                        if name_elem:
                            companies.append({
                                "name": name_elem.get_text(strip=True),
                                "website": "",
                                "description": ""
                            })
                
                for company in companies:
                    try:
                        name = company.get("name") or company.get("company_name", "")
                        if not name:
                            continue
                        
                        # Verify India connection
                        locations = company.get("locations", [])
                        if locations:
                            is_india = any("india" in str(loc).lower() for loc in locations)
                            if not is_india:
                                continue
                        
                        website = company.get("website", "") or company.get("url", "")
                        if website and not website.startswith("http"):
                            website = "https://" + website
                        
                        startups.append(normalize_startup(
                            company_name=clean_text(name),
                            website=website,
                            description=company.get("description", "") or company.get("one_liner", ""),
                            source=f"yc_{batch}",
                            confidence="high",
                            location="India",
                            funding_stage="seed" if batch.startswith("S") else "series_a"
                        ))
                        
                    except Exception as e:
                        logger.debug(f"Company parse error: {e}")
                        continue
                
                page += 1
                time.sleep(0.5)
                
                # Check for next page
                next_btn = soup.select_one("[data-testid='next-page'], .next, a[rel='next']")
                if not next_btn or "disabled" in str(next_btn):
                    break
                    
            except Exception as e:
                logger.error(f"Batch {batch} scrape error: {e}")
                break
    
    return startups


def collect_yc_india(limit: int = 50) -> List[Dict]:
    """
    Collect Y Combinator startups based in India.
    Uses API first, then directory scraping.
    """
    logger.info(f"Fetching YC India startups (target: {limit})...")
    
    # Try API first
    startups = fetch_yc_api("india", limit)
    logger.info(f"YC API fetch: {len(startups)} startups")
    
    # Supplement with directory scraping
    if len(startups) < limit:
        remaining = limit - len(startups)
        directory_startups = scrape_yc_directory_by_batch(remaining)
        
        existing_ids = {s["startup_id"] for s in startups}
        for s in directory_startups:
            if s["startup_id"] not in existing_ids:
                startups.append(s)
                existing_ids.add(s["startup_id"])
        
        logger.info(f"After directory scrape: {len(startups)} startups")
    
    return startups[:limit]


if __name__ == "__main__":
    results = collect_yc_india(50)
    print(f"Collected {len(results)} YC startups")
    for s in results[:5]:
        print(f"- {s['company_name']} ({s.get('funding_stage', 'unknown')})")