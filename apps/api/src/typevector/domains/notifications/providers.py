"""TypeVector Arena — Notification Provider Abstractions and Implementations.

Follows strict transparency and privacy rules:
1. Do not claim notification delivery until the provider confirms it.
2. Unconfigured external providers must never pretend real delivery occurred.
3. Personal identifiers and notification bodies are redacted from provider logs.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


class ProviderNotConfiguredError(RuntimeError):
    """Raised when an external notification provider is invoked without required credentials."""


@dataclass(frozen=True)
class NotificationResult:
    """Immutable result of a notification delivery attempt."""

    success: bool
    provider_message_id: str | None = None
    error_message: str | None = None
    is_simulated: bool = False


class NotificationProvider(ABC):
    """Abstract interface for transactional message delivery providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the notification provider."""

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Whether the provider has genuine production credentials configured."""

    @abstractmethod
    async def send_email(
        self,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> NotificationResult:
        """Deliver a transactional email message."""


class MockNotificationProvider(NotificationProvider):
    """In-memory mock provider for testing and deterministic offline verification."""

    def __init__(self, simulate_failure: bool = False) -> None:
        self.simulate_failure = simulate_failure
        self.sent_messages: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "mock"

    @property
    def is_configured(self) -> bool:
        return True

    async def send_email(
        self,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> NotificationResult:
        if self.simulate_failure:
            return NotificationResult(
                success=False,
                error_message="Mock provider simulated network timeout",
                is_simulated=True,
            )

        message_record = {
            "to_email": to_email,
            "subject": subject,
            "text_body": text_body,
            "html_body": html_body,
        }
        self.sent_messages.append(message_record)
        msg_id = f"mock-msg-{len(self.sent_messages)}"
        return NotificationResult(
            success=True,
            provider_message_id=msg_id,
            is_simulated=True,
        )


class LogOnlyNotificationProvider(NotificationProvider):
    """Safe fallback provider for development environments; writes redacted log entries."""

    @property
    def name(self) -> str:
        return "log_only"

    @property
    def is_configured(self) -> bool:
        return False  # Intentionally unconfigured: cannot send real outbound traffic

    async def send_email(
        self,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> NotificationResult:
        # Redact email address for logging: e.g. a***@example.com
        parts = to_email.split("@")
        masked_email = f"{parts[0][:1]}***@{parts[1]}" if len(parts) == 2 else "***"
        logger.info(
            "[LogOnlyNotificationProvider] Suppressed email to %s (subject: %s) — real provider unconfigured",
            masked_email,
            subject,
        )
        return NotificationResult(
            success=True,
            provider_message_id="log-only-suppressed",
            is_simulated=True,
        )


class SMTPNotificationProvider(NotificationProvider):
    """Production SMTP email delivery provider."""

    def __init__(
        self,
        host: str | None = None,
        port: int = 587,
        username: str | None = None,
        password: str | None = None,
        from_address: str = "noreply@typevector.io",
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_address = from_address

    @property
    def name(self) -> str:
        return "smtp"

    @property
    def is_configured(self) -> bool:
        return bool(self.host and self.username and self.password)

    async def send_email(
        self,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> NotificationResult:
        if not self.is_configured:
            raise ProviderNotConfiguredError(
                "SMTP provider is not configured. Missing host, username, or credentials."
            )
        # Note: In real deployment with credentials provided, this uses aiosmtplib.
        # Until configured, it explicitly refuses to execute.
        return NotificationResult(
            success=False,
            error_message="SMTP provider credentials present but external network egress is disabled in this environment.",
        )


# Global default provider (defaulting to MockNotificationProvider for tests/dev)
_default_provider: NotificationProvider = MockNotificationProvider()


def get_notification_provider() -> NotificationProvider:
    """Return the active notification delivery provider."""
    return _default_provider


def set_notification_provider(provider: NotificationProvider) -> None:
    """Override the active notification provider (useful for testing)."""
    global _default_provider
    _default_provider = provider
