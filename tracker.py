import json
import os
from datetime import date, datetime

BASE_DIR = os.path.dirname(__file__)
TRACKER_PATH     = os.path.join(BASE_DIR, "outreach_tracker.json")
SENT_LOG_PATH    = os.path.join(BASE_DIR, "sent_companies.json")
PHD_TRACKER_PATH = os.path.join(BASE_DIR, "phd_tracker.json")


# ---------------------------------------------------------------------------
# Core tracker (deduplication + full metadata)
# ---------------------------------------------------------------------------

def load_tracker() -> list[dict]:
    if not os.path.exists(TRACKER_PATH):
        return []
    with open(TRACKER_PATH, "r") as f:
        return json.load(f)


def get_contacted_companies() -> set[str]:
    tracker = load_tracker()
    return {entry["company"].lower() for entry in tracker}


def add_entry(
    company: str,
    contact_email: str,
    contact_name: str,
    subject: str,
    status: str = "sent",
) -> None:
    tracker = load_tracker()
    tracker.append(
        {
            "company": company,
            "contact_email": contact_email,
            "contact_name": contact_name,
            "date_sent": date.today().isoformat(),
            "subject": subject,
            "status": status,
        }
    )
    with open(TRACKER_PATH, "w") as f:
        json.dump(tracker, f, indent=2)

    # Also write to the human-readable sent log
    _log_sent_company(company, contact_email, contact_name, subject)


# ---------------------------------------------------------------------------
# Human-readable sent log
# ---------------------------------------------------------------------------

def _log_sent_company(
    company: str,
    contact_email: str,
    contact_name: str,
    subject: str,
) -> None:
    """
    Append one entry to sent_companies.json — a flat, human-readable list of
    every company successfully emailed, with timestamp.
    """
    if os.path.exists(SENT_LOG_PATH):
        with open(SENT_LOG_PATH, "r") as f:
            log: list[dict] = json.load(f)
    else:
        log = []

    log.append(
        {
            "company": company,
            "contact_email": contact_email,
            "contact_name": contact_name,
            "subject": subject,
            "sent_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
    )

    with open(SENT_LOG_PATH, "w") as f:
        json.dump(log, f, indent=2)


def load_sent_log() -> list[dict]:
    """Return all entries from sent_companies.json."""
    if not os.path.exists(SENT_LOG_PATH):
        return []
    with open(SENT_LOG_PATH, "r") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# CLI summary
# ---------------------------------------------------------------------------

def print_summary() -> None:
    """Print a summary of all outreach activity."""
    tracker = load_tracker()
    if not tracker:
        print("No outreach activity yet.")
        return

    print(f"\n{'='*60}")
    print(f"Total emails sent: {len(tracker)}")
    print(f"{'='*60}")
    for i, entry in enumerate(tracker, 1):
        print(
            f"{i:>3}. [{entry['date_sent']}] {entry['company']:30} "
            f"-> {entry['contact_email']}"
        )
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# PhD tracker
# ---------------------------------------------------------------------------

def load_phd_tracker() -> list[dict]:
    if not os.path.exists(PHD_TRACKER_PATH):
        return []
    with open(PHD_TRACKER_PATH, "r") as f:
        return json.load(f)


def get_contacted_phd_emails() -> set[str]:
    return {entry["email"].lower() for entry in load_phd_tracker()}


def add_phd_entry(
    name: str,
    email: str,
    university: str,
    research_area: str,
    subject: str,
    status: str = "sent",
) -> None:
    tracker = load_phd_tracker()
    tracker.append(
        {
            "name": name,
            "email": email,
            "university": university,
            "research_area": research_area,
            "date_sent": date.today().isoformat(),
            "subject": subject,
            "status": status,
        }
    )
    with open(PHD_TRACKER_PATH, "w") as f:
        json.dump(tracker, f, indent=2)


def print_phd_summary() -> None:
    tracker = load_phd_tracker()
    if not tracker:
        print("No PhD outreach yet.")
        return
    print(f"\n{'='*70}")
    print(f"PhD outreach emails sent: {len(tracker)}")
    print(f"{'='*70}")
    for i, e in enumerate(tracker, 1):
        print(f"{i:>3}. [{e['date_sent']}] {e['name']:25} {e['university']:20} -> {e['email']}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    print_summary()
    print_phd_summary()
