"""Email configuration checks. Kept free of app imports so Settings can use it without a circular import."""

CONSOLE_ALLOWED_ENVIRONMENTS = frozenset({"development", "dev", "test", "testing"})


def validate_sender_config(sender: str, environment: str, smtp_host: str) -> None:
    """Raise ValueError when the email configuration is unsafe. Used by Settings and get_email_sender."""
    sender = sender.strip().lower()
    env = environment.strip().lower()
    if sender == "console":
        if env not in CONSOLE_ALLOWED_ENVIRONMENTS:
            raise ValueError(
                "EMAIL_SENDER=console is only allowed when ENVIRONMENT is development or test (it logs OTPs and reset "
                f"links). ENVIRONMENT is '{env}': set EMAIL_SENDER=smtp with SMTP_HOST, SMTP_PORT and EMAIL_FROM."
            )
    elif sender == "smtp":
        if not smtp_host.strip():
            raise ValueError("EMAIL_SENDER=smtp requires SMTP_HOST (and normally SMTP_USERNAME/SMTP_PASSWORD)")
    else:
        raise ValueError("EMAIL_SENDER must be 'console' or 'smtp'")
