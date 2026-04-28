from __future__ import annotations

import logging
import os

import anthropic

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Francis's profile — source of truth for all emails
# ---------------------------------------------------------------------------

ABOUT_ME = """
Name: Francis Anthony Konikkara
Email: francisanthony0328@gmail.com
GitHub: github.com/franciskonikkara
LinkedIn: linkedin.com/in/francis-anthony-konikkara-5721021bb
Location: College Park, MD (open to any location — remote or in-person)
Status: F-1 visa, CPT-authorized for summer 2026 — no visa sponsorship needed
Education: MEng Cybersecurity Engineering, University of Maryland (graduating May 2027)

Experience:
- Analyst, Deloitte Touche Tomatsu LLP — Oct 2023 to Jul 2025. Security-adjacent analytics and
  ML workflows using Python and JavaScript across AWS and Azure. Secure data handling, model
  evaluation, feedback pipelines.
- Full Stack Development Intern, Zedex Info Pvt. Ltd — Jul 2022 to Apr 2023. Secure ERP system
  in React, Node.js, GraphQL. Authentication, authorization, API security, secure logging.
- Information Security Analyst Intern, CybersmithSecure Pvt Ltd — Apr 2021 to Aug 2021.
  Vulnerability assessments and penetration testing using Nessus, Burp Suite, Metasploit.

Projects (pick ONE that matches the company — do not mention all of them):
- DFIR Automation Framework (github.com/franciskonikkara/DFIR-Project): disk/memory/network
  forensics, IR workflow (PICERL), malware analysis, threat hunting (7 hypotheses),
  Wazuh/TheHive/Shuffle SOAR, VirusTotal/MISP/AlienVault OTX, 10 MITRE ATT&CK-mapped rules.
  USE FOR: DFIR, forensics, incident response, malware, SOC, threat detection companies.
- Secure CI/CD Pipeline (DevSecOps): SAST, secrets scanning, container scanning, policy-as-code
  gates aligned with SOC 2 and ISO/IEC 27001.
  USE FOR: DevSecOps, AppSec, cloud security, compliance companies.
- SIEM & Detection Engineering Lab: ELK SIEM, MITRE ATT&CK detection rules, attack simulation.
  USE FOR: SIEM vendors, detection engineering, threat hunting, SOC automation companies.
- Malware Analysis Lab: static and dynamic analysis, IOC extraction, reverse engineering.
  USE FOR: malware analysis, reverse engineering, threat intelligence, EDR companies.

Skills: Python, Go, Bash, Nessus, Metasploit, Burp Suite, Wireshark, Splunk, ELK, Wazuh,
        Volatility 3, YARA, Sigma, MITRE ATT&CK, AWS, Azure, Docker, Kubernetes
Certs: CEH, Practical Ethical Hacking (TCM Security)
CTF: UMBC Nightwing CTF (3rd Place), Fword CTF, Cyber Apocalypse CTF
"""

# ---------------------------------------------------------------------------
# Per-role project mapping — tells Claude exactly which project to highlight
# ---------------------------------------------------------------------------

