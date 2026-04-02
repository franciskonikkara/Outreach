"""
researcher.py

Discovers companies entirely via live web search — no hardcoded pool.
Runs multiple targeted queries across categories and regions, then uses
the Anthropic API to extract clean company names from the raw results.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time

import anthropic
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Diverse queries — run a random subset each time to stay fresh
DISCOVERY_QUERIES = [
    # Startups by funding/news
    "cybersecurity startup Series A B funding 2025",
    "AI security startup raised funding 2025 2026",
    "cloud security startup seed funding 2025",
    "application security startup funding round 2025",
    "threat intelligence startup funding 2025",
    "offensive security company new 2024 2025",
    "zero trust security startup 2025 funding",
    "identity security startup funding 2025",
    # Internship / hiring signals
    "security engineering internship summer 2026 startup",
    "product security intern 2026 hiring",
    "red team internship 2026",
    "bug bounty platform hiring 2026",
    "cybersecurity research intern 2026 remote",
    "appsec intern 2026 startup",
    "DFIR forensics intern 2026",
    "incident response intern summer 2026",
    # Research orgs worldwide
    "cybersecurity research lab internship 2026",
    "national laboratory security research intern 2026",
    "university cybersecurity research group hiring 2026",
    "applied security research organization 2026",
    "Fraunhofer cybersecurity internship 2026",
    "INRIA security research intern 2026",
    "European cybersecurity research institute intern",
    "Singapore cybersecurity research internship 2026",
    "Canada cybersecurity research lab intern 2026",
    "UK cybersecurity company internship 2026",
    # YC / accelerator
    "YC W25 S25 security startup",
    "Y Combinator cybersecurity startup 2025",
    "Techstars cybersecurity company 2025",
    # Specific categories
    "DFIR digital forensics incident response company hiring 2026",
    "malware analysis reverse engineering company intern 2026",
    "SOC automation SOAR platform hiring intern 2026",
    "devsecops startup hiring intern 2026",
    "SBOM software supply chain security company 2025",
    "IoT security company hiring 2026",
    "OT ICS security company intern 2026",
    # Job boards / lists
    "site:wellfound.com cybersecurity security intern 2026",
    "site:ycombinator.com/companies security internship",
    "crunchbase cybersecurity company founded 2023 2024 2025",
]


def discover_companies(contacted: set[str], count: int = 10) -> list[str]:
    """
    Discover `count` fresh companies not in `contacted` via live search.
    Runs several queries, extracts company names via Claude, deduplicates.
    """
    queries_to_run = random.sample(DISCOVERY_QUERIES, min(12, len(DISCOVERY_QUERIES)))

    raw_snippets: list[str] = []
    for query in queries_to_run:
        snippets = _search(query, max_results=8)
        raw_snippets.extend(snippets)
        time.sleep(0.4)

    if not raw_snippets:
        logger.error("All discovery searches failed — no results.")
        return []

    candidates = _extract_companies_via_claude(raw_snippets)
    logger.info(f"Claude extracted {len(candidates)} candidate companies from search results.")

    fresh = [c for c in candidates if c.lower() not in contacted]

    seen: set[str] = set()
    deduped: list[str] = []
    for c in fresh:
        key = c.lower().strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(c)

    random.shuffle(deduped)
    selected = deduped[:count]

    if len(selected) < count:
        logger.warning(
            f"Only found {len(selected)} fresh companies (wanted {count}). "
            "Consider running again later for more results."
        )

    return selected


def _search(query: str, max_results: int = 8) -> list[str]:
    """Run a DDG search and return a list of 'title: snippet' strings."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        snippets = []
        for r in results:
            title = r.get("title", "").strip()
            body = r.get("body", "").strip()[:200]
            if title or body:
                snippets.append(f"{title}: {body}")
        return snippets
    except Exception as e:
        logger.debug(f"DDG search failed for '{query}': {e}")
        return []


def _call_claude(prompt: str) -> str:
    """Call Anthropic API with a prompt and return the text response."""
    try:
        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except Exception as e:
        logger.error(f"Anthropic API call failed: {e}")
        return ""


