from __future__ import annotations

import logging
import os
import re
import time

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

# Security-relevant titles (used by both Apollo and fallback name search)
SECURITY_TITLES = [
    "Head of Security",
    "CISO",
    "Chief Information Security Officer",
    "Security Engineering Manager",
    "Director of Security",
    "VP of Security",
    "Security Engineer",
    "Security Recruiter",
    "Threat Intelligence",
    "Penetration Tester",
    "Red Team",
    "AppSec",
    "DevSecOps",
    "Incident Response",
]

# Generic inboxes — fallback only, tried last
TEAM_INBOXES = ["security", "appsec", "careers", "jobs", "recruiting", "hiring"]

# Email locals that are NOT personal addresses
GENERIC_LOCALS = {
    "noreply", "no-reply", "donotreply", "info", "contact", "support",
    "hello", "team", "press", "media", "legal", "privacy", "abuse",
    "security", "appsec", "careers", "jobs", "recruiting", "hiring",
    "sales", "marketing", "billing", "accounts", "admin", "webmaster",
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def find_contact(company_name: str, domain: str) -> tuple[str, str]:
    """
    Returns (email, contact_name).
    Priority chain:
      1. Hunter.io domain search  (HUNTER_API_KEY)
      2. Apollo.io people search  (APOLLO_API_KEY)
      3. Hunter.io email-finder   (uses Apollo name + Hunter key)
      4. GitHub / blog / DDG mining
      5. Named person + inferred email pattern
      6. Contact / team page scrape
      7. Generic team inbox fallback
    """
    if not domain:
        return "", "unknown"

    hunter_key = os.getenv("HUNTER_API_KEY", "")
    apollo_key = os.getenv("APOLLO_API_KEY", "")

    # ── 1. Hunter.io domain search ──────────────────────────────────────────
    if hunter_key:
        email, name = _hunter_domain_search(domain, hunter_key)
        if email:
            logger.info(f"Hunter.io found: {name} <{email}>")
            return email, name

    # ── 2. Apollo.io people search ──────────────────────────────────────────
    apollo_person: dict = {}
    if apollo_key:
        email, name, apollo_person = _apollo_people_search(company_name, domain, apollo_key)
        if email:
            logger.info(f"Apollo.io found: {name} <{email}>")
            return email, name

    # ── 3. Hunter.io email-finder (cross Apollo name × Hunter pattern) ──────
    if hunter_key and apollo_person.get("first_name") and apollo_person.get("last_name"):
        email, name = _hunter_email_finder(
            domain,
            apollo_person["first_name"],
            apollo_person["last_name"],
            hunter_key,
        )
        if email:
            logger.info(f"Hunter email-finder found: {name} <{email}>")
            return email, name

    # ── 4. GitHub / blog / DDG mining ───────────────────────────────────────
    email, name = _find_real_employee_email(company_name, domain)
    if email:
        logger.info(f"Web mining found: {name} <{email}>")
        return email, name

    # ── 5. Named person + inferred email pattern ─────────────────────────────
    person_name, title = _find_named_person(company_name)
    if person_name:
        pattern = _infer_email_pattern(company_name, domain)
        if pattern:
            email = _apply_pattern(person_name, pattern, domain)
            if email:
                return email, f"{person_name} ({title or 'inferred'})"

    # ── 6. Contact / team page scrape ────────────────────────────────────────
    scraped = _scrape_contact_page(domain)
    if scraped:
        return scraped, "contact page"

    # ── 7. Generic team inbox fallback ───────────────────────────────────────
    for inbox in TEAM_INBOXES:
        return f"{inbox}@{domain}", f"{inbox} team inbox"

    return "", "unknown"


# ---------------------------------------------------------------------------
# Strategy 1 — Hunter.io domain search
# ---------------------------------------------------------------------------

def _hunter_domain_search(domain: str, api_key: str) -> tuple[str, str]:
    """
    GET /v2/domain-search — returns all emails Hunter knows for the domain.
    Picks the most relevant security person; falls back to any personal email.
    Docs: https://hunter.io/api-documentation/v2#domain-search
    """
    url = "https://api.hunter.io/v2/domain-search"
    params = {
        "domain": domain,
        "api_key": api_key,
        "limit": 10,
        "type": "personal",
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        emails = data.get("emails", [])

        if not emails:
            logger.debug(f"Hunter domain search: no emails found for {domain}")
            return "", ""

        # Score each result: prefer security-relevant titles, higher confidence
        def _score(entry: dict) -> int:
            title = (entry.get("position") or "").lower()
            score = entry.get("confidence", 0)
            security_kw = ["security", "ciso", "appsec", "pentest", "red team",
                           "threat", "forensic", "soc", "devsecops", "infosec"]
            if any(kw in title for kw in security_kw):
                score += 50
            return score

        emails.sort(key=_score, reverse=True)
        best = emails[0]
        email = best.get("value", "")
        first = best.get("first_name", "")
        last = best.get("last_name", "")
        position = best.get("position", "")
        full_name = f"{first} {last}".strip() or _guess_name_from_email(email)
        display = f"{full_name} ({position})" if position else full_name
        return email, display

    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 401:
            logger.warning("Hunter.io: invalid API key (401). Check HUNTER_API_KEY.")
        elif e.response is not None and e.response.status_code == 429:
            logger.warning("Hunter.io: rate limit hit (429). Will retry next run.")
        else:
            logger.warning(f"Hunter.io domain search failed for {domain}: {e}")
    except Exception as e:
        logger.warning(f"Hunter.io domain search error for {domain}: {e}")

    return "", ""


# ---------------------------------------------------------------------------
# Strategy 2 — Apollo.io people search
# ---------------------------------------------------------------------------

def _apollo_people_search(
    company_name: str, domain: str, api_key: str
) -> tuple[str, str, dict]:
    """
    POST /v1/mixed_people/search — search for security people at the company.
    Returns (email, display_name, person_dict).
    person_dict has first_name/last_name for cross-use with Hunter email-finder.
    Docs: https://apolloio.github.io/apollo-api-docs/#people-search
    """
    url = "https://api.apollo.io/v1/mixed_people/search"
    payload = {
        "api_key": api_key,
        "q_organization_domains": domain,
        "person_titles": SECURITY_TITLES,
        "page": 1,
        "per_page": 5,
    }
    try:
        resp = requests.post(url, json=payload, timeout=12)
        resp.raise_for_status()
        people = resp.json().get("people", [])

        if not people:
            logger.debug(f"Apollo: no people found for {domain}")
            return "", "", {}

        # Prefer people whose email is fully revealed (not masked)
        def _has_full_email(p: dict) -> bool:
            email = p.get("email") or ""
            return bool(email) and "***" not in email and "@" in email

        revealed = [p for p in people if _has_full_email(p)]
        candidate = revealed[0] if revealed else people[0]

        first = candidate.get("first_name", "")
        last = candidate.get("last_name", "")
        title = candidate.get("title", "")
        email = candidate.get("email", "")
        full_name = f"{first} {last}".strip()
        display = f"{full_name} ({title})" if title else full_name

        if _has_full_email(candidate):
            return email, display, candidate

        # Email masked — return the person metadata for Hunter cross-lookup
        logger.debug(
            f"Apollo found {full_name} at {domain} but email is masked — "
            "will try Hunter email-finder."
        )
        return "", display, candidate

    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 401:
            logger.warning("Apollo.io: invalid API key (401). Check APOLLO_API_KEY.")
        elif e.response is not None and e.response.status_code == 429:
            logger.warning("Apollo.io: rate limit hit (429). Will retry next run.")
        else:
            logger.warning(f"Apollo people search failed for {domain}: {e}")
    except Exception as e:
        logger.warning(f"Apollo people search error for {domain}: {e}")

    return "", "", {}


# ---------------------------------------------------------------------------
# Strategy 3 — Hunter.io email-finder (name × domain)
# ---------------------------------------------------------------------------

def _hunter_email_finder(
    domain: str, first_name: str, last_name: str, api_key: str
) -> tuple[str, str]:
    """
    GET /v2/email-finder — given a person's name and domain, Hunter guesses
    and verifies the email address.
    Docs: https://hunter.io/api-documentation/v2#email-finder
    """
    url = "https://api.hunter.io/v2/email-finder"
    params = {
        "domain": domain,
        "first_name": first_name,
        "last_name": last_name,
        "api_key": api_key,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        email = data.get("email", "")
        score = data.get("score", 0)
        if email and score >= 30:          # Hunter confidence score 0-100
            full_name = f"{first_name} {last_name}".strip()
            return email, full_name
        elif email:
            logger.debug(
                f"Hunter email-finder returned {email} for {first_name} {last_name} "
                f"but confidence too low ({score}), skipping."
            )
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            logger.debug(f"Hunter email-finder: no result for {first_name} {last_name} @{domain}")
        else:
            logger.warning(f"Hunter email-finder failed: {e}")
    except Exception as e:
        logger.warning(f"Hunter email-finder error: {e}")

    return "", ""


# ---------------------------------------------------------------------------
# Strategy 4 — web mining (GitHub, team pages, DDG)
# ---------------------------------------------------------------------------

def _find_real_employee_email(company_name: str, domain: str) -> tuple[str, str]:
    """Tries several public-web approaches to find a real @domain email."""
    email, name = _search_github_commits(domain)
    if email:
        return email, name

    email, name = _scrape_team_page(domain)
    if email:
        return email, name

    email, name = _search_blog_authors(company_name, domain)
    if email:
        return email, name

    email, name = _ddg_email_search(company_name, domain)
    if email:
        return email, name

    return "", ""


def _search_github_commits(domain: str) -> tuple[str, str]:
    for query in [f'site:github.com "@{domain}"', f'site:github.com "{domain}" email']:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=8))
            for r in results:
                emails = _extract_personal_emails(
                    r.get("body", "") + " " + r.get("title", ""), domain
                )
                if emails:
                    return emails[0], _guess_name_from_email(emails[0])
            time.sleep(0.3)
        except Exception as e:
            logger.debug(f"GitHub email search failed for {domain}: {e}")
    return "", ""


def _scrape_team_page(domain: str) -> tuple[str, str]:
    for path in ["/team", "/about/team", "/people", "/company/team", "/about"]:
        url = f"https://{domain}{path}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=8)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            text = soup.get_text(separator=" ", strip=True)
            emails = _extract_personal_emails(text, domain)
            if emails:
                return emails[0], _guess_name_from_email(emails[0])
            for a in soup.find_all("a", href=re.compile(r"^mailto:")):
                raw = a["href"].replace("mailto:", "").split("?")[0].strip()
                local = raw.split("@")[0].lower() if "@" in raw else ""
                if "@" in raw and local not in GENERIC_LOCALS and raw.endswith(f"@{domain}"):
                    return raw, a.get_text(strip=True) or _guess_name_from_email(raw)
        except Exception as e:
            logger.debug(f"Team page scrape failed for {url}: {e}")
        time.sleep(0.2)
    return "", ""


def _search_blog_authors(company_name: str, domain: str) -> tuple[str, str]:
    for query in [
        f'"{company_name}" blog author "@{domain}"',
        f'site:{domain} author email security',
    ]:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
            for r in results:
                emails = _extract_personal_emails(
                    r.get("body", "") + " " + r.get("title", ""), domain
                )
                if emails:
                    return emails[0], _guess_name_from_email(emails[0])
            time.sleep(0.3)
        except Exception as e:
            logger.debug(f"Blog author search failed for {domain}: {e}")
    return "", ""


def _ddg_email_search(company_name: str, domain: str) -> tuple[str, str]:
    for query in [
        f'"{domain}" "security" -noreply -info -contact email',
        f'"{company_name}" security engineer contact email 2024 2025',
    ]:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=6))
            for r in results:
                emails = _extract_personal_emails(
                    r.get("body", "") + " " + r.get("title", ""), domain
                )
                if emails:
                    return emails[0], _guess_name_from_email(emails[0])
            time.sleep(0.3)
        except Exception as e:
            logger.debug(f"DDG email search failed for {domain}: {e}")
    return "", ""


