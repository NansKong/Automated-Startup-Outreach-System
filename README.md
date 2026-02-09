# Automated Startup Outreach System

An end-to-end system to **automatically discover newly registered Indian startups**, **enrich their data**, and **run personalized outreach campaigns** using **Python + n8n**.

---

## Overview

The Automated Startup Outreach System helps founders, sales teams, accelerators, and growth teams connect with early-stage Indian startups at scale — without manual research or copy-paste work.

This system:
- Discovers newly registered startups from multiple trusted sources
- Enriches startup data using **n8n workflows**
- Generates personalized outreach messages using AI
- Sends emails and WhatsApp messages automatically

---

## Key Features

### Startup Discovery (Python)
- Automated discovery of Indian startups from:
  - DPIIT
  - MCA
  - AngelList (Wellfound)
  - Tracxn
  - YC
  - LinkedIn
  - Tier-2 startup platforms
- Filters **official startup entities only** (no blogs, podcasts, or news articles)

### Data Enrichment (n8n)
- Uses **n8n workflows** for:
  - Website enrichment
  - Industry classification
  - Location normalization
  - Company description cleanup
  - Social profile enrichment (Founder Name, Email, LinkedIn, website, etc.)

### AI Message Generation (n8n)
- Personalized outreach message creation using LLMs
- Context-aware prompts based on:
  - Startup industry
  - Stage
  - Location
  - Business model

### Automated Outreach
- **Email sending** via n8n integrations
- **WhatsApp message sending** via API integrations
- Easy extension to CRM tools or Slack

---

## Repository Structure

```text
.
├── base.py                     # Base scraper class
├── run_discovery.py             # Main discovery pipeline
├── angellist_scraper.py
├── dpiit_scraper.py
├── inc42_scraper.py
├── linkedin_scraper.py
├── mca_scraper.py
├── tier2_scraper.py
├── tracxn_scraper.py
├── website_scraper.py
├── yc_scraper.py
├── Indian Startup Outreach System final.json
└── n8n/
    └── workflows.json           # n8n enrichment + outreach workflows
