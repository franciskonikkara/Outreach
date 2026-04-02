from __future__ import annotations

import logging
import os

import anthropic

logger = logging.getLogger(__name__)

ABOUT_ME = """
Name: Francis Anthony Konikkara
Email: francisanthony0328@gmail.com
GitHub: github.com/franciskonikkara
LinkedIn: linkedin.com/in/francis-anthony-konikkara-5721021bb
Location: College Park, MD (open to any location — remote or in-person)
Status: F-1 visa, CPT-authorized for summer 2026 — no visa sponsorship needed
Education: MEng Cybersecurity Engineering, University of Maryland (graduating May 2027)

Experience:
- Analyst, Deloitte Touche Tomatsu LLP — Oct 2023 to Jul 2025. Supported security-adjacent analytics and
  machine learning workflows using Python and JavaScript. Worked across AWS and Azure for enterprise-scale
  analytics. Assisted in secure data handling, model evaluation, and feedback pipelines for ML systems.
  Coordinated deliverables across cross-functional teams while maintaining security and compliance requirements.
- Full Stack Development Intern, Zedex Info Pvt. Ltd — Jul 2022 to Apr 2023. Designed and deployed a secure
  web-based ERP system using React, Node.js, and GraphQL. Implemented authentication, authorization, API
  security controls, and secure logging. Integrated third-party APIs with validation and error-handling.
- Information Security Analyst Intern, CybersmithSecure Pvt Ltd — Apr 2021 to Aug 2021. Conducted
  vulnerability assessments and penetration testing using Nessus, Burp Suite, and Metasploit. Identified
  web, network, and configuration vulnerabilities and supported remediation planning. Authored detailed
  technical reports.

Projects:
- DFIR Automation Framework (github.com/franciskonikkara/DFIR-Project): Full DFIR automation combining
  SOC automation with comprehensive DFIR capabilities. Modules: disk/memory/network forensics, IR workflow
  (PICERL), malware analysis (static + dynamic), threat hunting (7 hypotheses), Wazuh/TheHive/Shuffle SOAR
  integration, VirusTotal/MISP/AlienVault OTX threat intel, 10 custom MITRE ATT&CK-mapped Wazuh rules.
- Secure CI/CD Pipeline (DevSecOps): Compliance-ready CI/CD pipeline with embedded SAST, secrets scanning,
  and container vulnerability scanning. Policy-as-code security gates with audit-grade evidence aligned
  with SOC 2 and ISO/IEC 27001 controls.
- SIEM & Detection Engineering Lab: ELK-based SIEM platform to ingest, normalize, and analyze security
  logs. Detection rules mapped to MITRE ATT&CK techniques, attack scenario simulation, SOC triage and
  incident response workflows.
- Malware Analysis Lab: Static and dynamic analysis of Windows and Linux malware samples. IOC extraction,
  execution behavior analysis, reverse engineering and sandboxing techniques.

Skills: Python, Go, JavaScript, TypeScript, Bash, PowerShell, SQL, ReactJS, Django, Flask, Node.js |
        Nessus, Metasploit, Burp Suite, Wireshark, Nmap, OSINT |
        Splunk, ELK, Wazuh, TheHive, Shuffle | AWS, Azure, GCP, Docker, Kubernetes, Terraform |
        MITRE ATT&CK, OWASP Top 10, Sigma, YARA, Volatility 3, Scapy
Certs: Certified Ethical Hacker (CEH), Practical Ethical Hacking (TCM Security)
CTF: UMBC Nightwing CTF (3rd Place), Fword CTF, Cyber Apocalypse CTF
"""

