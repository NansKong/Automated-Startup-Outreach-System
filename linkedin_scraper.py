"""
LinkedIn startup discovery - Fixed to only return real companies
REMOVED: Fake stealth startup generation
"""

import requests
import json
import re
import time
from typing import List, Dict
from base import normalize_startup, logger, clean_text, is_valid_company
import os
from dotenv import load_dotenv

LINKEDIN_SEARCH_URL = "https://www.linkedin.com/voyager/api/search/blended"

load_dotenv()


def get_linkedin_cookies() -> Dict[str, str]:
    """Get LinkedIn authentication cookies."""
    return {
        "li_at": os.getenv("LI_AT"),
        "JSESSIONID": os.getenv("JSESSIONID")
    }


def search_linkedin_startups(keywords: List[str], limit: int = 20) -> List[Dict]:
    """
    Search LinkedIn for real startup companies only.
    """
    startups = []
    cookies = get_linkedin_cookies()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0",
        "Accept": "application/vnd.linkedin.normalized+json+2.1",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    
    for keyword in keywords:
        if len(startups) >= limit:
            break
            
        start = 0
        while len(startups) < limit:
            params = {
                "keywords": keyword,
                "origin": "GLOBAL_SEARCH_HEADER",
                "q": "blended",
                "start": start,
                "count": 20
            }
            
            try:
                res = requests.get(
                    LINKEDIN_SEARCH_URL,
                    params=params,
                    headers=headers,
                    cookies=cookies,
                    timeout=15
                )
                
                if res.status_code != 200:
                    break
                
                data = res.json()
                elements = data.get("data", {}).get("elements", [])
                
                if not elements:
                    break
                
                for element in elements:
                    try:
                        company = element.get("company", {})
                        if not company:
                            continue
                        
                        name = company.get("name", "")
                        if not name:
                            continue
                        
                        # Skip stealth/generic names
                        if not is_valid_company(name, "", "linkedin")[0]:
                            continue
                        
                        # Check for India presence
                        locations = company.get("locations", [])
                        is_india = any(
                            "india" in str(loc).lower() for loc in locations
                        )
                        
                        if not is_india:
                            continue
                        
                        website = ""
                        websites = company.get("websites", [])
                        if websites:
                            website = websites[0].get("url", "")
                        
                        startup = normalize_startup(
                            company_name=name,
                            website=website,
                            description=company.get("description", ""),
                            source="linkedin_search",
                            confidence="medium",
                            location="India",
                            industry=", ".join(company.get("industries", [])),
                            employee_count=str(company.get("staffCount", ""))
                        )
                        
                        if startup:
                            startups.append(startup)
                        
                        if len(startups) >= limit:
                            break
                            
                    except Exception as e:
                        logger.debug(f"Element parse error: {e}")
                        continue
                
                start += 20
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"LinkedIn search error: {e}")
                break
    
    return startups


# REMOVED: detect_stealth_startups() function - it was generating fake data


def collect_linkedin_startups(limit: int = 20, use_api: bool = False) -> List[Dict]:
    """
    Collect startups from LinkedIn - ONLY real companies, no fake stealth entries.
    """
    logger.info(f"Fetching LinkedIn startups (target: {limit})...")
    
    startups = []
    
    if use_api:
        # Only search for real companies
        keywords = [
            "startup india", 
            "fintech india", 
            "saas india", 
            "ai startup india"
        ]
        api_startups = search_linkedin_startups(keywords, limit)
        startups.extend(api_startups)
        logger.info(f"LinkedIn API: {len(startups)} startups")
    
    # REMOVED: No more fake stealth signal generation
    # If API doesn't return enough, we simply return what we have
    
    if len(startups) == 0:
        logger.warning("LinkedIn returned no results. No fake data will be generated.")
    
    return startups[:limit]


if __name__ == "__main__":
    results = collect_linkedin_startups(20)
    print(f"Collected {len(results)} LinkedIn startups")
    for s in results[:5]:
        print(f"- {s['company_name']} (confidence: {s['confidence']})")