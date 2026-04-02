# Outreach — Internship Email Automation

Automated cold email pipeline for internship outreach. Researches security companies, finds contacts, writes personalized emails with Claude, and sends via Gmail API — running on a schedule via GitHub Actions or locally.

---

## How It Works

```
target_companies.json
        │
        ▼
researcher.py      →  finds homepage, recent news, open roles (DuckDuckGo + scraping)
        │
contact_finder.py  →  finds named contact or team inbox (DDG + email pattern inference)
        │
email_writer.py    →  writes 150-200 word personalized email (Anthropic API + humanizer rules)
        │
resume_tailor.py   →  optionally tailors resume DOCX per company (Anthropic API)
        │
gmail_sender.py    →  sends via Gmail API with resume PDF attached
        │
tracker.py         →  logs every send to outreach_tracker.json (no duplicates)
```

---

## Quick Start (Local)

### 1. Clone and install

```bash
git clone https://github.com/franciskonikkara/Outreach.git
cd Outreach
pip install -r requirements.txt
```

### 2. Set up environment

```bash
cp .env.example .env
# Fill in: ANTHROPIC_API_KEY, GMAIL_SENDER, RESUME_PDF_PATH
```

### 3. Set up Gmail OAuth

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create a project
2. Enable the **Gmail API**
3. Create **OAuth 2.0 credentials** (Desktop App type)
4. Download `credentials.json` and place it in this folder
5. Run once to authorize: `python main.py --run-now`
   - A browser opens, sign in, and `token.json` is created automatically
   - All future runs (local and GitHub Actions) use this token

### 4. Run it

```bash
# Run immediately — sends up to 10 emails
python main.py --run-now

# Start local scheduler — runs at 8am Mon-Fri automatically
python main.py

# Manual batch send with hand-crafted emails
python send_batch.py

# Preview without sending
python send_batch.py --dry-run

# View outreach history
python tracker.py
```

---

## GitHub Actions Setup (Runs Every Weekday at 8am ET)

### Step 1 — Encode your secrets

After running locally once (to generate `token.json`), encode your secrets:

**Mac/Linux:**
```bash
base64 -i token.json | pbcopy
base64 -i resume/Francis_Konikkara_Resume.pdf | pbcopy
```

**Windows PowerShell:**
```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("token.json")) | Set-Clipboard
[Convert]::ToBase64String([IO.File]::ReadAllBytes("resume\Francis_Konikkara_Resume.pdf")) | Set-Clipboard
```

### Step 2 — Add GitHub Secrets

Go to: **Repo → Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key (`sk-ant-...`) |
| `GMAIL_TOKEN_B64` | Base64-encoded contents of `token.json` |
| `RESUME_PDF_B64` | Base64-encoded resume PDF |
| `GMAIL_SENDER` | `francisanthony0328@gmail.com` |

### Step 3 — Push and test

```bash
git add .
git commit -m "initial setup"
git push
```

Go to **Actions tab → Internship Outreach → Run workflow** to trigger a test run.

After each successful run, `outreach_tracker.json` is automatically committed back so the next run skips already-contacted companies.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | required | Anthropic API key |
| `GMAIL_SENDER` | `francisanthony0328@gmail.com` | Sender Gmail address |
| `RESUME_PDF_PATH` | `resume/Francis_Konikkara_Resume.pdf` | Resume PDF to attach |
| `RESUME_DOCX_PATH` | `resume/Francis_Konikkara_Resume.docx` | Base resume for per-company tailoring |
| `RESUME_OUTPUT_DIR` | `resume_outputs/` | Where tailored resumes are saved |
| `EMAILS_PER_RUN` | `10` | How many emails to send per run |

---

## File Structure

```
Outreach/
├── .github/
│   └── workflows/
│       └── outreach.yml        # GitHub Actions — runs Mon-Fri 8am ET
├── main.py                     # Orchestrator + APScheduler
├── researcher.py               # Company research (DuckDuckGo + scraping)
├── contact_finder.py           # Contact discovery (DDG + email inference)
├── email_writer.py             # Email generation (Anthropic API)
├── resume_tailor.py            # Resume tailoring per company (Anthropic API)
├── gmail_sender.py             # Gmail API sender
├── tracker.py                  # Outreach log
├── send_batch.py               # Manual batch sender for hand-crafted emails
├── target_companies.json       # ~130 target companies across categories
├── outreach_tracker.json       # Auto-updated — tracks every send
├── requirements.txt
├── .env.example                # Copy to .env and fill in values
└── .gitignore
```

---

## Customizing Targets

Edit `target_companies.json` to add or remove companies by category. The pipeline randomly picks `EMAILS_PER_RUN` companies that have not been contacted yet each run.

## Viewing History

```bash
python tracker.py
```

Prints a table of every email sent with date, company, and contact email.

---

## Important Notes

- **Defense companies** (Raytheon, Lockheed, Northrop, etc.) are excluded — they require US citizenship/security clearance and are not eligible for F-1 CPT
- `outreach_tracker.json` is committed back to the repo after each GitHub Actions run to persist state between runs
- `token.json` and `credentials.json` are gitignored — never commit them
- The Gmail OAuth token refreshes automatically as long as `token.json` has a valid refresh token
