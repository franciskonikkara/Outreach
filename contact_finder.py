from __future__ import annotations

import logging
import re

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

# Roles to search for in priority order
TARGET_ROLES = [
    "Head of Security",
    "CISO",
    "Security Engineering Manager",
    "VP of Engineering",
    "Director of Security",
    "Security Recruiter",
]

TEAM_INBOXES = ["security", "appsec", "careers", "jobs", "recruiting", "hiring"]


def find_contact(company_name: str, domain: str) -> tuple[str, str]:
    """
    Returns (email, contact_name).
    Tries: named person > inferred pattern > team inbox > general contact.
    """
    name, title = _find_named_person(company_name)
    if name and domain:
        pattern = _infer_email_pattern(company_name, domain)
        if pattern:
            email = _apply_pattern(name, pattern, domain)
            if email:
                return email, f"{name} ({title or 'inferred'})"

    for inbox in TEAM_INBOXES:
        if domain:
            email = f"{inbox}@{domain}"
            return email, f"{inbox} team inbox"

    if domain:
        email = _scrape_contact_page(domain)
        if email:
            return email, "contact page"

    return "", "unknown"


def _find_named_person(company_name: str) -> tuple[str, str]:
    """Search for a named security leader at the company. Returns (name, title)."""
    for role in TARGET_ROLES:
        try:
            with DDGS() as ddgs:
                results = list(
                    ddgs.text(
                        f'"{company_name}" "{role}" site:linkedin.com OR site:{company_name.lower().replace(" ", "")}.com',
                        max_results=3,
                    )
                )
            for r in results:
                name = _extract_person_name(r.get("title", ""), r.get("body", ""), role)
                if name:
                    return name, role
        except Exception as e:
            logger.debug(f"Named person search failed for {company_name}/{role}: {e}")

    try:
        with DDGS() as ddgs:
            results = list(
                ddgs.text(f'"{company_name}" security team email contact', max_results=3)
            )
        for r in results:
            name = _extract_person_name(r.get("title", ""), r.get("body", ""), "")
            if name:
                return name, ""
    except Exception:
        pass

    return "", ""


def _extract_person_name(title: str, body: str, role: str) -> str:
    """
    Try to extract a real person's name from a search result.
    Looks for patterns like "Jane Smith - Head of Security at CompanyName".
    """
    patterns = [
        r"([A-Z][a-z]+ [A-Z][a-z]+)\s*[-–|]\s*(?:Head|CISO|VP|Director|Manager|Engineer|Recruiter)",
        r"([A-Z][a-z]+ [A-Z][a-z]+),?\s+(?:Head|CISO|VP|Director|Manager|Engineer)",
    ]
    for text in [title, body]:
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                name = match.group(1)
                if name not in {"New York", "San Francisco", "Los Angeles", "United States"}:
                    return name
    return ""


def _infer_email_pattern(company_name: str, domain: str) -> str | None:
    """
    Try to find a confirmed email at this domain to learn the naming pattern.
    Returns a format string like '{first}.{last}' or '{first}' etc.
    """
    search_queries = [
        f'site:github.com "@{domain}"',
        f'"{domain}" email contact -noreply -no-reply',
        f'"{company_name}" "@{domain}" blog author',
    ]

    for query in search_queries:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
            for r in results:
                text = r.get("body", "") + " " + r.get("title", "")
                emails = re.findall(
                    r"[a-zA-Z0-9._%+\-]+@" + re.escape(domain), text
                )
                for email in emails:
                    local = email.split("@")[0].lower()
                    if local in TEAM_INBOXES or local in {"info", "contact", "support", "hello", "noreply"}:
                        continue
                    if "." in local:
                        parts = local.split(".")
                        if len(parts) == 2:
                            return "{first}.{last}"
                        elif len(parts[0]) == 1:
                            return "{fi}{last}"
                    else:
                        return "{first}"
        except Exception as e:
            logger.debug(f"Pattern inference failed for {domain}: {e}")

    return None


def _apply_pattern(full_name: str, pattern: str, domain: str) -> str:
    """Apply a naming pattern to a full name to produce an email."""
    parts = full_name.lower().split()
    if len(parts) < 2:
        return ""
    first, last = parts[0], parts[-1]
    try:
        local = pattern.format(first=first, last=last, fi=first[0])
        return f"{local}@{domain}"
    except Exception:
        return ""


def _scrape_contact_page(domain: str) -> str:
    """Try to find an email address on the company's contact/about page."""
    paths = ["/contact", "/about", "/contact-us", "/team"]
    for path in paths:
        url = f"https://{domain}{path}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=8)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "lxml")
                text = soup.get_text()
                emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
                for email in emails:
                    local = email.split("@")[0].lower()
                    if local not in {"noreply", "no-reply", "donotreply"}:
                        return email
        except Exception:
            pass
    return ""