PROJECT_MAP = {
    "DFIR / forensics": (
        "DFIR Automation Framework",
        "built a full DFIR automation framework covering disk/memory/network forensics, "
        "PICERL IR workflow, malware analysis, and threat hunting with Wazuh/TheHive/Shuffle "
        "SOAR and 10 custom MITRE ATT&CK-mapped detection rules "
        "(github.com/franciskonikkara/DFIR-Project)"
    ),
    "SOC / threat detection": (
        "SIEM & Detection Engineering Lab",
        "built an ELK-based SIEM with MITRE ATT&CK-mapped detection rules, attack simulation, "
        "and SOC triage workflows — also integrated Wazuh with custom detection rules in my "
        "DFIR framework"
    ),
    "malware analysis": (
        "Malware Analysis Lab + DFIR Framework",
        "built a malware analysis lab covering static and dynamic analysis, IOC extraction, "
        "and reverse engineering, with sandboxing and Volatility 3 for memory forensics as "
        "part of my DFIR automation framework"
    ),
    "offensive security / red team": (
        "penetration testing work + CTF",
        "did hands-on penetration testing at CybersmithSecure using Nessus, Burp Suite, and "
        "Metasploit, hold a CEH, and placed 3rd at UMBC Nightwing CTF"
    ),
    "DevSecOps / AppSec": (
        "Secure CI/CD Pipeline",
        "built a compliance-ready CI/CD pipeline with SAST, secrets scanning, container "
        "scanning, and policy-as-code security gates aligned with SOC 2 and ISO/IEC 27001"
    ),
    "cloud security": (
        "Secure CI/CD + Deloitte cloud work",
        "built a DevSecOps pipeline with container scanning and policy-as-code, and spent "
        "two years at Deloitte working across AWS and Azure on enterprise-scale analytics "
        "with secure data handling and compliance requirements"
    ),
    "AI security / product security": (
        "ML security work at Deloitte + DFIR Framework",
        "worked on ML model evaluation and secure data pipelines at Deloitte, and my DFIR "
        "framework includes threat intel integration and automated detection logic that could "
        "apply to ML-assisted security workflows"
    ),
    "embedded / IoT security": (
        "penetration testing + low-level tooling",
        "did vulnerability assessments at CybersmithSecure and have hands-on experience "
        "with Nessus, Burp Suite, and Metasploit — currently building detection tools "
        "using Scapy for network-level analysis"
    ),
    "general security engineering": (
        "DFIR Automation Framework",
        "built a full DFIR automation framework covering forensics, incident response, "
        "malware analysis, and threat hunting with Wazuh SOAR integration and MITRE "
        "ATT&CK-mapped detection rules (github.com/franciskonikkara/DFIR-Project)"
    ),
}

# ---------------------------------------------------------------------------
# Humanizer rules — professional outreach
# ---------------------------------------------------------------------------

HUMANIZER_RULES = """
STRICT EMAIL STRUCTURE (follow this order exactly):

SENTENCE 1 — THEIR WORK:
  Mention one specific, real, verifiable thing about what this company does or recently
  published. Name a product feature, a specific blog post topic, a CVE they patched, a
  tool they released, or a concrete technical problem they solve.
  NOT a compliment ("Your work is impressive"). NOT vague ("You do interesting security work").
  A FACT. Example: "Cloudflare's blog post on blocking 230 billion threats daily using
  their Radar dataset caught my attention because of how the detection pipeline scales."

SENTENCES 2-3 — FRANCIS'S MATCHING WORK:
  Describe what Francis built that directly connects to what they do. Name the project.
  Name the specific technology or technique. Show the parallel.
  Example: "I built a DFIR automation framework that integrates Wazuh, TheHive, and Shuffle
  for SOC triage, with 10 custom MITRE ATT&CK-mapped detection rules — the detection
  engineering problem you're working on at scale is exactly what I want to work on next."

SENTENCE 4 — CPT LINE:
  "I'm CPT-authorized for summer 2026, no sponsorship needed."

SENTENCE 5 — THE ASK:
  "If there's a security intern role open this summer, I'd like to talk."
  Direct. Not desperate. Not "I would be honored."

SIGN-OFF:
  Francis Konikkara | francisanthony0328@gmail.com | github.com/franciskonikkara

=== BANNED WORDS (instant fail if any appear) ===
Additionally, Furthermore, Moreover, testament to, landscape, showcasing, delve, crucial,
vital, leverage, utilize, impactful, passionate, excited, eager, genuinely, straightforward,
delighted, thrilled, pivotal, groundbreaking, remarkable, incredible, impressive, breathtaking,
synergy, opportunity, journey.

=== BANNED CONSTRUCTIONS ===
- No bullet points or lists in the body
- No em dashes
- No "I hope this email finds you well"
- No "I came across your company"
- No "I've always admired"
- No "Your company is doing incredible/amazing things"
- No rule-of-three ("X, Y, and Z skills")
- No "serves as / acts as / functions as"
- No sycophantic openers
- No chatbot closings ("Looking forward to hearing from you!", "Let me know if...")
- No bold, headers, or markdown formatting

=== LENGTH ===
150-200 words total. Hard cap. Every sentence must earn its place.

=== SUBJECT LINE ===
Reference what THEY are working on specifically. Not "Internship Application".
Example: "Cloudflare's threat detection pipeline — summer 2026"
"""

