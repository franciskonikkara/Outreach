import json
import os
from datetime import date

TRACKER_PATH = os.path.join(os.path.dirname(__file__), "outreach_tracker.json")


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
