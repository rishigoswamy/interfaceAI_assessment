"""
src/guardrails/redaction.py
PII and Secrets Sanitizer. Ensures raw sensitive data is never persisted in artifacts or logs.
"""

import re
from typing import Any, Dict, List, Union

# Regex patterns for common sensitive financial data
SSN_PATTERN = re.compile(r'\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b')
PAN_PATTERN = re.compile(r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})\b')
TOKEN_PATTERN = re.compile(r'(?i)(?:bearer\s+|token[\s:=]+|secret[\s:=]+|password[\s:=]+)([A-Za-z0-9_\-\.]{8,})')


class DataRedactor:
    """Sanitizes text and structured payloads to scrub credentials and PII."""

    @staticmethod
    def redact_text(text: str) -> str:
        if not isinstance(text, str):
            return text

        # Redact SSN
        text = SSN_PATTERN.sub("[REDACTED_SSN]", text)
        # Redact Payment Card PAN
        text = PAN_PATTERN.sub("[REDACTED_PAN]", text)
        # Redact generic bearer / auth tokens
        text = TOKEN_PATTERN.sub(r"\1 [REDACTED_TOKEN]", text)
        return text

    @classmethod
    def redact_data(cls, data: Any) -> Any:
        """Recursively traverses dictionaries, lists, and primitives to sanitize values."""
        if isinstance(data, str):
            return cls.redact_text(data)
        elif isinstance(data, dict):
            sanitized = {}
            for k, v in data.items():
                lower_k = k.lower()
                if any(secret_key in lower_k for secret_key in ["password", "secret", "token", "ssn", "pin", "auth"]):
                    sanitized[k] = "[REDACTED_SECRET]"
                else:
                    sanitized[k] = cls.redact_data(v)
            return sanitized
        elif isinstance(data, list):
            return [cls.redact_data(item) for item in data]
        return data
