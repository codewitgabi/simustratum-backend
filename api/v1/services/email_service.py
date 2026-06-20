from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType

from api.v1.utils.config import config
from api.v1.utils.logger import get_logger

logger = get_logger("email_service")

# Mirrors the neubrutalist palette in the web app's globals.css (@theme inline):
# cream/pale backgrounds, sienna as the primary action color, ink for borders/
# text, hard edges + offset box-shadows instead of soft drop shadows.
_CREAM = "#fbf4ea"
_PALE = "#f0e5d0"
_CAMEL = "#c19a6b"
_SIENNA = "#a0522d"
_INK = "#1a1109"
_MID = "#7a5c3a"


def _build_connection_config() -> ConnectionConfig:
    """Built lazily (not at import time) so importing this module doesn't require
    SMTP settings to already be configured — only actually sending an email does."""
    return ConnectionConfig(
        MAIL_USERNAME=config.MAIL_USERNAME or "",
        MAIL_PASSWORD=config.MAIL_PASSWORD or "",
        MAIL_FROM=config.MAIL_FROM,
        MAIL_FROM_NAME=config.MAIL_FROM_NAME,
        MAIL_PORT=config.MAIL_PORT,
        MAIL_SERVER=config.MAIL_SERVER or "",
        MAIL_STARTTLS=config.MAIL_STARTTLS,
        MAIL_SSL_TLS=config.MAIL_SSL_TLS,
        USE_CREDENTIALS=config.MAIL_USE_CREDENTIALS,
        VALIDATE_CERTS=config.MAIL_VALIDATE_CERTS,
    )


def _email_shell(preview_text: str, body_html: str) -> str:
    """Shared branded wrapper (header wordmark + footer) so every transactional
    email looks the same, regardless of which one fires. Hard 3px ink borders and
    an offset box-shadow on the card, matching the .neu-btn / .neu-input
    neubrutalism treatment used across the web app."""
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Simustratum</title>
</head>
<body style="margin:0; padding:0; background-color:{_PALE}; font-family:'Segoe UI', Helvetica, Arial, sans-serif;">
  <span style="display:none; max-height:0; overflow:hidden; opacity:0;">{preview_text}</span>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:{_PALE}; padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px; background-color:{_CREAM}; border:3px solid {_INK}; box-shadow:7px 7px 0 {_INK};">
          <tr>
            <td style="background-color:{_SIENNA}; padding:24px 32px; border-bottom:3px solid {_INK};">
              <span style="color:{_CREAM}; font-size:21px; font-weight:700; letter-spacing:0.3px; font-family:Georgia, 'Times New Roman', serif;">Simustratum</span>
            </td>
          </tr>
          <tr>
            <td style="padding:32px;">
              {body_html}
            </td>
          </tr>
          <tr>
            <td style="padding:18px 32px; background-color:{_PALE}; border-top:3px solid {_INK};">
              <p style="margin:0; font-size:12px; color:{_MID}; line-height:1.5;">
                You're receiving this email because it's tied to a Simustratum account.
                If this wasn't you, you can safely ignore it.
              </p>
              <p style="margin:8px 0 0; font-size:12px; color:{_MID}; font-weight:600;">&copy; Simustratum</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


async def send_password_reset_email(to_email: str, reset_link: str) -> None:
    if not config.MAIL_SERVER:
        logger.warning(
            "MAIL_SERVER is not configured — skipping password reset email send",
            extra={"to_email": to_email},
        )
        return

    body_html = f"""
    <h1 style="margin:0 0 16px; font-size:20px; color:{_INK}; font-family:Georgia, 'Times New Roman', serif;">Reset your password</h1>
    <p style="margin:0 0 24px; font-size:15px; color:{_INK}; line-height:1.6;">
      We received a request to reset the password for your Simustratum account.
      Click the button below to choose a new one.
    </p>
    <table role="presentation" cellpadding="0" cellspacing="0">
      <tr>
        <td style="background-color:{_SIENNA}; border:3px solid {_INK}; box-shadow:5px 5px 0 {_INK};">
          <a href="{reset_link}"
             style="display:inline-block; padding:12px 28px; font-size:15px; font-weight:700;
                    color:{_CREAM}; text-decoration:none;">
            Reset Password
          </a>
        </td>
      </tr>
    </table>
    <p style="margin:32px 0 0; font-size:13px; color:{_MID}; line-height:1.6;">
      This link expires in {config.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes. If you
      didn't request a password reset, no action is needed — your password will stay
      the same.
    </p>
    <p style="margin:20px 0 0; font-size:13px; color:{_MID}; line-height:1.6; word-break:break-all;">
      Or paste this link into your browser:<br />
      <a href="{reset_link}" style="color:{_SIENNA}; font-weight:600;">{reset_link}</a>
    </p>
    """

    message = MessageSchema(
        subject="Reset your Simustratum password",
        recipients=[to_email],
        body=_email_shell(preview_text="Reset your Simustratum password", body_html=body_html),
        subtype=MessageType.html,
    )
    await FastMail(_build_connection_config()).send_message(message)