SYSTEM_PROMPT = (
    "You are writing a cold outreach email on behalf of Francis Konikkara, "
    "a cybersecurity graduate student. Write in his voice — direct, confident, specific. "
    "The email must lead with something specific about the company's work, "
    "then connect it to Francis's own projects. No AI-speak. No flattery."
)

# ---------------------------------------------------------------------------
# Humanizer rules — PhD collaboration outreach
# ---------------------------------------------------------------------------

PHD_HUMANIZER_RULES_WITH_PAPER = """
STRICT EMAIL STRUCTURE (follow this order exactly):

SENTENCE 1 — THEIR SPECIFIC PAPER:
  Reference the exact paper title provided. Make one specific, technical observation about
  the problem it addresses or the approach it takes.
  NOT a compliment ("Your paper is impressive"). A factual technical statement.
  Example: "Your paper on coverage-guided fuzzing for network protocol parsers addresses
  the exact blind spot AFL misses on stateful inputs."

SENTENCES 2-3 — FRANCIS'S PARALLEL WORK:
  Describe what Francis built that directly connects to that paper. Name the project.
  Name the specific technique or artifact. Make the overlap concrete.
  Example: "I'm building a DFIR automation framework that does memory forensics with
  Volatility 3 and threat hunting against 7 hypotheses — the malware persistence
  techniques your paper analyzes are exactly what I'm trying to detect at the artifact level."

SENTENCE 4 — THE ASK:
  One concrete ask. A 20-minute call about a specific technical problem or gap in their work.
  NOT "I'd love to collaborate". NOT vague interest.
  Example: "Would you be open to a 20-minute call about how you're handling evasion
  in your dynamic analysis pipeline?"

SIGN-OFF:
  Francis Konikkara | francisanthony0328@gmail.com | github.com/franciskonikkara

=== BANNED WORDS ===
Additionally, Furthermore, Moreover, testament to, landscape, showcasing, delve, crucial,
vital, leverage, utilize, impactful, passionate, excited, eager, genuinely, straightforward,
delighted, thrilled, pivotal, groundbreaking, remarkable, incredible, impressive, breathtaking,
synergy, collaboration opportunities, mutually beneficial, mentorship.

=== BANNED CONSTRUCTIONS ===
- No bullet points
- No em dashes
- No "I hope this email finds you well"
- No "I've always admired your research"
- No "Your work is groundbreaking"
- No "I would love to pick your brain"
- No "I am a passionate student seeking mentorship"
- No chatbot closings
- NEVER invent, guess, or paraphrase a paper title not explicitly given to you

=== LENGTH ===
120-160 words. Hard cap.

=== SUBJECT LINE ===
Reference the specific paper topic. NOT "Collaboration request".
Example: "Memory forensics for malware persistence — connecting to your evasion work"
"""

