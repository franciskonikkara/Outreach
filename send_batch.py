#!/usr/bin/env python3
"""
send_batch.py — Manual batch sender for pre-written emails.

Use this to send hand-crafted emails to a specific list of targets
without going through the full automated pipeline.

Usage:
    python send_batch.py
    python send_batch.py --dry-run   # Preview without sending
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from gmail_sender import send_email
from tracker import add_entry

# Path to resume PDF to attach — set via env or update directly
RESUME_PDF = os.getenv("RESUME_PDF_PATH", "resume/Francis_Konikkara_Resume.pdf")

# ---------------------------------------------------------------------------
# Hand-crafted target emails — add your custom targets here
# ---------------------------------------------------------------------------
EMAILS = [
    # Example — replace or extend with your own
    {
        "company": "Trail of Bits",
        "contact_name": "Dan Guido",
        "contact_email": "dan.guido@trailofbits.com",
        "subject": "Agentic AI browser vulnerabilities and a summer intern question",
        "body": """Hi Dan,

Trail of Bits publishing research on prompt injection in agentic browsers, specifically the four attack techniques that exfiltrated Gmail data from Perplexity's Comet, was a rare piece of AI security writing that gave concrete examples instead of generalizations.

I built a full DFIR automation framework as a grad school project — disk/memory/network forensics, SOAR integration with Wazuh, TheHive and Shuffle, and custom MITRE ATT&CK-mapped detection rules. Before UMD, I was at Deloitte supporting ML security workflows and at CybersmithSecure doing penetration testing with Nessus, Burp Suite and Metasploit.

I'm CPT-authorized for summer 2026, no sponsorship needed. If there's a security research intern role open this summer, I'd like to talk.

Francis Konikkara | francisanthony0328@gmail.com | github.com/franciskonikkara""",
    },
    {
        "company": "Bishop Fox",
        "contact_name": "Christie Terrill",
        "contact_email": "cterrill@bishopfox.com",
        "subject": "Cosmos AI vulnerability chaining and summer internship",
        "body": """Hi Christie,

Bishop Fox launching Cosmos AI to find chained vulnerability paths that individual scanners miss addresses the right problem. Most tools still treat findings in isolation.

My background is split between offensive security and DFIR. At CybersmithSecure, I did vulnerability assessments and penetration testing using Nessus, Burp Suite and Metasploit. At UMD, I built a full DFIR automation framework with malware analysis, IR workflow, and Wazuh/TheHive/Shuffle SOAR integration. I also have a Secure CI/CD pipeline project with embedded SAST and container scanning aligned to SOC 2 controls.

I'm CPT-authorized for summer 2026, no sponsorship needed. If there's an offensive security intern position open this summer, I'd like to talk.

Francis Konikkara | francisanthony0328@gmail.com | github.com/franciskonikkara""",
    },
    {
        "company": "Wiz",
        "contact_name": "Ryan Kazanciyan",
        "contact_email": "ryan.kazanciyan@wiz.io",
        "subject": "AI-APP and summer internships at Wiz",
        "body": """Hi Ryan,

Wiz shipping AI-APP and Red Agent right after the Google acquisition close shows where the priority is. Continuous validation using an AI attacker alongside blue and green agents is a practical approach to a problem that static assessments miss.

I've been working on cloud security from a detection and response angle. My DFIR automation framework integrates Wazuh SIEM with custom MITRE ATT&CK detection rules and Shuffle SOAR, and my Secure CI/CD project covers cloud container security aligned to ISO/IEC 27001. At Deloitte, I worked across AWS and Azure supporting enterprise-scale security analytics.

I'm CPT-authorized for summer 2026, no sponsorship needed. If there's a security intern role open this summer, I'd like to talk.

Francis Konikkara | francisanthony0328@gmail.com | github.com/franciskonikkara""",
    },
    {
        "company": "CrowdStrike",
        "contact_name": "Security Recruiting",
        "contact_email": "recruiting@crowdstrike.com",
        "subject": "Security engineering internship — summer 2026",
        "body": """Hi,

CrowdStrike's Falcon platform approach to combining EDR, threat intelligence, and cloud security in one agent is something I've studied closely while building my own detection engineering lab.

I built a SIEM and detection engineering lab on the ELK stack with detection rules mapped to MITRE ATT&CK techniques and attack simulation workflows — similar problems at a smaller scale. My DFIR automation framework covers memory forensics using Volatility 3, network forensics with Scapy, and IR workflow following PICERL with Wazuh, TheHive, and Shuffle SOAR integration.

At Deloitte, I supported ML security workflows across AWS and Azure. Earlier, I did penetration testing and vulnerability assessments at CybersmithSecure.

I'm CPT-authorized for summer 2026, no sponsorship needed. If there's a security engineering intern position open this summer, I'd like to talk.

Francis Konikkara | francisanthony0328@gmail.com | github.com/franciskonikkara""",
    },
    {
        "company": "Snyk",
        "contact_name": "Danny Allan",
        "contact_email": "danny.allan@snyk.io",
        "subject": "AI-generated code vulnerabilities and Evo AI-SPM",
        "body": """Hi Danny,

Snyk finding that nearly half of AI-generated code has vulnerabilities and then shipping Evo AI-SPM to inventory LLMs and MCP servers across repos is a direct response to a problem that's growing faster than most security teams track.

My Secure CI/CD Pipeline project embeds SAST, secrets scanning, and container vulnerability scanning into a compliance-ready pipeline with policy-as-code gates aligned to SOC 2 and ISO/IEC 27001. I also built a DFIR automation framework with supply chain threat intelligence integration via MISP and AlienVault OTX. At Deloitte, I supported ML feedback pipelines with secure data handling requirements.

I'm CPT-authorized for summer 2026, no sponsorship needed. If there's a security intern role open this summer, I'd like to talk.

Francis Konikkara | francisanthony0328@gmail.com | github.com/franciskonikkara""",
    },
]


def main():
    parser = argparse.ArgumentParser(description="Manual batch email sender")
    parser.add_argument("--dry-run", action="store_true", help="Preview emails without sending")
    args = parser.parse_args()

    resume_path = RESUME_PDF if os.path.exists(RESUME_PDF) else None
    if not resume_path:
        print(f"WARNING: Resume not found at {RESUME_PDF}. Sending without attachment.")

    sent = 0
    failed = 0

    for e in EMAILS:
        print(f"\n{'='*50}")
        print(f"To:      {e['contact_name']} <{e['contact_email']}>")
        print(f"Company: {e['company']}")
        print(f"Subject: {e['subject']}")
        print(f"Body:\n{e['body']}")

        if args.dry_run:
            print("[DRY RUN] Would send this email.")
            continue

        ok = send_email(
            to=e["contact_email"],
            subject=e["subject"],
            body=e["body"],
            attachment_path=resume_path,
        )
        if ok:
            add_entry(
                company=e["company"],
                contact_email=e["contact_email"],
                contact_name=e["contact_name"],
                subject=e["subject"],
                status="sent",
            )
            sent += 1
        else:
            failed += 1
        time.sleep(2)

    if not args.dry_run:
        print(f"\n{'='*50}")
        print(f"Done. {sent} sent, {failed} failed.")


if __name__ == "__main__":
    main()
