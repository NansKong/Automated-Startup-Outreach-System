"""
Startup Discovery Engine - Fixed to only collect real companies
"""

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from base import deduplicate, normalize_startup, filter_valid_startups, logger
from dpiit_scraper import collect_dpiit_startups
from mca_scraper import collect_mca_startups
from yc_scraper import collect_yc_india
from angellist_scraper import collect_angellist_startups
from tracxn_scraper import collect_tracxn_startups
from linkedin_scraper import collect_linkedin_startups
from tier2_scraper import collect_tier2_startups
from inc42_scraper import collect_inc42_startups, enrich_with_inc42
from website_scraper import enrich_from_website

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET_COUNT = 50
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "data", "startup_discovery.json")

def parallel_collection() -> List[Dict]:
    """
    Collect startups from all sources in parallel.
    Filters out invalid entries immediately.
    """
    all_startups = []
    
    # Only use reliable sources
    scraper_tasks = {
        "DPIIT (Official)": lambda: collect_dpiit_startups(limit=25),
        "MCA Filings": collect_mca_startups,
        "Y Combinator India": collect_yc_india,
        "AngelList India": lambda: collect_angellist_startups(limit=20),
        "Tracxn Emerging": collect_tracxn_startups,
        # REMOVED: LinkedIn stealth signals (fake data)
        # "LinkedIn Signals": collect_linkedin_startups,
        "Tier-2 Cities": collect_tier2_startups,
        "Inc42 Startups": lambda: collect_inc42_startups(limit=30),
    }
    
    logger.info("🚀 Starting parallel startup discovery...")
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_source = {
            executor.submit(func): source 
            for source, func in scraper_tasks.items()
        }
        
        for future in as_completed(future_to_source):
            source = future_to_source[future]
            try:
                startups = future.result()
                # Filter valid immediately
                valid_startups = filter_valid_startups(startups)
                all_startups.extend(valid_startups)
                logger.info(f"✅ {source}: {len(valid_startups)} valid startups ({len(startups) - len(valid_startups)} filtered)")
            except Exception as e:
                logger.error(f"❌ {source}: Failed - {str(e)}")
    
    return all_startups

def smart_deduplication(startups: List[Dict]) -> List[Dict]:
    """Enhanced deduplication."""
    logger.info(f"🔍 Deduplicating {len(startups)} startups...")
    
    unique_startups = deduplicate(startups)
    
    # Additional fuzzy matching
    final_startups = []
    name_map = {}
    
    for s in unique_startups:
        name = s["company_name"].lower().replace(" ", "").replace(".", "").replace(",", "")
        is_duplicate = False
        
        for existing_name in name_map:
            if name in existing_name or existing_name in name:
                if len(name) > 5:
                    is_duplicate = True
                    break
        
        if not is_duplicate:
            name_map[name] = True
            final_startups.append(s)
    
    logger.info(f"✨ Deduplication: {len(startups)} → {len(final_startups)}")
    return final_startups

def enrich_startup_data(startups: List[Dict]) -> List[Dict]:
    """Multi-layer enrichment."""
    logger.info("🎨 Enriching startup data...")
    
    try:
        startups = enrich_with_inc42(startups)
    except Exception as e:
        logger.error(f"Inc42 enrichment failed: {e}")
    
    try:
        startups = enrich_from_website(startups)
    except Exception as e:
        logger.error(f"Website enrichment failed: {e}")
    
    # Confidence scoring
    for s in startups:
        score = 0
        if s.get("website") and ".gov.in" not in s["website"]: 
            score += 1
        if s.get("description") and len(s["description"]) > 20: 
            score += 1
        if s.get("location"): 
            score += 1
        
        s["confidence"] = "high" if score >= 3 else "medium" if score >= 2 else "low"
    
    return startups

def save_results(startups: List[Dict], filepath: str):
    """Save results to JSON."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    # Filter out any remaining invalid entries
    valid_startups = [s for s in startups if s and s.get("is_valid_company", True)]
    
    output = {
        "metadata": {
            "total_count": len(valid_startups),
            "target_count": TARGET_COUNT,
            "sources_used": list(set(s["source"] for s in valid_startups)),
            "high_confidence": len([s for s in valid_startups if s.get("confidence") == "high"]),
            "medium_confidence": len([s for s in valid_startups if s.get("confidence") == "medium"]),
            "low_confidence": len([s for s in valid_startups if s.get("confidence") == "low"]),
        },
        "startups": valid_startups
    }
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    logger.info(f"💾 Results saved: {filepath}")

def main():
    """Main execution flow."""
    logger.info("=" * 60)
    logger.info("🚀 STARTUP DISCOVERY SYSTEM (FIXED VERSION)")
    logger.info("=" * 60)
    
    # Phase 1: Collect
    startups = parallel_collection()
    
    # Phase 2: Deduplicate
    startups = smart_deduplication(startups)
    
    # Phase 3: Enrich
    startups = enrich_startup_data(startups)
    
    # Phase 4: Sort by confidence
    startups.sort(key=lambda x: (x.get("confidence") != "high", x.get("confidence") != "medium"))
    final_startups = startups[:TARGET_COUNT]
    
    # Phase 5: Save
    save_results(final_startups, OUTPUT_PATH)
    
    # Summary
    logger.info("=" * 60)
    logger.info("📊 DISCOVERY SUMMARY")
    logger.info("=" * 60)
    logger.info(f"✅ Total Valid Startups: {len(final_startups)}")
    logger.info(f"⭐ High Confidence: {len([s for s in final_startups if s.get('confidence') == 'high'])}")
    logger.info(f"📍 Medium Confidence: {len([s for s in final_startups if s.get('confidence') == 'medium'])}")
    logger.info(f"❌ Rejected Invalid Entries: See logs above")
    
    source_counts = {}
    for s in final_startups:
        src = s["source"]
        source_counts[src] = source_counts.get(src, 0) + 1
    
    logger.info("\n📈 Source Breakdown:")
    for source, count in sorted(source_counts.items(), key=lambda x: -x[1]):
        logger.info(f"   • {source}: {count}")
    
    logger.info("=" * 60)
    
    return final_startups

if __name__ == "__main__":
    main()