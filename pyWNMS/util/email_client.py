"""Simple SMTP email client.

Ports the Java ``EmailClient`` — uses Python's ``smtplib`` instead of
raw socket I/O.
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText
from typing import List

logger = logging.getLogger(__name__)


class EmailClient:
    """Send plain-text email notifications via SMTP.

    :param server: SMTP server hostname.
    :param sender: Sender email address (``From:``).
    :param recipients: List of recipient email addresses.
    :param port: SMTP server port (default 25).
    """

    def __init__(
        self,
        server: str = "",
        sender: str = "",
        recipients: List[str] | None = None,
        port: int = 25,
    ) -> None:
        self.server = server
        self.sender = sender
        self.recipients: List[str] = recipients or []
        self.port = port

    def send(self, subject: str, message: str) -> None:
        """Send an email.

        :param subject: Email subject line.
        :param message: Email body text.
        :raises ValueError: If server or recipients are not configured.
        :raises smtplib.SMTPException: On SMTP errors.
        """
        if not self.server:
            raise ValueError("SMTP server not configured")
        if not self.recipients:
            raise ValueError("No recipients configured")

        msg = MIMEText(message, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.recipients)

        with smtplib.SMTP(self.server, self.port, timeout=10) as smtp:
            smtp.sendmail(self.sender, self.recipients, msg.as_string())

        logger.info("Email sent: '%s' to %s", subject, self.recipients)

    # ---- Serialization --------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "server": self.server,
            "sender": self.sender,
            "recipients": self.recipients,
            "port": self.port,
        }

    @classmethod
    def from_dict(cls, data: dict) -> EmailClient:
        return cls(
            server=data.get("server", ""),
            sender=data.get("sender", ""),
            recipients=data.get("recipients", []),
            port=data.get("port", 25),
        )
