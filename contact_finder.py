from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(__file__)
CONTACTS_LOG = os.path.join(BASE_DIR, "contacts_found.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Security-relevant titles searched by Apollo and DDG fallbacks
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

# Email locals that are NOT personal — never returned as a contact
GENERIC_LOCALS = {
    "noreply", "no-reply", "donotreply", "info", "contact", "support",
    "hello", "team", "press", "media", "legal", "privacy", "abuse",
    "security", "appsec", "careers", "jobs", "recruiting", "hiring",
    "sales", "marketing", "billing", "accounts", "admin", "webmaster",
    "enquiries", "enquiry", "helpdesk", "hr", "office", "operations",
}


# ---------------------------------------------------------------------------
# Domain validation
# ---------------------------------------------------------------------------

def _is_company_domain(company_name: str, domain: str) -> bool:
    """
    Returns True if `domain` plausibly belongs to `company_name`.

    Strategy (any one match → accept):
      1. A meaningful slug of the company name appears inside the domain
         e.g. "Trail of Bits"  → slug "trailofbits"  → found in "trailofbits.com"  ✓
              "Wiz"            → slug "wiz"           → found in "wiz.io"            ✓
              "Armis"          → slug "armis"         → NOT in "army.mil"            ✗
      2. Every individual word in the company name (3+ chars) appears somewhere
         in the domain  (handles abbrev / rebrands like "CrowdStrike" → "crowdstrike")
      3. The first 4+ chars of the slug appear at the start of the domain label
         (handles "Fortinet" → slug "fortinet" in "fortinet.net")
    """
    # Normalise both sides to lowercase alphanumeric
    def _alphanum(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", s.lower())

    slug = _alphanum(company_name)          # "trailofbits", "wiz", "armis"
    domain_clean = _alphanum(domain)        # "trailofbitscom", "wizio", "armymil"
    domain_label = domain.split(".")[0].lower()   # "trailofbits", "wiz", "army"

    # Rule 1: full slug in domain
    if len(slug) >= 3 and slug in domain_clean:
        return True

    # Rule 2: every meaningful word in company name is in the domain
    words = [w for w in re.findall(r"[a-z]{3,}", company_name.lower()) if w not in
             {"the", "and", "for", "inc", "llc", "ltd", "corp", "security",
              "cyber", "tech", "labs", "lab", "group", "systems", "solutions"}]
    if words and all(_alphanum(w) in domain_clean for w in words):
        return True

    # Rule 3: first 4 chars of slug match start of domain label
    if len(slug) >= 4 and domain_label.startswith(slug[:4]):
        return True

    return False


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def find_contact(company_name: str, domain: str) -> tuple[str, str]:
    """
    Returns (email, display_name) for a REAL named person at this company.
    Returns ("", "") if no real person can be found — never returns a generic
    inbox like security@ or careers@.

    Priority chain:
      1. Hunter.io domain search       (HUNTER_API_KEY env var)
      2. Apollo.io people search       (APOLLO_API_KEY env var)
      3. Hunter.io email-finder        (Apollo name × Hunter verification)
      4. GitHub / team page / DDG web mining
      5. Named person + inferred email pattern
      6. Contact page scrape (personal emails only)
    """
    if not domain:
        return "", ""

    # Hard gate: reject the domain if it doesn't plausibly belong to the company.
    # This prevents wrong-domain bugs (e.g. "Armis" resolving to army.mil).
    if not _is_company_domain(company_name, domain):
        logger.warning(
            f"Domain '{domain}' doesn't look like it belongs to '{company_name}' — "
            "skipping to avoid emailing the wrong organisation."
        )
        return "", ""

    hunter_key = os.getenv("HUNTER_API_KEY", "")
    apollo_key = os.getenv("APOLLO_API_KEY", "")

    # ── 1. Hunter.io domain search ───────────────────────────────────────────
    if hunter_key:
        email, name, position = _hunter_domain_search(domain, hunter_key)
        if email:
            logger.info(f"[Hunter domain] {name} ({position}) <{email}>")
            _save_contact(company_name, domain, email, name, position, "hunter.io")
            return email, f"{name} ({position})" if position else name

    # ── 2. Apollo.io people search ───────────────────────────────────────────
    apollo_person: dict = {}
    if apollo_key:
        email, name, position, apollo_person = _apollo_people_search(
            company_name, domain, apollo_key
        )
        if email:
            logger.info(f"[Apollo] {name} ({position}) <{email}>")
            _save_contact(company_name, domain, email, name, position, "apollo.io")
            return email, f"{name} ({position})" if position else name

    # ── 3. Hunter email-finder (Apollo name × Hunter key) ────────────────────
    if hunter_key and apollo_person.get("first_name") and apollo_person.get("last_name"):
        email, name = _hunter_email_finder(
            domain,
            apollo_person["first_name"],
            apollo_person["last_name"],
            hunter_key,
        )
        if email:
            position = apollo_person.get("title", "")
            logger.info(f"[Hunter finder] {name} ({position}) <{email}>")
            _save_contact(company_name, domain, email, name, position, "hunter.io (email-finder)")
            return email, f"{name} ({position})" if position else name

    # ── 4. GitHub / team page / DDG web mining ───────────────────────────────
    email, name, position = _find_real_employee_email(company_name, domain)
    if email:
        logger.info(f"[Web mining] {name} ({position}) <{email}>")
        _save_contact(company_name, domain, email, name, position, "web mining")
        return email, f"{name} ({position})" if position else name

    # ── 5. Named person + inferred email pattern ─────────────────────────────
    person_name, title = _find_named_person(company_name)
    if person_name:
        pattern = _infer_email_pattern(company_name, domain)
        if pattern:
            email = _apply_pattern(person_name, pattern, domain)
            if email:
                logger.info(f"[Pattern] {person_name} ({title}) <{email}> (inferred)")
                _save_contact(company_name, domain, email, person_name, title, "pattern inference")
                return email, f"{person_name} ({title})" if title else person_name

    # ── 6. Contact/team page — personal emails only ──────────────────────────
    email, name = _scrape_contact_page_personal(domain)
    if email:
        logger.info(f"[Page scrape] {name} <{email}>")
        _save_contact(company_name, domain, email, name, "", "page scrape")
        return email, name

    # No real person found — skip this company
    logger.warning(f"No named contact found for {company_name} ({domain}) — skipping.")
    return "", ""


# ---------------------------------------------------------------------------
# Contacts log
# ---------------------------------------------------------------------------

def _save_contact(
    company: str,
    domain: str,
    email: str,
    name: str,
    position: str,
    source: str,
) -> None:
    """
    Append the contact to contacts_found.json.
    Deduplicates by email — won't add the same address twice.
    """
    if os.path.exists(CONTACTS_LOG):
        with open(CONTACTS_LOG, "r", encoding="utf-8") as f:
            contacts: list[dict] = json.load(f)
    else:
        contacts = []

    # Skip if already logged
    existing_emails = {c["email"].lower() for c in contacts}
    if email.lower() in existing_emails:
        return

    contacts.append(
        {
            "name": name,
            "position": position or "—",
            "company": company,
            "email": email,
            "domain": domain,
            "source": source,
            "found_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
    )

    with open(CONTACTS_LOG, "w", encoding="utf-8") as f:
        json.dump(contacts, f, indent=2)


def load_contacts() -> list[dict]:
    """Return all entries from contacts_found.json."""
    if not os.path.exists(CONTACTS_LOG):
        return []
    with open(CONTACTS_LOG, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Strategy 1 — Hunter.io domain search
# ---------------------------------------------------------------------------

def _hunter_domain_search(domain: str, api_key: str) -> tuple[str, str, str]:
    """
    GET /v2/domain-search — returns verified emails Hunter knows for the domain.
    Returns (email, full_name, position). Skips all generic locals.
    """
    url = "https://api.hunter.io/v2/domain-search"
    params = {"domain": domain, "api_key": api_key, "limit": 10, "type": "personal"}
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        emails = resp.json().get("data", {}).get("emails", [])

        # Filter to real personal addresses only
        personal = [
            e for e in emails
            if e.get("value") and e["value"].split("@")[0].lower() not in GENERIC_LOCALS
        ]
        if not personal:
            return "", "", ""

        # Score: security-relevant title → higher
        def _score(e: dict) -> int:
            title = (e.get("position") or "").lower()
            s = e.get("confidence", 0)
            if any(kw in title for kw in [
                "security", "ciso", "appsec", "pentest", "red team",
                "threat", "forensic", "soc", "devsecops", "infosec", "engineer",
            ]):
                s += 50
            return s

        personal.sort(key=_score, reverse=True)
        best = personal[0]
        email = best["value"]
        first = best.get("first_name", "")
        last = best.get("last_name", "")
        full_name = f"{first} {last}".strip() or _guess_name_from_email(email)
        position = best.get("position", "")
        return email, full_name, position

    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        if code == 401:
            logger.warning("Hunter.io: invalid API key (401).")
        elif code == 429:
            logger.warning("Hunter.io: rate limit (429).")
        else:
            logger.warning(f"Hunter domain search failed for {domain}: {e}")
    except Exception as e:
        logger.warning(f"Hunter domain search error for {domain}: {e}")
    return "", "", ""


# ---------------------------------------------------------------------------
# Strategy 2 — Apollo.io people search
# ---------------------------------------------------------------------------

def _apollo_people_search(
    company_name: str, domain: str, api_key: str
) -> tuple[str, str, str, dict]:
    """
    POST /v1/mixed_people/search — find security people at the company.
    Returns (email, full_name, position, person_dict).
    email is "" when Apollo has the person but the email is masked.
    """
    url = "https://api.apollo.io/v1/mixed_people/search"
    # Apollo now requires the key in the X-Api-Key header (not the body)
    headers = {"X-Api-Key": api_key, "Content-Type": "application/json"}
    payload = {
        "q_organization_domains": domain,
        "person_titles": SECURITY_TITLES,
        "page": 1,
        "per_page": 5,
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=12)
        resp.raise_for_status()
        people = resp.json().get("people", [])

        if not people:
            return "", "", "", {}

        def _has_full_email(p: dict) -> bool:
            e = p.get("email") or ""
            return bool(e) and "***" not in e and "@" in e

        revealed = [p for p in people if _has_full_email(p)]
        candidate = revealed[0] if revealed else people[0]

        first = candidate.get("first_name", "")
        last = candidate.get("last_name", "")
        title = candidate.get("title", "")
        email = candidate.get("email", "") if _has_full_email(candidate) else ""
        full_name = f"{first} {last}".strip()

        return email, full_name, title, candidate

    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        if code == 401:
            logger.warning("Apollo.io: invalid API key (401). Check APOLLO_API_KEY.")
        elif code == 403:
            logger.debug(
                "Apollo.io: people search requires a paid plan — skipping Apollo. "
                "Hunter.io will be used instead."
            )
        elif code == 429:
            logger.warning("Apollo.io: rate limit (429).")
        else:
            logger.warning(f"Apollo people search failed for {domain}: {e}")
    except Exception as e:
        logger.warning(f"Apollo people search error for {domain}: {e}")
    return "", "", "", {}


# ---------------------------------------------------------------------------
# Strategy 3 — Hunter.io email-finder
# ---------------------------------------------------------------------------

def _hunter_email_finder(
    domain: str, first_name: str, last_name: str, api_key: str
) -> tuple[str, str]:
    """
    GET /v2/email-finder — construct + verify an email given name + domain.
    Only returns if Hunter confidence >= 30.
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
        local = email.split("@")[0].lower() if email else ""
        if email and local not in GENERIC_LOCALS and score >= 30:
            return email, f"{first_name} {last_name}".strip()
        if email and score < 30:
            logger.debug(f"Hunter email-finder: {email} confidence {score} too low, skipping.")
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            logger.debug(f"Hunter email-finder: no result for {first_name} {last_name}@{domain}")
        else:
            logger.warning(f"Hunter email-finder failed: {e}")
    except Exception as e:
        logger.warning(f"Hunter email-finder error: {e}")
    return "", ""


# ---------------------------------------------------------------------------
# Strategy 4 — web mining (GitHub, team pages, DDG)
# ---------------------------------------------------------------------------

def _find_real_employee_email(company_name: str, domain: str) -> tuple[str, str, str]:
    """Returns (email, name, position) from public web sources."""
    email, name = _search_github_commits(domain)
    if email:
        return email, name, "GitHub"

    email, name = _scrape_team_page(domain)
    if email:
        return email, name, "team page"

    email, name = _search_blog_authors(company_name, domain)
    if email:
        return email, name, "blog"

    email, name = _ddg_email_search(company_name, domain)
    if email:
        return email, name, "web search"

    return "", "", ""


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
            logger.debug(f"GitHub search failed for {domain}: {e}")
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
                name = _extract_person_name(r.get("title", ""), r.get("body", ""))
                if name:
                    return name, role
            time.sleep(0.25)
        except Exception as e:
            logger.debug(f"Named person search failed for {company_name}/{role}: {e}")
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(f'"{company_name}" security contact email', max_results=3))
        for r in results:
            name = _extract_person_name(r.get("title", ""), r.get("body", ""))
            if name:
                return name, ""
    except Exception:
        pass
    return "", ""


def _extract_person_name(title: str, body: str) -> str:
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
# Strategy 6 — contact page scrape (personal emails only)
# ---------------------------------------------------------------------------

def _scrape_contact_page_personal(domain: str) -> tuple[str, str]:
    """Scrape contact/about pages but return ONLY personal-looking emails."""
    for path in ["/contact", "/about", "/contact-us", "/team", "/people"]:
        url = f"https://{domain}{path}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=8)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "lxml")
                text = soup.get_text(separator=" ", strip=True)
                personal = _extract_personal_emails(text, domain)
                if personal:
                    return personal[0], _guess_name_from_email(personal[0])
        except Exception:
            pass
        time.sleep(0.2)
    return "", ""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _extract_personal_emails(text: str, domain: str) -> list[str]:
    """Extract @domain emails that look like a real person (not a generic inbox)."""
    personal = []
    for email in re.findall(r"[a-zA-Z][a-zA-Z0-9._%+\-]{1,40}@" + re.escape(domain), text):
        local = email.split("@")[0].lower()
        if local in GENERIC_LOCALS:
            continue
        # Must match a name-like pattern: at least two letter groups
        if re.match(r"^[a-z]{2,}[.\-_]?[a-z]{2,}", local):
            personal.append(email)
    return personal


def _guess_name_from_email(email: str) -> str:
    """john.doe@company.com  ->  'John Doe'"""
    local = email.split("@")[0]
    parts = [p.capitalize() for p in re.split(r"[.\-_]", local) if len(p) > 1]
    return " ".join(parts) if len(parts) >= 2 else local.capitalize()


# ---------------------------------------------------------------------------
# Email verification — Hunter.io verifier
# ---------------------------------------------------------------------------

def verify_email(email: str) -> bool:
    """
    Verify an email address using Hunter.io's email-verifier endpoint.
    Returns True if the email is deliverable, False if definitely invalid.
    Falls back to True (assume valid) if no API key or rate-limited.

    Statuses:
      valid       → deliverable, return True
      invalid     → undeliverable, return False
      accept_all  → server accepts all mail (can't verify), return True
      webmail     → gmail/yahoo etc, return True
      unknown     → could not determine, return True (optimistic)
    """
    hunter_key = os.getenv("HUNTER_API_KEY", "")
    if not hunter_key:
        return True  # Can't verify without key — optimistic

    url = "https://api.hunter.io/v2/email-verifier"
    params = {"email": email, "api_key": hunter_key}
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        status = data.get("status", "unknown")
        if status == "invalid":
            logger.warning(f"Hunter verified {email} as INVALID — skipping.")
            return False
        logger.debug(f"Hunter email verify: {email} → {status}")
        return True
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else 0
        if code == 429:
            logger.debug("Hunter verifier: rate limit hit, skipping verification.")
        return True  # Optimistic fallback
    except Exception as e:
        logger.debug(f"Hunter email verify error for {email}: {e}")
        return True  # Optimistic fallback


# ---------------------------------------------------------------------------
# CLI — python contact_finder.py
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    contacts = load_contacts()
    if not contacts:
        print("No contacts found yet.")
    else:
        print(f"\n{'='*75}")
        print(f"  {'NAME':<22} {'POSITION':<28} {'COMPANY':<20} {'EMAIL'}")
        print(f"{'='*75}")
        for c in contacts:
            print(
                f"  {c['name']:<22} {c['position']:<28} {c['company']:<20} {c['email']}"
            )
        print(f"{'='*75}")
        print(f"  Total contacts: {len(contacts)}")
        print(f"{'='*75}\n")
