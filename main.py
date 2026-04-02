#!/usr/bin/env python3
from __future__ import annotations
"""
Internship Outreach Tool — Francis Konikkara
Finds security companies, researches them, writes personalized emails, sends via Gmail.
Runs automatically at 8am Mon-Fri via APScheduler (or GitHub Actions cron).

Usage:
    python main.py              # Start scheduler (runs at 8am weekdays)
    python main.py --run-now    # Run immediately, bypass schedule
"""

import argparse
import json
import logging
import os
import random
import sys
import time
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from contact_finder import find_contact
from email_writer import write_email, _classify_target_role
from gmail_sender import send_email
from researcher import research_company
from resume_tailor import tailor_resume
from tracker import add_entry, get_contacted_companies

BASE_DIR = os.path.dirname(__file__)
TARGET_LIST = os.path.join(BASE_DIR, "target_companies.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("outreach.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

EMAILS_PER_RUN = int(os.getenv("EMAILS_PER_RUN", "10"))


def _convert_to_pdf(docx_path: str) -> str | None:
    """Convert DOCX to PDF. Returns PDF path or None on failure."""
    try:
        from docx2pdf import convert
        pdf_path = docx_path.rsplit(".", 1)[0] + ".pdf"
        convert(docx_path, pdf_path)
        return pdf_path
    except Exception as e:
        logger.warning(f"docx2pdf failed: {e}")
        return None


def _load_target_companies(contacted: set[str], count: int) -> list[str]:
    """Load companies from target_companies.json, skip already contacted, return `count` random picks."""
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


def run_outreach():
    logger.info("=" * 60)
    logger.info(f"Starting outreach run at {datetime.now().isoformat()}")

    contacted = get_contacted_companies()
    logger.info(f"Already contacted {len(contacted)} companies.")

    companies = _load_target_companies(contacted, EMAILS_PER_RUN)
    if not companies:
        logger.warning("No new companies found. All targets contacted. Exiting.")
        return

    logger.info(f"Targeting: {', '.join(companies)}")

    # Check for a pre-built resume PDF to attach (no tailoring needed if set)
    resume_pdf_env = os.getenv("RESUME_PDF_PATH", "")

    sent_count = 0

    for company_name in companies:
        logger.info(f"--- Processing: {company_name} ---")

        try:
            # Research
            logger.info(f"Researching {company_name}...")
            research = research_company(company_name)
            domain = research.get("domain", "")

            if not domain:
                logger.warning(f"No domain found for {company_name}, skipping.")
                continue

            # Find contact
            logger.info(f"Finding contact for {company_name} ({domain})...")
            contact_email, contact_name = find_contact(company_name, domain)

            if not contact_email:
                logger.warning(f"No contact found for {company_name}, skipping.")
                continue

            logger.info(f"Contact: {contact_name} <{contact_email}>")

            # Write email
            logger.info(f"Writing email for {company_name}...")
            result = write_email(company_name, contact_name, research)

            if result is None:
                logger.warning(f"Email generation failed for {company_name}, skipping.")
                continue

            subject, body = result
            logger.info(f"Subject: {subject}")
            logger.info(f"Body preview: {body[:120]}...")

            # Determine resume attachment
            attachment_path = None
            if resume_pdf_env and os.path.exists(resume_pdf_env):
                # Use pre-built PDF directly (GitHub Actions mode)
                attachment_path = resume_pdf_env
                logger.info(f"Using pre-built resume PDF: {attachment_path}")
            else:
                # Try to tailor and convert
                role_type = _classify_target_role(research)
                logger.info(f"Tailoring resume for {company_name} ({role_type})...")
                resume_path = tailor_resume(company_name, research, role_type)
                if resume_path:
                    pdf_path = _convert_to_pdf(resume_path)
                    attachment_path = pdf_path if pdf_path else resume_path
                    if pdf_path:
                        logger.info(f"Resume PDF: {pdf_path}")
                    else:
                        logger.warning("PDF conversion failed, attaching DOCX instead")
                else:
                    logger.warning(f"Resume tailoring skipped for {company_name}, sending without attachment")

            # Send
            logger.info(f"Sending to {contact_email}...")
            success = send_email(
                to=contact_email,
                subject=subject,
                body=body,
                attachment_path=attachment_path,
            )

            if success:
                add_entry(
                    company=company_name,
                    contact_email=contact_email,
                    contact_name=contact_name,
                    subject=subject,
                    status="sent",
                )
                sent_count += 1
                logger.info(f"Sent and logged: {company_name}")
            else:
                logger.error(f"Send failed for {company_name}, not logging to tracker.")

        except Exception as e:
            logger.error(f"Unexpected error processing {company_name}: {e}", exc_info=True)
            continue

        time.sleep(2)

    logger.info(f"Run complete. {sent_count}/{len(companies)} emails sent.")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Internship Outreach Tool — Francis Konikkara")
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Run immediately instead of waiting for scheduled time",
    )
    args = parser.parse_args()

    if args.run_now:
        logger.info("--run-now flag detected. Running immediately.")
        run_outreach()
    else:
        scheduler = BlockingScheduler()
        scheduler.add_job(
            run_outreach,
            trigger="cron",
            day_of_week="mon-fri",
            hour=8,
            minute=0,
        )
        logger.info("Scheduler started. Will run at 8:00am Mon-Fri.")
        logger.info("Press Ctrl+C to stop.")
        try:
            scheduler.start()
        except KeyboardInterrupt:
            logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