PHD_HUMANIZER_RULES_NO_PAPER = """
STRICT EMAIL STRUCTURE (follow this order exactly):

SENTENCE 1 — THEIR RESEARCH AREA:
  Name the specific technical problem they work on (from the research area provided).
  Make a concrete, factual technical observation about that problem space.
  NOT a compliment. NOT vague. A technical statement about the problem itself.
  Example: "Binary analysis for firmware vulnerabilities has a coverage problem that
  most static tools don't solve well — you're working on exactly that."
  IMPORTANT: Do NOT reference a specific paper title. You were not given one.
  Do NOT invent a paper title. If you cannot name a real paper, describe the research
  area's problem concretely.

SENTENCES 2-3 — FRANCIS'S PARALLEL WORK:
  Describe what Francis built that directly overlaps with their research area.
  Name the project. Name the specific technique. Show the connection concretely.

SENTENCE 4 — THE ASK:
  One concrete ask tied to their research area. A specific question or call request.
  NOT "I'd love to collaborate". NOT vague interest.

SIGN-OFF:
  Francis Konikkara | francisanthony0328@gmail.com | github.com/franciskonikkara

=== BANNED WORDS ===
Additionally, Furthermore, Moreover, testament to, landscape, showcasing, delve, crucial,
vital, leverage, utilize, impactful, passionate, excited, eager, genuinely, straightforward,
delighted, thrilled, pivotal, groundbreaking, remarkable, incredible, impressive, breathtaking,
synergy, collaboration opportunities, mutually beneficial, mentorship.

=== BANNED CONSTRUCTIONS ===
- No bullet points
- No em dashes
- No "I hope this email finds you well"
- No "I've always admired your research"
- No "Your work is groundbreaking"
- No "I would love to pick your brain"
- No "I am a passionate student seeking mentorship"
- No chatbot closings
- NEVER invent or hallucinate a paper title — you were not given one

=== LENGTH ===
120-160 words. Hard cap.

=== SUBJECT LINE ===
Reference their research area specifically. NOT "Collaboration request".
Example: "Binary firmware analysis — connecting on detection at the artifact level"
"""

PHD_SYSTEM_PROMPT = (
    "You are writing a research outreach email on behalf of Francis Konikkara, "
    "a cybersecurity graduate student at UMD. Write peer-to-peer — direct, specific, "
    "technical. Lead with their research, then show Francis's parallel work. "
    "No flattery. No AI-speak."
)


# ---------------------------------------------------------------------------
# Role classifier
# ---------------------------------------------------------------------------

