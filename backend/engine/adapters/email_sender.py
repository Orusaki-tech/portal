from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class EmailSender(ABC):
    @abstractmethod
    def send(self, to: str, subject: str, body: str) -> None: ...


class ConsoleEmailSender(EmailSender):
    def send(self, to: str, subject: str, body: str) -> None:
        logger.info("Email sent — to=%s subject=%s body=%s", to, subject, body)


class NullEmailSender(EmailSender):
    def send(self, to: str, subject: str, body: str) -> None:
        pass


try:
    import sendgrid
    from sendgrid.helpers.mail import Content, Mail

    class SendGridEmailSender(EmailSender):
        def __init__(self) -> None:
            api_key = os.getenv("SENDGRID_API_KEY")
            if not api_key:
                logger.warning("SENDGRID_API_KEY not set — falling back to ConsoleEmailSender")
                self._fallback = ConsoleEmailSender()
                self._client = None
            else:
                self._client = sendgrid.SendGridAPIClient(api_key=api_key)
                self._fallback = None

        def send(self, to: str, subject: str, body: str) -> None:
            if self._client is None:
                self._fallback.send(to, subject, body)
                return
            from_email = os.getenv("SENDGRID_FROM_EMAIL", "noreply@realitysync.com")
            message = Mail(
                from_email=from_email,
                to_emails=to,
                subject=subject,
                html_content=Content("text/plain", body),
            )
            try:
                self._client.send(message)
                logger.info("Email sent via SendGrid to=%s subject=%s", to, subject)
            except Exception as e:
                logger.error("SendGrid send failed to=%s: %s", to, e)

except ImportError:
    logger.info("sendgrid package not installed — using ConsoleEmailSender as fallback")
    SendGridEmailSender = None


def get_email_sender() -> EmailSender:
    env = os.getenv("ENV", "development")
    if env == "production" and SendGridEmailSender is not None:
        return SendGridEmailSender()
    return ConsoleEmailSender()
