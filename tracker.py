import json
import os
from datetime import date, datetime

BASE_DIR = os.path.dirname(__file__)
TRACKER_PATH = os.path.join(BASE_DIR, "outreach_tracker.json")
SENT_LOG_PATH = os.path.join(BASE_DIR, "sent_companies.json")


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


if __name__ == "__main__":
    print_summary()