def _extract_companies_via_claude(snippets: list[str]) -> list[str]:
    """
    Pass raw search snippets to Claude and ask it to extract company/org names.
    Returns a flat list of company name strings.
    """
    chunk_size = 120
    all_names: list[str] = []

    for i in range(0, len(snippets), chunk_size):
        chunk = snippets[i : i + chunk_size]
        blob = "\n".join(chunk)

        prompt = f"""Below are web search snippets about cybersecurity companies, security startups, research labs, and related organizations.

Extract every distinct company name, startup name, or research organization name you can identify. Include:
- Security startups and scaleups (any stage, any country)
- Cybersecurity research labs and institutes (university-affiliated, government, independent)
- National labs with security research programs
- Established security companies that look like they hire interns
- DFIR, forensics, incident response, and SOC automation companies
- Bug bounty platforms, offensive security firms, threat intelligence companies

Exclude:
- Generic words that aren't company names (e.g., "Google", "LinkedIn", "YouTube", "Twitter" as platforms)
- News outlets, blogs, job board names (Wellfound, LinkedIn, Glassdoor, Indeed, Crunchbase itself)
- Universities themselves (unless they have a named research lab/center)
- Vague terms like "Security Company" or "Startup"

Output ONLY a JSON array of strings — the company/org names, nothing else. No explanation. Example format:
["Wiz", "Trail of Bits", "Fraunhofer AISEC", "SRI International"]

Search snippets:
{blob}"""

        try:
            raw = _call_claude(prompt)
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                names = json.loads(match.group(0))
                all_names.extend([n for n in names if isinstance(n, str) and n.strip()])
        except Exception as e:
            logger.warning(f"Claude extraction failed for chunk {i}: {e}")

    return all_names


def research_company(company_name: str) -> dict:
    """Fetch homepage, recent news, and jobs page for a company."""
    result = {
        "name": company_name,
        "description": "",
        "recent_news": "",
        "open_roles": "",
        "homepage_url": "",
        "domain": "",
    }

    homepage_url, domain = _find_homepage(company_name)
    result["homepage_url"] = homepage_url
    result["domain"] = domain

    if not homepage_url:
        logger.warning(f"Could not find homepage for {company_name}")
        return result

    result["description"] = _scrape_text(homepage_url, char_limit=1500)
    result["recent_news"] = _find_recent_news(company_name, domain)
    result["open_roles"] = _find_open_roles(company_name, domain, homepage_url)

    return result


def _find_homepage(company_name: str) -> tuple[str, str]:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(f"{company_name} official website", max_results=5))
        for r in results:
            url = r.get("href", "")
            if url and _looks_like_homepage(url, company_name):
                domain = _extract_domain(url)
                return url, domain
        if results:
            url = results[0].get("href", "")
            return url, _extract_domain(url)
    except Exception as e:
        logger.warning(f"Homepage search failed for {company_name}: {e}")
    return "", ""


def _looks_like_homepage(url: str, company: str) -> bool:
    slug = re.sub(r"[^a-z0-9]", "", company.lower())
    domain_part = re.sub(r"[^a-z0-9]", "", _extract_domain(url).lower())
    return slug[:6] in domain_part or domain_part[:6] in slug


def _extract_domain(url: str) -> str:
    match = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return match.group(1) if match else ""


def _scrape_text(url: str, char_limit: int = 1500) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        return text[:char_limit]
    except Exception as e:
        logger.warning(f"Scrape failed for {url}: {e}")
        return ""


def _find_recent_news(company_name: str, domain: str) -> str:
    try:
        with DDGS() as ddgs:
            results = list(
                ddgs.text(f"{company_name} security news blog 2025 2026", max_results=3)
            )
        snippets = [r.get("body", "")[:300] for r in results]
        return " | ".join(snippets)[:800]
    except Exception as e:
        logger.warning(f"News search failed for {company_name}: {e}")
        return ""


def _find_open_roles(company_name: str, domain: str, homepage_url: str) -> str:
    careers_paths = ["/careers", "/jobs", "/about/jobs", "/work-with-us", "/join-us"]
    base = f"https://{domain}" if domain else homepage_url.rstrip("/")

    for path in careers_paths:
        url = base + path
        try:
            resp = requests.get(url, headers=HEADERS, timeout=8)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "lxml")
                text = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))
                if any(kw in text.lower() for kw in ["security", "intern", "engineer"]):
                    return text[:600]
        except Exception:
            pass
        time.sleep(0.2)

    try:
        with DDGS() as ddgs:
            results = list(
                ddgs.text(f"{company_name} security intern role 2026", max_results=2)
            )
        if results:
            return results[0].get("body", "")[:400]
    except Exception as e:
        logger.warning(f"Roles search failed for {company_name}: {e}")

    return ""
