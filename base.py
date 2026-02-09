import hashlib
import asyncio
import aiohttp
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
from urllib.parse import urlparse, urljoin
import json
import re
import html

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class Startup:
    """Structured startup data model."""
    company_name: str
    source: str
    website: str = ""
    description: str = ""
    location: str = "India"
    discovered_date: str = ""
    confidence: str = "medium"
    startup_id: str = ""
    industry: str = ""
    funding_stage: str = ""
    employee_count: str = ""
    is_valid_company: bool = True
    validation_reason: str = ""
    
    def __post_init__(self):
        if not self.discovered_date:
            self.discovered_date = datetime.utcnow().isoformat()
        if not self.startup_id:
            self.startup_id = generate_id(self.company_name, self.website)
        self.company_name = self.company_name.strip()


# Validation patterns for filtering out non-companies
COMPANY_VALIDATION_PATTERNS = {
    'article_patterns': [
        r'the\s+\w+\s+reset',
        r'the\s+future\s+of',
        r'bharat\s+vistaar',
        r'union\s+budget',
        r'budget\s+\d{4}',
        r'how\s+\w+\s+(is|are|will)',
        r'why\s+\w+\s+matters',
        r'inside\s+\w+',
        r'beyond\s+\w+',
        r'meet\s+the',
        r'\d+\s+startups\s+to',
        r'what\s+(is|are)\s+\w+',
        r'when\s+\w+\s+(is|are)',
        r'where\s+\w+\s+(is|are)',
        r'who\s+\w+\s+(is|are)',
        r'guide\s+to',
        r'explained',
        r'analysis',
        r'report',
        r'study',
        r'trends?',
    ],
    'fake_patterns': [
        r'^stealth\s+(mode\s+)?(startup|fintech|saas|ai|company|venture)',
        r'^stealth\s*$',
        r'^unknown\s+',
        r'^tbd$',
        r'^placeholder$',
        r'^test\s+',
        r'^sample\s+',
    ],
    'government_patterns': [
        r'bharat\s+vistaar',
        r'government\s+of',
        r'ministry\s+of',
        r'department\s+of',
        r'initiative',
        r'scheme',
        r'programme',
        r'portal',
    ],
    'company_indicators': [
        r'founded\s+(in|by|on)',
        r'(ceo|founder|co-founder|cto|cfo|chief)\s*[:@]',
        r'headquartered\s+in',
        r'based\s+in',
        r'(raised|secured|closed)\s+\$?\d+',
        r'(seed|series\s+[a-d]|pre-seed|angel|venture)\s+(funding|round|investment)',
        r'(product|platform|app|solution|service|software)\s+(that|which|for|to|helps)',
        r'(customers?|clients?|users?|enterprises?)\s+',
        r'startup',
        r'headquarters',
        r'office\s+in',
    ],
    'valid_company_suffixes': [
        r'\b(pvt|private)\s*(limited|ltd)',
        r'\b(technologies|tech|solutions|services|labs|ventures|innovations|systems|software|digital|data|ai|analytics|cloud|network|media|studios|group|holdings|enterprises|corp|corporation)\b',
        r'\b\.(ai|io|co|app|tech|dev|cloud)\b',
        r'^[A-Z][a-z]+[A-Z][a-z]+',  # CamelCase
    ]
}

def clean_text(text: str) -> str:
    """
    Normalize and clean scraped text safely.
    - Removes HTML entities
    - Collapses whitespace
    - Strips junk characters
    """
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\x20-\x7E]", "", text)
    return text.strip()

def generate_id(name: str, website: str = "") -> str:
    """Generate unique ID for deduplication."""
    key = f"{name.lower().strip()}|{website.lower().strip()}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]

def is_valid_company(name: str, description: str = "", source: str = "") -> tuple[bool, str]:
    """
    Validate if this is a real company, not an article or placeholder.
    Returns (is_valid, reason)
    """
    if not name or len(name) < 2:
        return False, "empty_or_too_short_name"
    
    name_lower = name.lower().strip()
    desc_lower = (description or "").lower()
    source_lower = (source or "").lower()
    
    # Check 1: Article patterns in name
    for pattern in COMPANY_VALIDATION_PATTERNS['article_patterns']:
        if re.search(pattern, name_lower):
            return False, f"article_title_detected: {pattern}"
    
    # Check 2: Fake/placeholder patterns
    for pattern in COMPANY_VALIDATION_PATTERNS['fake_patterns']:
        if re.search(pattern, name_lower):
            return False, f"fake_placeholder_detected: {pattern}"
    
    # Check 3: Government initiatives (not startups)
    for pattern in COMPANY_VALIDATION_PATTERNS['government_patterns']:
        if re.search(pattern, name_lower) or re.search(pattern, desc_lower):
            return False, f"government_initiative_detected: {pattern}"
    
    # Check 4: Source-based rejection
    if 'stealth_signals' in source_lower:
        return False, "stealth_mode_not_verifiable"
    
    if 'features' in source_lower and not any(
        re.search(p, desc_lower) for p in COMPANY_VALIDATION_PATTERNS['company_indicators']
    ):
        return False, "likely_article_no_company_indicators"
    
    # Check 5: Must have company indicators OR valid suffix
    has_company_indicators = any(
        re.search(p, desc_lower) for p in COMPANY_VALIDATION_PATTERNS['company_indicators']
    )
    
    has_valid_suffix = any(
        re.search(p, name_lower) for p in COMPANY_VALIDATION_PATTERNS['valid_company_suffixes']
    )
    
    # Check if it looks like a proper noun (capitalized words)
    words = name.split()
    looks_like_company = len(words) <= 4 and all(w[0].isupper() for w in words if w)
    
    if not (has_company_indicators or has_valid_suffix or looks_like_company):
        # Allow if name is short and capitalized (might be a startup name)
        if len(name) > 20 or not looks_like_company:
            return False, "no_company_indicators_found"
    
    return True, "passed_validation"

def normalize_startup(
    company_name: str,
    source: str,
    website: str = "",
    description: str = "",
    location: str = "India",
    discovered_date: Optional[str] = None,
    confidence: str = "medium",
    **kwargs
) -> Optional[Dict[str, Any]]:
    """
    Legacy compatibility wrapper with validation.
    Returns None if not a valid company.
    """
    # Validate first
    is_valid, reason = is_valid_company(company_name, description, source)
    
    if not is_valid:
        logger.warning(f"REJECTED '{company_name}' from {source}: {reason}")
        return None
    
    startup = Startup(
        company_name=company_name,
        source=source,
        website=website,
        description=description,
        location=location,
        discovered_date=discovered_date or datetime.utcnow().isoformat(),
        confidence=confidence,
        validation_reason=reason,
        **kwargs
    )
    return asdict(startup)

def deduplicate(startups: List[Dict]) -> List[Dict]:
    """Remove duplicates based on startup_id and filter out None values."""
    # Filter out None first
    startups = [s for s in startups if s is not None]
    
    seen = set()
    result = []
    for s in startups:
        sid = s.get("startup_id") or generate_id(s.get("company_name", ""), s.get("website", ""))
        if sid not in seen:
            seen.add(sid)
            s["startup_id"] = sid
            result.append(s)
    return result

def filter_valid_startups(startups: List[Dict]) -> List[Dict]:
    """Filter list to only valid companies."""
    valid = [s for s in startups if s is not None and s.get("is_valid_company", True)]
    rejected = len(startups) - len(valid)
    if rejected > 0:
        logger.info(f"Filtered out {rejected} invalid entries")
    return valid