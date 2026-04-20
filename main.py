#!/usr/bin/env python3
from __future__ import annotations
"""
Outreach Tool — Francis Konikkara
Runs two outreach campaigns daily:
  1. Professional: 10 emails to security professionals at companies
  2. PhD: 10 emails to cybersecurity PhD students for research collaboration

Usage:
    python main.py              # Start scheduler (9am weekdays)
    python main.py --run-now    # Run both campaigns immediately
    python main.py --run-now --pro-only   # Only professional outreach
    python main.py --run-now --phd-only   # Only PhD outreach
"""

import argparse
import json
import logging

from dotenv import load_dotenv
load_dotenv()
import os
import random
import sys
import time
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from contact_finder import find_contact, verify_email
from email_writer import write_email, write_phd_email, _classify_target_role
from gmail_sender import send_email
from phd_finder import discover_phd_students, find_student_email
from researcher import discover_companies, research_company
from resume_tailor import tailor_resume
from tracker import (
    add_entry, get_contacted_companies,
    add_phd_entry, get_contacted_phd_emails,
)

BASE_DIR = os.path.dirname(__file__)
TARGET_LIST = os.path.join(BASE_DIR, "target_companies.json")

EMAILS_PER_RUN     = int(os.getenv("EMAILS_PER_RUN", "10"))
PHD_EMAILS_PER_RUN = int(os.getenv("PHD_EMAILS_PER_RUN", "10"))