# ---------------------------------------------------------------------------
# Strategy 5 — named person + email pattern inference
# ---------------------------------------------------------------------------

def _find_named_person(company_name: str) -> tuple[str, str]:
    for role in SECURITY_TITLES:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(f'"{company_name}" "{role}"', max_results=4))
            for r in results:
                name = _extract_person_name(r.get("title", ""), r.get("body", ""), role)
                if name:
                    return name, role
            time.sleep(0.25)
        except Exception as e:
            logger.debug(f"Named person search failed for {company_name}/{role}: {e}")
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(f'"{company_name}" security contact email', max_results=3))
        for r in results:
            name = _extract_person_name(r.get("title", ""), r.get("body", ""), "")
            if name:
                return name, ""
    except Exception:
        pass
    return "", ""


def _extract_person_name(title: str, body: str, role: str) -> str:
    patterns = [
        r"([A-Z][a-z]+ [A-Z][a-z]+)\s*[-–|]\s*(?:Head|CISO|VP|Director|Manager|Engineer|Recruiter)",
        r"([A-Z][a-z]+ [A-Z][a-z]+),?\s+(?:Head|CISO|VP|Director|Manager|Engineer)",
        r"by ([A-Z][a-z]+ [A-Z][a-z]+)",
    ]
    PLACE_NAMES = {
        "New York", "San Francisco", "Los Angeles", "United States",
        "United Kingdom", "North America", "South America",
        "Security Team", "Engineering Manager",
    }
    for text in [title, body]:
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                name = match.group(1)
                if name not in PLACE_NAMES:
                    return name
    return ""


