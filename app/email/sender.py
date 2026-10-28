"""Email delivery abstraction.

``ConsoleEmailSender`` writes the message to the log and exists only for local development and tests;
``get_email_sender`` refuses to build it in any other environment. ``SmtpEmailSender`` delivers over SMTP.
"""
import asyncio
import logging
import smtplib
import ssl
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage

from app.core.config import settings
from app.email.validation import validate_sender_config

logger = logging.getLogger("app.email.sender")


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    body: str


class EmailSender(ABC):
    @abstractmethod
    async def send(self, message: EmailMessage) -> None:
        """Deliver the message or raise. Must not swallow failures: the worker retries on exceptions."""


class ConsoleEmailSender(EmailSender):
    """Development/test only: logs the whole message (including any OTP / reset link) instead of sending it."""

    async def send(self, message: EmailMessage) -> None:
        logger.info("[DEV EMAIL] to=%s subject=%s\n%s", message.to, message.subject, message.body)


class SmtpEmailSender(EmailSender):
    def __init__(self) -> None:
        self._host = settings.SMTP_HOST
        self._port = settings.SMTP_PORT
        self._username = settings.SMTP_USERNAME
        self._password = settings.SMTP_PASSWORD.get_secret_value() if settings.SMTP_PASSWORD else None
        self._use_ssl = settings.SMTP_USE_SSL
        self._starttls = settings.SMTP_STARTTLS
        self._timeout = settings.SMTP_TIMEOUT_SECONDS
        self._from = settings.EMAIL_FROM

    def _send_sync(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"] = self._from
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.body)
        context = ssl.create_default_context()
        if self._use_ssl:
            smtp = smtplib.SMTP_SSL(self._host, self._port, timeout=self._timeout, context=context)
        else:
            smtp = smtplib.SMTP(self._host, self._port, timeout=self._timeout)
        with smtp:
            if self._starttls and not self._use_ssl:
                smtp.starttls(context=context)
            if self._username:
                smtp.login(self._username, self._password or "")
            smtp.send_message(mime)

    async def send(self, message: EmailMessage) -> None:
        await asyncio.to_thread(self._send_sync, message)


def get_email_sender() -> EmailSender:
    validate_sender_config(settings.EMAIL_SENDER, settings.ENVIRONMENT, settings.SMTP_HOST)
    if settings.EMAIL_SENDER.strip().lower() == "smtp":
        return SmtpEmailSender()
    return ConsoleEmailSender()
