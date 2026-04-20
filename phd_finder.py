"""
phd_finder.py

Discovers PhD students in cybersecurity research via university lab pages
and web search. Returns structured profiles (name, email, university,
research area, recent paper) for personalized collaboration outreach.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time

import anthropic
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(__file__)
PHD_TARGETS_PATH = os.path.join(BASE_DIR, "phd_targets.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Top university cybersecurity research lab pages
SECURITY_LABS = [
    ("CMU CyLab",           "https://cylab.cmu.edu/directory/index.html"),
    ("Georgia Tech SCP",    "https://scp.cc.gatech.edu/people/"),
    ("UC Berkeley SecLab",  "https://security.cs.berkeley.edu/"),
    ("NYU OSIRIS",          "https://osiris.cyber.nyu.edu/team/"),
    ("UCSB SecLab",         "https://seclab.cs.ucsb.edu/people/"),
    ("MIT CSAIL CSS",       "https://css.csail.mit.edu/people/"),
    ("Stanford SecLab",     "https://seclab.stanford.edu/people/"),
    ("UMD Security",        "https://www.cs.umd.edu/research/areas/security-and-privacy"),
    ("Purdue CERIAS",       "https://www.cerias.purdue.edu/people/students/"),
    ("Illinois SecLab",     "https://seclab.illinois.edu/people/"),
    ("UTexas SecLab",       "https://security.utexas.edu/people"),
    ("Northeastern CCS",    "https://ccs.neu.edu/group/"),
]

# DDG search queries to find PhD students
PHD_SEARCH_QUERIES = [
    "cybersecurity PhD student research email contact site:.edu 2025",
    "malware analysis PhD student university lab email site:.edu",
    "network security PhD candidate research group email site:.edu",
    "DFIR digital forensics PhD student university email contact",
    "vulnerability research PhD student university 2024 2025 site:.edu",
    "applied cryptography PhD student university email site:.edu",
    "IoT firmware security PhD student university email",
    "threat intelligence PhD student lab email site:.edu",
    "binary analysis reverse engineering PhD student email site:.edu",
    "machine learning security PhD student lab site:.edu email",
    "zero-day exploit research PhD student university contact",
    "intrusion detection PhD candidate university email site:.edu",
]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def discover_phd_students(contacted_emails: set[str], count: int = 10) -> list[dict]:
    """
    Discover `count` PhD students in cybersecurity not already contacted.
    Returns list of dicts: {name, email, university, research_area, recent_work, source}.
    """
    raw: list[dict] = []

    # 1. Scrape known university lab pages
    for lab_name, url in SECURITY_LABS:
        if len(raw) >= count * 4:
            break
        students = _scrape_lab_page(lab_name, url)
        raw.extend(students)
        time.sleep(0.5)

    # 2. DDG search fallback
    for query in PHD_SEARCH_QUERIES:
        if len(raw) >= count * 4:
            break
        students = _search_phd_students(query)
        raw.extend(students)
        time.sleep(0.4)

    # Deduplicate by email, skip already contacted
    seen: set[str] = set()
    unique: list[dict] = []
    for s in raw:
        email = s.get("email", "").lower().strip()
        if not email or email in seen or email in contacted_emails:
            continue
        seen.add(email)
        unique.append(s)

    if len(unique) < count:
        logger.warning(f"Only found {len(unique)} PhD students (wanted {count}).")

    return unique[:count]


def load_phd_targets() -> list[dict]:
    if not os.path.exists(PHD_TARGETS_PATH):
        return []
    with open(PHD_TARGETS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_phd_targets(targets: list[dict]) -> None:
    with open(PHD_TARGETS_PATH, "w", encoding="utf-8") as f:
        json.dump(targets, f, indent=2)


# ---------------------------------------------------------------------------
# Lab page scraper
# ---------------------------------------------------------------------------

def _scrape_lab_page(lab_name: str, url: str) -> list[dict]:
    """Scrape a university security lab page for PhD student profiles."""
    students = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "lxml")
        text = soup.get_text(separator=" ", strip=True)

        # Find .edu emails on the page
        emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.edu", text)
        personal_emails = [
            e for e in emails
            if not any(x in e.split("@")[0].lower() for x in
                       ["info", "admin", "contact", "noreply", "help", "dept", "office"])
        ]

        if not personal_emails:
            # Try extracting from hrefs (mailto links)
            for a in soup.find_all("a", href=re.compile(r"^mailto:")):
                raw = a["href"].replace("mailto:", "").split("?")[0].strip()
                if "@" in raw and ".edu" in raw:
                    personal_emails.append(raw)

        # Use Claude to extract structured profiles from the page text
        if personal_emails:
            profiles = _extract_profiles_via_claude(lab_name, text[:3000], personal_emails[:15])
            students.extend(profiles)

        logger.debug(f"Scraped {len(students)} students from {lab_name}")
    except Exception as e:
        logger.debug(f"Lab page scrape failed for {lab_name} ({url}): {e}")
    return students


# ---------------------------------------------------------------------------
# DDG search
# ---------------------------------------------------------------------------

def _search_phd_students(query: str) -> list[dict]:
    """Search DDG for PhD students and extract profiles from snippets."""
    students = []
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=8))

        snippets = []
        for r in results:
            title = r.get("title", "")
            body = r.get("body", "")
            href = r.get("href", "")
            if ".edu" in href or "phd" in title.lower() or "student" in title.lower():
                snippets.append(f"{title}: {body[:300]} [url: {href}]")

        if snippets:
            blob = "\n".join(snippets)
            profiles = _extract_profiles_via_claude("web search", blob, [])
            students.extend(profiles)

    except Exception as e:
        logger.debug(f"PhD search failed for '{query}': {e}")
    return students


# ---------------------------------------------------------------------------
# Claude extraction
# ---------------------------------------------------------------------------

def _extract_profiles_via_claude(source: str, text: str, known_emails: list[str]) -> list[dict]:
    """Use Claude to extract structured PhD student profiles from text."""
    emails_hint = f"\nKnown emails found on page: {', '.join(known_emails)}" if known_emails else ""

    prompt = f"""Extract PhD student profiles in cybersecurity from the text below.
