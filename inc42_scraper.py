"""
Inc42 Scraper - Optimized for fetching 50+ startups with rich data
Fetches from multiple Inc42 endpoints: startups to watch, funding news, and ecosystem lists
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import random
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

from base import normalize_startup

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Inc42 endpoints that list startups
INC42_ENDPOINTS = [
    "https://inc42.com/startups/",
    "https://inc42.com/startups/30-startups-to-watch/",
    "https://inc42.com/datalabs/startup-funding-report/",
    "https://inc42.com/features/",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

def extract_company_from_title(title: str) -> Optional[str]:
    title = title.strip()

    patterns = [
        r"^How\s+(.+?)\s+Is\s+",
        r"^How\s+(.+?)\s+Has\s+",
        r"^How\s+(.+?)\s+Uses\s+",
        r"^How\s+(.+?)\s+Helps\s+",
        r"^Why\s+(.+?)\s+",
        r"^(.+?)’s\s+",
        r"^(.+?)'s\s+",
        r"^Inside\s+([A-Z][A-Za-z0-9&.\-]{2,20})$",
    ]

    for pattern in patterns:
        match = re.search(pattern, title, flags=re.IGNORECASE)
        if not match:
            continue

        name = match.group(1).strip()

        # reject phrases
        if len(name.split()) > 3:
            return None

        INVALID_NAMES = {
            "gig economy",
            "startup",
            "startups",
            "guide",
            "funding",
            "economy",
            "features",
            "decoding",
            "understanding",
        }

        if name.lower() in INVALID_NAMES:
            return None

        return name
    COUNTRY_BLOCKLIST = {"india", "bharat", "indian", "usa", "china", "europe"}

    if name.lower() in COUNTRY_BLOCKLIST:
        return None


    return None



def clean_html(text: str) -> str:
    """Clean HTML tags and normalize whitespace"""
    if not text:
        return ""
    text = re.sub(r"<img[^>]*>", " ", text)
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def fetch_page(url: str, retries: int = 3, delay: float = 1.0) -> Optional[str]:
    """
    Fetch page content with retry logic and rate limiting
    """
    for attempt in range(retries):
        try:
            time.sleep(delay + random.uniform(0, 1))  # Polite delay
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.warning(f"Attempt {attempt + 1}/{retries} failed for {url}: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                logger.error(f"Failed to fetch {url} after {retries} attempts")
                return None
    return None

def extract_startup_from_article(article_html: str, source_url: str) -> Optional[Dict]:
    """
    Extract startup information from Inc42 article HTML
    """
    soup = BeautifulSoup(article_html, "html.parser")
    
    # Try multiple selectors for company names
    name_selectors = [
        "h1.entry-title",
        "h2.entry-title",
        "h1.article-title",
        "h2.title",
        ".startup-name",
        "h3",
        "h2"
    ]
    
    # Step 1: get article title
    title_tag = soup.select_one("h1, h2, .entry-title")
    if not title_tag:
        return None

    article_title = clean_html(title_tag.get_text())

    # Step 2: extract startup name from title
    company_name = extract_company_from_title(article_title)

    # If no real startup entity is found → skip article
    if not company_name:
        return None

    
    # Extract description from meta or content
    description = ""
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc:
        description = meta_desc.get("content", "")
    
    if not description:
        # Try to get first paragraph
        first_p = soup.find("p")
        if first_p:
            description = clean_html(str(first_p))[:300]
    
    # Extract website if available
    website = ""
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if href.startswith("http") and not "inc42.com" in href:
            if any(domain in href.lower() for domain in [".com", ".in", ".io", ".ai", ".tech"]):
                website = href
                break
    
    # Determine sector from content
    sector_keywords = {
        "fintech": ["fintech", "financial", "payment", "banking", "lending"],
        "healthtech": ["health", "medical", "healthcare", "diagnostic", "pharma"],
        "edtech": ["education", "learning", "edtech", "student", "course"],
        "ecommerce": ["ecommerce", "retail", "marketplace", "shopping", "consumer"],
        "saas": ["saas", "enterprise", "software", "b2b", "cloud"],
        "ai": ["ai", "artificial intelligence", "machine learning", "ml", "deep learning"],
        "cleantech": ["clean", "green", "sustainability", "climate", "energy", "solar"],
        "deeptech": ["deeptech", "semiconductor", "chip", "hardware", "iot"],
        "agritech": ["agri", "farm", "agriculture", "crop", "farmer"],
        "logistics": ["logistics", "supply chain", "delivery", "transport", "warehouse"]
    }
    
    detected_sector = "technology"
    content_lower = (description + " " + company_name).lower()
    for sector, keywords in sector_keywords.items():
        if any(kw in content_lower for kw in keywords):
            detected_sector = sector
            break

    # reject obvious non-company phrases
    BAD_FUNDING_NAMES = [
        "guide",
        "understanding",
        "funding",
        "startup",
        "founders",
        "economy",
    ]

    if any(bad in company_name.lower() for bad in BAD_FUNDING_NAMES):
        return None

    
    return normalize_startup(
        company_name=company_name,
        source="inc42_" + urlparse(source_url).path.split("/")[1],
        website=website,
        description=f"{detected_sector.upper()}: {description}" if description else detected_sector.upper(),
        location="India",
        confidence="high" if website else "medium"
    )

def scrape_inc42_listings_page(url: str) -> List[Dict]:
    """
    Scrape a listings page (like 30 Startups to Watch) for multiple startup links
    """
    html = fetch_page(url)
    if not html:
        return []
    
    soup = BeautifulSoup(html, "html.parser")
    startups = []
    
    # Find all article links
    article_links = set()
    
    # Common patterns for article links on Inc42
    selectors = [
        "article h2 a",
        "article h3 a",
        ".post-title a",
        ".entry-title a",
        ".startup-card a",
        "a[href*='/startups/']",
        "a[href*='/features/']",
        "h2 a[href]",
        "h3 a[href]"
    ]
    
    for selector in selectors:
        for link in soup.select(selector):
            href = link.get("href", "")
            if href and "/startups/" in href or "/features/" in href or "/news/" in href:
                full_url = urljoin("https://inc42.com", href)
                article_links.add(full_url)
    
    logger.info(f"Found {len(article_links)} potential startup articles on {url}")
    
    # Process each article
    for article_url in list(article_links)[:20]:  # Limit to 20 per page to be polite
        try:
            article_html = fetch_page(article_url, delay=0.5)
            if article_html:
                startup = extract_startup_from_article(article_html, article_url)
                if startup:
                    startups.append(startup)
                    logger.info(f"Extracted: {startup['company_name']}")
        except Exception as e:
            logger.error(f"Error processing {article_url}: {e}")
    
    return startups

def scrape_inc42_funding_news(limit: int = 30) -> List[Dict]:
    """
    Scrape funding news articles which often contain multiple startups
    """
    url = "https://inc42.com/news/funding/"
    html = fetch_page(url)
    if not html:
        return []
    
    soup = BeautifulSoup(html, "html.parser")
    startups = []
    
    # Funding articles often mention multiple companies
    funding_articles = soup.select("article")[:10]
    
    for article in funding_articles:
        # Extract company names from funding headlines
        title_elem = article.select_one("h2, h3, .entry-title")
        if not title_elem:
            continue
        
        title = clean_html(str(title_elem))
        
        # Pattern: "Startup Name Raises $X Million"
        patterns = [
            r"([A-Z][\w\s&]+)\s+(?:Raises|Secures|Gets|Closes)",
            r"([A-Z][\w\s&]+)\s+(?:Funding|Investment)",
            r"([A-Z][\w\s&]+)\s+(?:Announces|Launches)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, title)
            if match:
                company_name = match.group(1).strip()
                if len(company_name) > 2 and len(company_name) < 50:
                    link_elem = article.select_one("a")
                    website = ""
                    if link_elem and link_elem.get("href"):
                        article_url = urljoin("https://inc42.com", link_elem["href"])
                        # Try to get more details
                        article_html = fetch_page(article_url, delay=0.3)
                        if article_html:
                            article_soup = BeautifulSoup(article_html, "html.parser")
                            # Look for website link in article
                            for a in article_soup.find_all("a", href=True):
                                if "inc42.com" not in a["href"] and a["href"].startswith("http"):
                                    website = a["href"]
                                    break
                    
                    startup = normalize_startup(
                        company_name=company_name,
                        source="inc42_funding_news",
                        website=website,
                        description=f"Featured in funding news: {title[:100]}",
                        location="India",
                        confidence="high" if website else "medium"
                    )
                    startups.append(startup)
                    break
    
    return startups[:limit]

def collect_inc42_startups(limit: int = 50, use_parallel: bool = True) -> List[Dict]:
    """
    Main entry point: Collect startups from multiple Inc42 sources
    Ensures at least 50 startups are fetched
    """
    all_startups = []
    
    logger.info("Starting Inc42 scraping...")
    
    # Method 1: Scrape main listings pages
    for endpoint in INC42_ENDPOINTS[:3]:  # Use first 3 endpoints
        try:
            startups = scrape_inc42_listings_page(endpoint)
            all_startups.extend(startups)
            logger.info(f"Collected {len(startups)} from {endpoint}")
            if len(all_startups) >= limit:
                break
        except Exception as e:
            logger.error(f"Error scraping {endpoint}: {e}")
    
    # Method 2: Scrape funding news
    if len(all_startups) < limit:
        try:
            funding_startups = scrape_inc42_funding_news(limit=limit - len(all_startups))
            all_startups.extend(funding_startups)
            logger.info(f"Collected {len(funding_startups)} from funding news")
        except Exception as e:
            logger.error(f"Error scraping funding news: {e}")
    
    # Method 3: Parallel scraping of additional pages if still needed
    if len(all_startups) < limit and use_parallel:
        additional_urls = [
            "https://inc42.com/startups/page/2/",
            "https://inc42.com/startups/page/3/",
            "https://inc42.com/datalabs/",
        ]
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_url = {executor.submit(scrape_inc42_listings_page, url): url for url in additional_urls}
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    startups = future.result()
                    all_startups.extend(startups)
                    logger.info(f"Parallel collected {len(startups)} from {url}")
                except Exception as e:
                    logger.error(f"Error in parallel scraping {url}: {e}")
    
    # Remove duplicates based on startup_id
    seen_ids = set()
    unique_startups = []
    for s in all_startups:
        if s["startup_id"] not in seen_ids:
            seen_ids.add(s["startup_id"])
            unique_startups.append(s)
    
    logger.info(f"Total unique startups from Inc42: {len(unique_startups)}")
    return unique_startups[:limit]

def enrich_with_inc42(startups: List[Dict]) -> List[Dict]:
    """
    Enrich existing startup data with Inc42 metadata
    """
    logger.info(f"Enriching {len(startups)} startups with Inc42 data...")
    
    for s in startups:
        # Add sector tags based on name/description
        name_desc = (s.get("company_name", "") + " " + s.get("description", "")).lower()
        
        sector_indicators = {
            "fintech": ["pay", "fin", "bank", "lend", "money", "wallet", "insurance"],
            "healthtech": ["health", "med", "care", "clinic", "doctor", "patient", "diagnostic"],
            "edtech": ["edu", "learn", "school", "student", "course", "academy"],
            "ecommerce": ["shop", "store", "retail", "market", "commerce", "buy", "sell"],
            "saas": ["cloud", "software", "enterprise", "b2b", "api", "platform"],
            "ai": ["ai", "artificial", "intelligence", "ml", "machine learning", "neural", "bot"],
            "agritech": ["agri", "farm", "crop", "farmer", "harvest", "rural"],
            "cleantech": ["green", "clean", "solar", "energy", "carbon", "climate", "sustain"],
            "logistics": ["logistics", "delivery", "supply", "transport", "cargo", "warehouse"],
            "food": ["food", "restaurant", "kitchen", "meal", "grocery", "delivery"],
        }
        
        for sector, keywords in sector_indicators.items():
            if any(kw in name_desc for kw in keywords):
                if not s.get("description"):
                    s["description"] = f"{sector.title()} startup operating in India"
                else:
                    s["description"] = f"[{sector.upper()}] {s['description']}"
                break
        
        # Mark as enriched
        s["inc42_enriched"] = True
    
    return startups

# Backward compatibility
def collect_startups_from_inc42(limit: int = 50) -> List[Dict]:
    """Alias for collect_inc42_startups"""
    return collect_inc42_startups(limit=limit)

if __name__ == "__main__":
    # Test the scraper
    startups = collect_inc42_startups(limit=50)
    print(f"\n✅ Successfully fetched {len(startups)} startups from Inc42")
    for i, s in enumerate(startups[:10], 1):
        print(f"{i}. {s['company_name']} ({s.get('description', 'N/A')[:50]}...)")