def _infer_email_pattern(company_name: str, domain: str) -> str | None:
    for query in [
        f'site:github.com "@{domain}"',
        f'"{domain}" email -noreply -info',
        f'"{company_name}" "@{domain}" blog author',
    ]:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
            for r in results:
                text = r.get("body", "") + " " + r.get("title", "")
                for email in re.findall(r"[a-zA-Z0-9._%+\-]+@" + re.escape(domain), text):
                    local = email.split("@")[0].lower()
                    if local in GENERIC_LOCALS:
                        continue
                    if "." in local:
                        parts = local.split(".")
                        return "{first}.{last}" if len(parts) == 2 else "{fi}{last}"
                    elif "-" in local:
                        return "{first}-{last}"
                    else:
                        return "{first}"
            time.sleep(0.25)
        except Exception as e:
            logger.debug(f"Pattern inference failed for {domain}: {e}")
    return None


def _apply_pattern(full_name: str, pattern: str, domain: str) -> str:
    parts = full_name.lower().split()
    if len(parts) < 2:
        return ""
    first, last = parts[0], parts[-1]
    try:
        return f"{pattern.format(first=first, last=last, fi=first[0])}@{domain}"
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Strategy 6 — contact page scrape
# ---------------------------------------------------------------------------

def _scrape_contact_page(domain: str) -> str:
    for path in ["/contact", "/about", "/contact-us", "/team", "/people"]:
        url = f"https://{domain}{path}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=8)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "lxml")
                text = soup.get_text(separator=" ", strip=True)
                personal = _extract_personal_emails(text, domain)
                if personal:
                    return personal[0]
                for email in re.findall(
                    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text
                ):
                    local = email.split("@")[0].lower()
                    if local not in {"noreply", "no-reply", "donotreply"}:
                        return email
        except Exception:
            pass
        time.sleep(0.2)
    return ""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _extract_personal_emails(text: str, domain: str) -> list[str]:
    """Extract @domain emails that look like real person addresses."""
    personal = []
    for email in re.findall(r"[a-zA-Z][a-zA-Z0-9._%+\-]{1,40}@" + re.escape(domain), text):
        local = email.split("@")[0].lower()
        if local in GENERIC_LOCALS:
            continue
        if re.match(r"^[a-z]{2,}[.\-_]?[a-z]{2,}", local):
            personal.append(email)
    return personal


def _guess_name_from_email(email: str) -> str:
    """john.doe@company.com  ->  'John Doe'"""
    local = email.split("@")[0]
    parts = [p.capitalize() for p in re.split(r"[.\-_]", local) if len(p) > 1]
    return " ".join(parts) if len(parts) >= 2 else local.capitalize()