Source: {source}{emails_hint}

For each PhD student (NOT professors/faculty), extract:
- name: full name
- email: their .edu email if visible, else empty string
- university: university name
- research_area: 3-6 word description (e.g. "malware analysis and reverse engineering")
- recent_work: title of a paper or project they're working on, or empty string

Rules:
- Only include current PhD students or PhD candidates, not professors
- Only include people doing cybersecurity, security, or privacy research
- If no email found, still include the student if name + university + research_area are clear
- Skip anyone with no name or unclear role

Return ONLY a JSON array. Example:
[
  {{"name": "Jane Smith", "email": "jsmith@cs.cmu.edu", "university": "CMU", "research_area": "fuzzing and vulnerability discovery", "recent_work": "Coverage-guided fuzzing of network protocols"}}
]

Text:
{text[:2500]}"""

    try:
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            profiles = json.loads(match.group(0))
            # Add source field
            for p in profiles:
                p["source"] = source
                p.setdefault("email", "")
                p.setdefault("recent_work", "")
            return [p for p in profiles if isinstance(p, dict) and p.get("name")]
    except Exception as e:
        logger.debug(f"Claude profile extraction failed: {e}")
    return []


# ---------------------------------------------------------------------------
# Find email for a student who has no email yet
# ---------------------------------------------------------------------------

def find_student_email(student: dict) -> str:
    """
    Try to find an email for a PhD student who doesn't have one yet.
    Searches their personal page, university directory, or GitHub.
    """
    name = student.get("name", "")
    university = student.get("university", "")
    research_area = student.get("research_area", "")

    queries = [
        f'"{name}" "{university}" cybersecurity email site:.edu',
        f'"{name}" security research email contact',
        f'"{name}" "{research_area}" site:.edu',
    ]

    for query in queries:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
            for r in results:
                text = r.get("body", "") + " " + r.get("title", "")
                emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.edu", text)
                for email in emails:
                    local = email.split("@")[0].lower()
                    # Check name similarity
                    name_parts = name.lower().split()
                    if any(part[:4] in local for part in name_parts if len(part) >= 3):
                        return email
            time.sleep(0.3)
        except Exception:
            pass

    return ""
