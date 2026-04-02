import base64
import logging
import mimetypes
import os
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

# Sender email — set via GMAIL_SENDER env var or fallback to your address
SENDER = os.getenv("GMAIL_SENDER", "francisanthony0328@gmail.com")

BASE_DIR = os.path.dirname(__file__)
CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")


def _get_gmail_service():
    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"credentials.json not found at {CREDENTIALS_PATH}. "
                    "Download it from Google Cloud Console > APIs & Services > Credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as token_file:
            token_file.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def send_email(to: str, subject: str, body: str, attachment_path: str = None) -> bool:
    """
    Send an email via Gmail API, optionally with a file attachment.
    Returns True on success, False on failure.
    """
    try:
        service = _get_gmail_service()

        if attachment_path and os.path.exists(attachment_path):
            message = MIMEMultipart()
            message["to"] = to
            message["from"] = SENDER
            message["subject"] = subject
            message.attach(MIMEText(body, "plain"))

            content_type, _ = mimetypes.guess_type(attachment_path)
            if content_type is None:
                content_type = "application/octet-stream"
            main_type, sub_type = content_type.split("/", 1)

            with open(attachment_path, "rb") as f:
                attachment = MIMEBase(main_type, sub_type)
                attachment.set_payload(f.read())
            encoders.encode_base64(attachment)
            filename = os.path.basename(attachment_path)
            attachment.add_header("Content-Disposition", "attachment", filename=filename)
            message.attach(attachment)
        else:
            message = MIMEText(body, "plain")
            message["to"] = to
            message["from"] = SENDER
            message["subject"] = subject
            if attachment_path:
                logger.warning(f"Attachment not found: {attachment_path}, sending without it")

        encoded = base64.urlsafe_b64encode(message.as_bytes()).decode()
        result = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": encoded})
            .execute()
        )
        logger.info(f"Email sent to {to} | message id: {result.get('id')}")
        return True

    except HttpError as e:
        logger.error(f"Gmail API error sending to {to}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending to {to}: {e}")
        return False