COMPANY_REFRESH_THRESHOLD = int(os.getenv("COMPANY_REFRESH_THRESHOLD", "15"))
COMPANY_REFRESH_COUNT     = int(os.getenv("COMPANY_REFRESH_COUNT", "20"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("outreach.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _convert_to_pdf(docx_path: str) -> str | None:
    try:
        from docx2pdf import convert
        pdf_path = docx_path.rsplit(".", 1)[0] + ".pdf"
        convert(docx_path, pdf_path)
        return pdf_path
    except Exception as e:
        logger.warning(f"docx2pdf failed: {e}")
        return None


def _load_target_companies(contacted: set[str], count: int) -> list[str]:
    with open(TARGET_LIST) as f:
        data = json.load(f)
    all_companies = []
    for category in data.values():
        if isinstance(category, list):
            all_companies.extend(category)
        elif isinstance(category, dict):
            for sublist in category.values():
                all_companies.extend(sublist)
    fresh = [c for c in all_companies if c.lower() not in contacted]
    random.shuffle(fresh)
    return fresh[:count]


def _refresh_company_list(contacted: set[str]) -> int:
    try:
        with open(TARGET_LIST) as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Could not read {TARGET_LIST}: {e}")
        return 0

    all_companies: list[str] = []
    for category in data.values():
        if isinstance(category, list):
            all_companies.extend(category)
        elif isinstance(category, dict):
            for sublist in category.values():
                all_companies.extend(sublist)

    fresh_count = sum(1 for c in all_companies if c.lower() not in contacted)
    if fresh_count >= COMPANY_REFRESH_THRESHOLD:
        logger.info(f"Company pool has {fresh_count} uncontacted entries — no refresh needed.")
        return 0

    logger.info(f"Only {fresh_count} companies left. Discovering {COMPANY_REFRESH_COUNT} more...")
    existing_lower = {c.lower() for c in all_companies}
    new_companies = discover_companies(contacted | existing_lower, count=COMPANY_REFRESH_COUNT)
    if not new_companies:
        return 0

    if "discovered" not in data:
        data["discovered"] = []
    data["discovered"].extend(new_companies)
    try:
        with open(TARGET_LIST, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Added {len(new_companies)} new companies: {new_companies}")
    except Exception as e:
        logger.error(f"Could not write updated company list: {e}")
        return 0
    return len(new_companies)


# ---------------------------------------------------------------------------
# Campaign 1 — Professional outreach (10 emails to security companies)
# ---------------------------------------------------------------------------

def run_outreach():
    logger.info("=" * 60)
    logger.info(f"[PROFESSIONAL] Starting run at {datetime.now().isoformat()}")

    contacted = get_contacted_companies()
    logger.info(f"Already contacted {len(contacted)} companies.")

    added = _refresh_company_list(contacted)
    if added:
        logger.info(f"Company list refreshed: +{added} new companies.")

    companies = _load_target_companies(contacted, EMAILS_PER_RUN)
    if not companies:
        logger.warning("No new companies to contact.")
        return

    logger.info(f"Targeting: {', '.join(companies)}")
    resume_pdf_env = os.getenv("RESUME_PDF_PATH", "")
    sent_count = 0

    for company_name in companies:
        logger.info(f"--- Processing: {company_name} ---")
        try:
            research = research_company(company_name)
            domain = research.get("domain", "")
            if not domain:
                logger.warning(f"No domain for {company_name}, skipping.")
                continue

            contact_email, contact_name = find_contact(company_name, domain)
            if not contact_email:
                logger.warning(f"No contact found for {company_name}, skipping.")
                continue

            # Verify email is deliverable before sending
            if not verify_email(contact_email):
                logger.warning(f"Email {contact_email} failed verification — skipping {company_name}.")
                continue

            logger.info(f"Contact: {contact_name} <{contact_email}>")

            result = write_email(company_name, contact_name, research)
            if result is None:
                logger.warning(f"Email generation failed for {company_name}, skipping.")
                continue

            subject, body = result
            logger.info(f"Subject: {subject}")
            logger.info(f"Body preview: {body[:120]}...")

            # Resume attachment
            attachment_path = None
            if resume_pdf_env and os.path.exists(resume_pdf_env):
                attachment_path = resume_pdf_env
                logger.info(f"Using pre-built resume PDF: {attachment_path}")
            else:
                role_type = _classify_target_role(research)
                resume_path = tailor_resume(company_name, research, role_type)
                if resume_path:
                    pdf_path = _convert_to_pdf(resume_path)
                    attachment_path = pdf_path if pdf_path else resume_path
                else:
                    logger.warning(f"Resume tailoring skipped for {company_name}.")

            success = send_email(
                to=contact_email, subject=subject, body=body,
                attachment_path=attachment_path,
            )

            if success:
                add_entry(
                    company=company_name, contact_email=contact_email,
                    contact_name=contact_name, subject=subject, status="sent",
                )
                sent_count += 1
                logger.info(f"Sent and logged: {company_name}")
            else:
                logger.error(f"Send failed for {company_name}.")

        except Exception as e:
            logger.error(f"Error processing {company_name}: {e}", exc_info=True)
        time.sleep(2)

    logger.info(f"[PROFESSIONAL] Done. {sent_count}/{len(companies)} sent.")
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# Campaign 2 — PhD outreach (10 collaboration emails to PhD students)
# ---------------------------------------------------------------------------

def run_phd_outreach():
    logger.info("=" * 60)
    logger.info(f"[PHD] Starting run at {datetime.now().isoformat()}")

    contacted_emails = get_contacted_phd_emails()
    logger.info(f"Already contacted {len(contacted_emails)} PhD students.")

    students = discover_phd_students(contacted_emails, count=PHD_EMAILS_PER_RUN)
    if not students:
        logger.warning("[PHD] No new PhD students found.")
        return

    logger.info(f"[PHD] Found {len(students)} candidates.")
    sent_count = 0

    for student in students:
        name     = student.get("name", "Unknown")
        email    = student.get("email", "")
        univ     = student.get("university", "")
        area     = student.get("research_area", "")

        logger.info(f"--- PhD: {name} ({univ}) ---")
        try:
            # Try to find email if missing
            if not email:
                logger.info(f"No email for {name}, searching...")
                email = find_student_email(student)
                student["email"] = email

            if not email:
                logger.warning(f"No email found for {name}, skipping.")
                continue

            # Verify email before sending
            if not verify_email(email):
                logger.warning(f"Email {email} failed verification — skipping {name}.")
                continue

            result = write_phd_email(student)
            if result is None:
                logger.warning(f"Email generation failed for {name}, skipping.")
                continue

            subject, body = result
            logger.info(f"Subject: {subject}")
            logger.info(f"Body preview: {body[:120]}...")

            # No resume attached for PhD outreach — it's a collaboration ask, not a job application
            success = send_email(to=email, subject=subject, body=body)

            if success:
                add_phd_entry(
                    name=name, email=email, university=univ,
                    research_area=area, subject=subject, status="sent",
                )
                sent_count += 1
                logger.info(f"Sent to {name} <{email}>")
            else:
                logger.error(f"Send failed for {name}.")

        except Exception as e:
            logger.error(f"Error processing PhD student {name}: {e}", exc_info=True)
        time.sleep(2)

    logger.info(f"[PHD] Done. {sent_count}/{len(students)} sent.")
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_all():
    """Run both campaigns back to back."""
    run_outreach()
    run_phd_outreach()


def main():
    parser = argparse.ArgumentParser(description="Outreach Tool — Francis Konikkara")
    parser.add_argument("--run-now",   action="store_true", help="Run immediately")
    parser.add_argument("--pro-only",  action="store_true", help="Only professional outreach")
    parser.add_argument("--phd-only",  action="store_true", help="Only PhD outreach")
    args = parser.parse_args()

    if args.run_now:
        logger.info("--run-now flag detected.")
        if args.pro_only:
            run_outreach()
        elif args.phd_only:
            run_phd_outreach()
        else:
            run_all()
    else:
        scheduler = BlockingScheduler()
        scheduler.add_job(run_all, trigger="cron", day_of_week="mon-fri", hour=9, minute=0)
        logger.info("Scheduler started. Will run both campaigns at 9:00am Mon-Fri.")
        logger.info("Press Ctrl+C to stop.")
        try:
            scheduler.start()
        except KeyboardInterrupt:
            logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