HUMANIZER_RULES = """
STRICT HUMANIZER RULES (25 AI-pattern checks):

=== BANNED WORDS AND PHRASES (instant reject if any appear) ===
Additionally, Furthermore, Moreover, testament to, landscape, showcasing, delve, crucial,
vital, leverage, utilize, impactful, passionate, excited, eager, genuinely, straightforward,
delighted, thrilled, pivotal, groundbreaking, remarkable, incredible, impressive, breathtaking.

=== BANNED CONSTRUCTIONS ===
- No bullet points or lists in the email body
- No em dashes. One comma or period instead.
- No rule-of-three ("I bring X, Y, and Z"). Use one or two items.
- No "It's not just X, it's Y" negative parallelisms. Say Y directly.
- No "from X to Y" false ranges that pad rather than inform.
- No "serves as", "acts as", "functions as". Use "is" or "has".
- No synonym cycling. Pick the clearest word and repeat it.
- No significance inflation ("pivotal moment", "landmark"). State the fact.
- No formulaic challenges ("despite facing challenges"). Name the actual problem or skip it.
- No excessive hedging ("could potentially possibly"). One modifier max.
- No filler: "In order to" -> "to". "Due to the fact that" -> "because".
- No generic conclusions or platitudes.
- No sycophantic openers ("Great question!", "Absolutely!").
- No chatbot artifacts ("I hope this helps!", "Let me know if...").
- No bold, headers, or formatting. Plain prose only.

=== BANNED EMAIL OPENERS ===
- "I hope this email finds you well"
- "I came across your company and was immediately drawn to..."
- "I've always admired..."
- "Your company is doing incredible things"
- "I've long followed your work"
- "I am a passionate/dedicated/driven student seeking..."

=== WHAT TO DO ===
- Opening: one specific sentence about something real and current about the company. A product detail,
  a recent blog post, a specific problem they solve. Not a compliment. A factual observation.
- Background: 2-3 sentences. Match to what this company does. Pick the most relevant parts of Francis's
  background. Do not dump everything.
- One project mention: DFIR Framework for incident response/SOC/forensics. CI/CD Pipeline for DevSecOps.
  SIEM lab for detection engineering/threat hunting. Malware lab for malware analysis. One line.
- CPT line: "I'm CPT-authorized for summer 2026, no sponsorship needed."
- Ask: "If there's a security intern role open this summer, I'd like to talk." Direct, not desperate.
- Sign-off: Francis Konikkara | francisanthony0328@gmail.com | github.com/franciskonikkara

=== LENGTH AND TONE ===
- 150-200 words. Hard cap.
- Direct and confident. Like someone with real work behind them reaching out because the company is
  genuinely interesting.
- Subject line: specific and human. NOT "Internship Application — Summer 2026 — Francis Konikkara"

=== FINAL AUDIT ===
After writing, re-read the email and check for any of the 25 banned patterns above. If any slip through,
rewrite that sentence.
"""

SYSTEM_PROMPT = (
    "You are writing a cold outreach email on behalf of Francis Konikkara, "
    "a cybersecurity graduate student and practitioner. Write in his voice — direct, "
    "confident, specific, no AI-speak. Follow the humanizer rules exactly."
)


def _classify_target_role(company_research: dict) -> str:
    """Pick the most relevant role angle based on company description."""
    text = (
        company_research.get("description", "")
        + " "
        + company_research.get("recent_news", "")
        + " "
        + company_research.get("open_roles", "")
    ).lower()

    if any(kw in text for kw in ["bug bounty", "penetration", "red team", "offensive", "pentest"]):
        return "offensive security / red team"
    if any(kw in text for kw in ["ai", "machine learning", "llm", "ml security"]):
        return "AI security / product security"
    if any(kw in text for kw in ["cloud", "cspm", "aws", "azure", "kubernetes", "container"]):
        return "cloud security"
    if any(kw in text for kw in ["soc", "siem", "threat", "detection", "incident response"]):
        return "SOC / threat detection"
    if any(kw in text for kw in ["forensic", "dfir", "incident", "malware", "artifact"]):
        return "DFIR / forensics"
    if any(kw in text for kw in ["devsecops", "ci/cd", "sast", "supply chain", "sbom"]):
        return "DevSecOps / AppSec"
    if any(kw in text for kw in ["iot", "embedded", "firmware", "hardware", "ot", "ics"]):
        return "embedded / IoT security"
    return "general security engineering"


def _call_claude(prompt: str) -> str:
    """Call Anthropic API with a prompt and return the text response."""
    try:
        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except Exception as e:
        logger.error(f"Anthropic API call failed: {e}")
        return ""


def write_email(
    company_name: str,
    contact_name: str,
    company_research: dict,
) -> tuple[str, str] | None:
    """
    Returns (subject, body) or None on failure.
    """
    target_role = _classify_target_role(company_research)

    research_block = f"""
Company: {company_name}
Homepage: {company_research.get('homepage_url', 'N/A')}
Description: {company_research.get('description', 'N/A')[:800]}
Recent news/blog: {company_research.get('recent_news', 'N/A')[:500]}
Open roles: {company_research.get('open_roles', 'N/A')[:400]}
"""

    prompt = f"""{SYSTEM_PROMPT}

Write a cold internship outreach email to {contact_name or 'the security team'} at {company_name}.

About the company (from research):
{research_block}

About Francis:
{ABOUT_ME}

Target role: {target_role}

{HUMANIZER_RULES}

Output ONLY the email — subject line first (no "Subject:" prefix), then a blank line, then the body. Nothing else. No preamble."""

    try:
        raw = _call_claude(prompt)
        if not raw:
            logger.error(f"Empty response from Anthropic API for {company_name}")
            return None
        return _parse_email(raw)
    except Exception as e:
        logger.error(f"Claude call failed for {company_name}: {e}")
        return None


def _parse_email(raw: str) -> tuple[str, str] | None:
    """Split raw output into (subject, body)."""
    lines = raw.strip().splitlines()
    if not lines:
        return None

    subject = ""
    body_start = 0
    for i, line in enumerate(lines):
        line = line.strip()
        if line:
            subject = line
            body_start = i + 1
            break

    while body_start < len(lines) and not lines[body_start].strip():
        body_start += 1

    body = "\n".join(lines[body_start:]).strip()

    if not subject or not body:
        return None

    return subject, body
