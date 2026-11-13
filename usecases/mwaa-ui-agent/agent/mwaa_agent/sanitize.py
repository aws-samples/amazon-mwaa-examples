# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Structural redaction and bounded serialization for model and UI output."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

MAX_TOOL_OUTPUT_CHARS = 40_000
MAX_UI_TEXT_CHARS = 80_000

# Bare values after "password=" or "token:" that are not secrets.
_LITERALS = frozenset({"true", "false", "none", "null", "nil"})
# Annotations: "token: str", "token: Optional[str]", "password: SecretStr | None".
_ANNOTATION = re.compile(
    r"(?:str|int|bool|bytes|float|dict|list|Any|SecretStr|"
    r"(?:Optional|Union|Dict|List|dict|list|Mapping|Sequence)\[[\w\[\], |]*\]?)"
)
# Code that reads a secret instead of containing one. Kept to known forms, so a secret that merely looks
# like code ("Ab9x()", "Kx9[q2Lm]") is still redacted:
#   Variable.get("x"), conn.get_password(), os.environ["X"], os.getenv("X"), getpass(), get_secret("x")
#   and attribute references such as conn.password or self.api_token. A bare word is not exempt
#   ("password=hunter2" is the most common real secret), except the key's own name (password=password).
_SECRET_READ = re.compile(
    r"(?:"
    r"(?:Variable|BaseHook|Connection|os|self|conn|connection|hook|cfg|config|settings|secrets?)"
    r"(?:\.\w+)*(?:\.get\w*|\.getenv|\.environ)[(\[]"
    r"|(?:getpass|get_\w*(?:secret|password|token|credential|key)\w*)\("
    r"|(?:kwargs|params|context|conf|config|settings|secrets?|credentials?)\["
    r"|\w+\.xcom_pull\("
    r"|(?:self|cls|conn|connection|hook|creds|credentials|cfg|config|settings|secret|secrets|kwargs|params)"
    r"(?:\.[a-z_][a-z0-9_]*)+"
    r")$"
)


def _redact_assignment(match: re.Match[str]) -> str:
    """Redact the value of a credential assignment, unless it is code, a literal, or a type annotation.

    Leaving code alone lets authored DAGs that read secrets properly pass the upload check; a hardcoded
    value is still redacted (and refused). A bare value runs to the next separator and may contain quotes
    (``password=Ab"cD3``), so the exemptions look only at its leading code-like part.
    """
    prefix, separator, value = match.group(1), match.group(2), match.group(3)
    if value.startswith("[REDACTED"):
        return match.group(0)
    if value[0] not in "\"'":
        head = re.match(r"[^'\"]*", value).group(
            0
        )  # before any quote: 'Variable.get(' of 'Variable.get("db")'
        core = head.rstrip(
            ")"
        )  # "def f(token: str)" and "f(use_token=True)" end in the call's ')'
        whole = head == value
        if whole and core.lower() in _LITERALS:
            return match.group(0)
        if whole and separator == ":" and _ANNOTATION.fullmatch(core):
            return match.group(0)
        if _SECRET_READ.fullmatch(core) and (whole or core.endswith(("(", "["))):
            return match.group(0)
        # password=password: passing a variable named like the key, as in HttpHook(password=password).
        # Only as a keyword argument inside a call, not in free text, where "password=password" is a
        # (weak) real credential.
        # Look back only a short way: searching all text before every match made redaction quadratic.
        key = re.search(
            r"(?:\(|,\s*)(\w+)\s*=\s*$",
            match.string[max(0, match.start(3) - 200) : match.start(3)],
        )
        if whole and separator == "=" and key and core == key.group(1):
            return match.group(0)
    return f"{prefix}[REDACTED]"