def _classify_target_role(company_research: dict) -> str:
    text = (
        company_research.get("description", "")
        + " " + company_research.get("recent_news", "")
        + " " + company_research.get("open_roles", "")
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


def _select_project(role_type: str) -> tuple[str, str]:
    """Return (project_name, project_description) for this role type."""
    return PROJECT_MAP.get(role_type, PROJECT_MAP["general security engineering"])


# ---------------------------------------------------------------------------
# Claude wrapper
# ---------------------------------------------------------------------------

def _call_claude(prompt: str) -> str:
    try:
        client = anthropic.Anthropic()
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except Exception as e:
        logger.error(f"Anthropic API call failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Professional outreach email
# ---------------------------------------------------------------------------

def write_email(
    company_name: str,
    contact_name: str,
    company_research: dict,
) -> tuple[str, str] | None:
    """Returns (subject, body) or None on failure."""
    role_type = _classify_target_role(company_research)
    project_name, project_desc = _select_project(role_type)

    research_block = f"""
Company: {company_name}
What they do: {company_research.get('description', 'N/A')[:600]}
Recent news / blog posts / products: {company_research.get('recent_news', 'N/A')[:500]}
Open roles: {company_research.get('open_roles', 'N/A')[:300]}
Role angle for this email: {role_type}
"""

    prompt = f"""{SYSTEM_PROMPT}

Write a cold internship outreach email to {contact_name or 'the security team'} at {company_name}.

--- COMPANY RESEARCH (use this to write sentence 1 about THEIR work) ---
{research_block}

--- FRANCIS'S PROJECT TO HIGHLIGHT (use this for sentences 2-3 about HIS work) ---
Project: {project_name}
What he built: {project_desc}

--- FULL PROFILE (for CPT line and sign-off only — do NOT dump everything) ---
{ABOUT_ME}

--- RULES ---
{HUMANIZER_RULES}

Output ONLY the email — subject line first (no "Subject:" prefix), blank line, then body. Nothing else."""

    try:
        raw = _call_claude(prompt)
        if not raw:
            logger.error(f"Empty response for {company_name}")
            return None
        return _parse_email(raw)
    except Exception as e:
        logger.error(f"Claude call failed for {company_name}: {e}")
        return None


# ---------------------------------------------------------------------------
# PhD collaboration email
# ---------------------------------------------------------------------------

def write_phd_email(student: dict) -> tuple[str, str] | None:
    """Returns (subject, body) or None on failure."""
    name = student.get("name", "the researcher")
    first_name = name.split()[0] if name else "Hi"
    university = student.get("university", "your university")
    research_area = student.get("research_area", "cybersecurity")
    recent_work = student.get("recent_work", "")

    # Pick the Francis project most relevant to their research area
    area_lower = research_area.lower()
    if any(kw in area_lower for kw in ["malware", "reverse", "binary", "exploit", "vulnerability"]):
        project_name, project_desc = _select_project("malware analysis")
    elif any(kw in area_lower for kw in ["forensic", "dfir", "incident", "artifact", "memory"]):
        project_name, project_desc = _select_project("DFIR / forensics")
    elif any(kw in area_lower for kw in ["detection", "siem", "threat hunt", "soc", "sigma"]):
        project_name, project_desc = _select_project("SOC / threat detection")
    elif any(kw in area_lower for kw in ["devsecops", "supply chain", "appsec", "sast", "fuzzing"]):
        project_name, project_desc = _select_project("DevSecOps / AppSec")
    elif any(kw in area_lower for kw in ["network", "protocol", "traffic", "intrusion"]):
        project_name, project_desc = _select_project("DFIR / forensics")
    else:
        project_name, project_desc = _select_project("general security engineering")

    # Choose rules based on whether a REAL verified paper title is available.
    # If recent_work is empty or blank, we must NOT hallucinate one — use the
    # no-paper ruleset which instructs Claude to describe the research area instead.
    has_real_paper = bool(recent_work and recent_work.strip())
    rules = PHD_HUMANIZER_RULES_WITH_PAPER if has_real_paper else PHD_HUMANIZER_RULES_NO_PAPER

    if has_real_paper:
        their_work_block = (
            f"Research area: {research_area}\n"
            f"Specific verified paper title (use this — do NOT change or paraphrase it): "
            f"{recent_work.strip()}"
        )
    else:
        their_work_block = (
            f"Research area: {research_area}\n"
            f"NOTE: No specific paper title is available. Reference the research area "
            f"concretely. Do NOT invent a paper title."
        )

    prompt = f"""{PHD_SYSTEM_PROMPT}

Write a research outreach email to {first_name} ({name}), PhD student at {university}.

--- THEIR RESEARCH (lead the email with this — be specific and technical) ---
{their_work_block}

--- FRANCIS'S PROJECT THAT CONNECTS TO THEIR WORK (use for sentences 2-3) ---
Project: {project_name}
What he built: {project_desc}

--- FRANCIS'S FULL PROFILE (for context — do not dump everything) ---
{ABOUT_ME}

--- RULES ---
{rules}

Output ONLY the email — subject line first (no "Subject:" prefix), blank line, then body. Nothing else."""

    try:
        raw = _call_claude(prompt)
        if not raw:
            logger.error(f"Empty response for PhD email to {name}")
            return None
        return _parse_email(raw)
    except Exception as e:
        logger.error(f"Claude call failed for PhD email to {name}: {e}")
        return None


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _parse_email(raw: str) -> tuple[str, str] | None:
    lines = raw.strip().splitlines()
    if not lines:
        return None
    subject = ""
    body_start = 0
    for i, line in enumerate(lines):
        if line.strip():
            subject = line.strip()
            body_start = i + 1
            break
    while body_start < len(lines) and not lines[body_start].strip():
        body_start += 1
    body = "\n".join(lines[body_start:]).strip()
    if not subject or not body:
        return None
    return subject, body
