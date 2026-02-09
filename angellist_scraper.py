"""
AngelList (Wellfound) scraper - Optimized for 50+ results.
Uses multiple strategies: search, filtering, and API endpoints.
"""

import requests
import json
import re
import time
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from base import normalize_startup, logger, clean_text

BASE_URL = "https://wellfound.com"
GRAPHQL_URL = "https://wellfound.com/graphql"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://wellfound.com/companies",
    "X-Requested-With": "XMLHttpRequest"
}


def get_graphql_startups(limit: int = 50) -> List[Dict]:
    """
    Fetch startups using Wellfound's GraphQL API.
    More reliable than HTML scraping.
    """
    startups = []
    cursor = None
    
    query = """
    query SearchCompanies($cursor: String, $filters: CompanySearchFilters!) {
      companySearch(first: 20, after: $cursor, filters: $filters) {
        edges {
          node {
            id
            name
            slug
            websiteUrl
            oneLiner
            locations
            industries
            fundingStage
            employeeCount
          }
          cursor
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
    """
    
    while len(startups) < limit:
        variables = {
            "filters": {
                "locations": ["india"],
                "companyStages": ["seed", "series_a", "series_b", "early_stage"]
            },
            "cursor": cursor
        }
        
        try:
            res = requests.post(
                GRAPHQL_URL,
                json={"query": query, "variables": variables},
                headers={**HEADERS, "Content-Type": "application/json"},
                timeout=15
            )
            
            if res.status_code != 200:
                break
                
            data = res.json()
            companies = data.get("data", {}).get("companySearch", {})
            edges = companies.get("edges", [])
            
            for edge in edges:
                node = edge.get("node", {})
                if not node:
                    continue
                    
                startups.append(normalize_startup(
                    company_name=node.get("name", ""),
                    website=node.get("websiteUrl", ""),
                    description=node.get("oneLiner", ""),
                    source="angellist_graphql",
                    confidence="high",
                    location="India",
                    funding_stage=node.get("fundingStage", ""),
                    employee_count=str(node.get("employeeCount", ""))
                ))
                
                if len(startups) >= limit:
                    break
            
            page_info = companies.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")
            
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"GraphQL fetch error: {e}")
            break
    
    return startups


def scrape_html_fallback(limit: int = 50) -> List[Dict]:
    """
    Fallback HTML scraping when API fails.
    Uses multiple location filters to get more results.
    """
    startups = []
    locations = ["india", "bangalore", "mumbai", "delhi", "hyderabad", "pune", "chennai"]
    
    for location in locations:
        if len(startups) >= limit:
            break
            
        page = 1
        location_count = 0
        max_per_location = limit // len(locations) + 10
        
        while location_count < max_per_location and len(startups) < limit:
            url = f"{BASE_URL}/companies?page={page}&locations={location}&stage=seed&stage=series_a"
            
            try:
                res = requests.get(url, headers=HEADERS, timeout=10)
                if res.status_code != 200:
                    break
                
                soup = BeautifulSoup(res.text, "html.parser")
                
                # Multiple selector strategies
                cards = (
                    soup.select("[data-test='company-card']") or
                    soup.select(".companyCard") or
                    soup.select("[class*='companyCard']") or
                    soup.select("div[class*='styles_companyCard']")
                )
                
                if not cards:
                    # Try JSON embedded in script
                    scripts = soup.find_all("script", type="application/json")
                    for script in scripts:
                        try:
                            data = json.loads(script.string)
                            if "props" in data:
                                # Extract from Next.js data
                                pass
                        except:
                            continue
                    break
                
                for card in cards:
                    try:
                        name_elem = (
                            card.select_one("h2") or
                            card.select_one("[data-test='company-name']") or
                            card.select_one("a[class*='name']") or
                            card.find("a")
                        )
                        
                        if not name_elem:
                            continue
                            
                        name = clean_text(name_elem.get_text())
                        link = name_elem.get("href", "") if name_elem.name == "a" else ""
                        
                        # Extract website if available
                        website = ""
                        website_elem = card.select_one("a[href^='http']")
                        if website_elem:
                            website = website_elem.get("href", "")
                        
                        # Extract description
                        desc = ""
                        desc_elem = (
                            card.select_one("[data-test='company-description']") or
                            card.select_one("p[class*='description']") or
                            card.select_one("p")
                        )
                        if desc_elem:
                            desc = clean_text(desc_elem.get_text())
                        
                        if name and len(name) > 1:
                            startups.append(normalize_startup(
                                company_name=name,
                                website=website or (f"{BASE_URL}{link}" if link else ""),
                                description=desc,
                                source=f"angellist_{location}",
                                confidence="high"
                            ))
                            location_count += 1
                            
                    except Exception as e:
                        logger.debug(f"Card parsing error: {e}")
                        continue
                
                page += 1
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"HTML scrape error for {location}: {e}")
                break
    
    return startups


def collect_angellist_startups(limit: int = 50) -> List[Dict]:
    """
    Collect startups from AngelList/Wellfound.
    Tries GraphQL API first, falls back to HTML scraping.
    """
    logger.info(f"Fetching AngelList startups (target: {limit})...")
    
    # Try GraphQL first
    startups = get_graphql_startups(limit)
    logger.info(f"GraphQL fetch: {len(startups)} startups")
    
    # Fallback to HTML if needed
    if len(startups) < limit:
        remaining = limit - len(startups)
        html_startups = scrape_html_fallback(remaining)
        
        # Deduplicate
        existing_ids = {s["startup_id"] for s in startups}
        for s in html_startups:
            if s["startup_id"] not in existing_ids:
                startups.append(s)
                existing_ids.add(s["startup_id"])
        
        logger.info(f"After HTML fallback: {len(startups)} startups")
    
    return startups[:limit]


if __name__ == "__main__":
    results = collect_angellist_startups(50)
    print(f"Collected {len(results)} startups")
    for s in results[:5]:
        print(f"- {s['company_name']} ({s.get('website', 'no website')})")