_SENSITIVE_KEY = re.compile(
    r"(?i)(password|passwd|pwd|secret|credential|token|api[_-]?key|authorization|cookie|private[_-]?key|user[_-]?data)"
)
_SENSITIVE_NAME = re.compile(
    r"(?i)(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key)"
)
# Pagination cursors in AWS responses. Their names contain "token", but aws_api must return them so the
# model can page through results (FilterLogEvents often returns an empty page with a nextToken).
_PAGINATION_KEYS = frozenset(
    {
        "NextToken",
        "nextToken",
        "nextForwardToken",
        "nextBackwardToken",
        "NextContinuationToken",
        "ContinuationToken",
        "PaginationToken",
        "NextPageToken",
    }
)
_PATTERNS = (
    (re.compile(r"\b(AKIA|ASIA)[A-Z0-9]{16}\b"), "[REDACTED_AWS_KEY_ID]"),
    (
        re.compile(
            r"(?i)([?&](?:X-Amz-[A-Za-z-]+|token|signature|credential)=)[^&\s\"']+"
        ),
        r"\1[REDACTED]",
    ),
    (
        re.compile(
            r"(?i)(\"?(?:password|passwd|pwd|secret|secret_access_key|aws_secret_access_key|session_token|"
            r"aws_session_token|api[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token|db[_-]?pass|"
            r"passworddata)\"?\s*([:=])\s*)(\"[^\"]*\"|'[^']*'|[^\s,;}\]'\"][^\s,;}\]]*)"
        ),
        lambda m: _redact_assignment(m),
    ),
    (
        re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^\s:/@]+:)([^\s@/]+)(@)"),
        r"\1[REDACTED]\3",
    ),
    (re.compile(r"(?i)(bearer\s+)[a-z0-9._~+/=-]{8,}"), r"\1[REDACTED]"),
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
    # Names that END in a credential word: GITHUB_TOKEN=..., db_password: ..., AWS_SECRET_ACCESS_KEY=...
    # Names that only contain one (max_tokens, token_count) do not match; _redact_assignment keeps values
    # that are code or literals, not secrets.
    (
        re.compile(
            r"(?i)(\b[A-Za-z0-9_]*?(?:token|secret|password|passwd|pwd|api_?key|access_?key|secret_?key|"
            r"private_?key)\"?\s*([:=])\s*)(\"[^\"\n]*\"|'[^'\n]*'|[^\s,;}\]'\"][^\s,;}\]]*)"
        ),
        lambda m: _redact_assignment(m),
    ),
    # CLI flags: --db-password hunter2, --api-token=abc. Two dashes at a word boundary, so hyphenated prose
    # ("the refresh-token is", "non-secret config") is not a flag.
    (
        re.compile(
            r"(?i)((?<![\w-])--[A-Za-z0-9-]*(?:password|passwd|secret|token|api-key|access-key)(?:\s+|=))"
            r"(?!-)(\"[^\"\n]*\"|'[^'\n]*'|[^\s\"']+)"
        ),
        r"\1[REDACTED]",
    ),
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
        "[REDACTED_JWT]",
    ),
    (
        re.compile(
            r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|xox[abprs]-[A-Za-z0-9-]{10,}|"
            r"AIza[0-9A-Za-z_-]{35}|sk_live_[0-9A-Za-z]{20,})"
        ),
        "[REDACTED_TOKEN]",
    ),
    (
        re.compile(
            r"(?i)https://(?:hooks\.slack\.com/(?:services|workflows|triggers)|"
            r"[a-z0-9.-]+\.webhook\.office\.com|discord(?:app)?\.com/api/webhooks)/[^\s\"'<>]+"
        ),
        "[REDACTED_WEBHOOK_URL]",
    ),
)

# A bare AWS secret access key: exactly 40 base64 characters. Requiring upper case, lower case and a digit
# keeps lower-case hex such as 40-character git commit SHAs.
_BARE_SECRET_KEY = re.compile(r"(?<![A-Za-z0-9/+=])[A-Za-z0-9/+]{40}(?![A-Za-z0-9/+=])")


def _redact_bare_secret_key(match: re.Match[str]) -> str:
    value = match.group(0)
    if not (
        any(c.isupper() for c in value)
        and any(c.islower() for c in value)
        and any(c.isdigit() for c in value)
    ):
        return value
    # URL and file paths: a '/'-separated segment that reads as a word (GetCustomerOrders, region) is not
    # random key material.
    if "/" in value and any(
        _WORD_SEGMENT.fullmatch(segment) for segment in value.split("/")
    ):
        return value
    return "[REDACTED_SECRET_KEY]"


_WORD_SEGMENT = re.compile(r"[A-Z]?[a-z]{2,}(?:[A-Z][a-z]+)*\d*")


def _redact_url(value: str) -> str:
    """Remove signed/credential query values while preserving an otherwise useful URL."""
    if "?" not in value or not re.match(r"(?i)^https?://", value):
        return value
    try:
        parts = urlsplit(value)
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        if any(
            _SENSITIVE_KEY.search(key) or key.lower().startswith("x-amz-")
            for key, _ in pairs
        ):
            query = urlencode([(key, "[REDACTED]") for key, _ in pairs])
            return urlunsplit(
                (parts.scheme, parts.netloc, parts.path, query, parts.fragment)
            )
    except ValueError:
        pass
    return value


def redact(text: str) -> str:
    text = _redact_url(text)
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return _BARE_SECRET_KEY.sub(_redact_bare_secret_key, text)


def redact_values(value: Any) -> Any:
    """Apply value-pattern redaction to every string (keys included), without key-name rules.

    For approval cards: a mutation body is the user's own input, so a conf key such as secret_name or
    max_tokens must be shown, not blanked. The approval hook refuses any request this function would
    change, so the card always equals what runs.
    """
    if isinstance(value, dict):
        return {redact_values(k): redact_values(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_values(v) for v in value]
    if isinstance(value, str):
        return redact(value)
    return value


def scrub(value: Any, parent_key: str = "") -> Any:
    """Recursively redact sensitive fields before converting a response to text."""
    if parent_key in _PAGINATION_KEYS:
        # Opaque paging cursors, not credentials; the model needs them to read the next page.
        return redact(value) if isinstance(value, str) else value
    if _SENSITIVE_KEY.search(parent_key):
        return "[REDACTED]"
    if isinstance(value, dict):
        # AWS APIs often represent environment variables as {name: X, value: Y}.
        name = value.get("name", value.get("Name"))
        if isinstance(name, str) and _SENSITIVE_NAME.search(name):
            return {
                k: (
                    "[REDACTED]"
                    if str(k).lower() in ("value", "values")
                    else scrub(v, str(k))
                )
                for k, v in value.items()
            }
        return {str(k): scrub(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(v, parent_key) for v in value]
    if isinstance(value, str):
        return redact(value)
    return value


def truncate(text: str, limit: int = MAX_TOOL_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    head = limit * 2 // 5
    tail = limit - head
    omitted = len(text) - limit
    return f"{text[:head]}\n\n... [{omitted} characters omitted; narrow the query to see them] ...\n\n{text[-tail:]}"


def clean(text: str, limit: int = MAX_TOOL_OUTPUT_CHARS) -> str:
    return truncate(redact(text), limit)
