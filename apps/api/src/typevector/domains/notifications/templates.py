"""TypeVector Arena — Transactional Notification Templates.

Renders sanitized text and HTML notification bodies.
User-supplied parameters are strictly escaped to prevent HTML injection attacks.
"""

import html


def render_registration_confirmed(
    user_display_name: str,
    event_title: str,
) -> tuple[str, str, str]:
    """Template for event registration confirmation."""
    safe_name = html.escape(user_display_name)
    safe_event = html.escape(event_title)

    subject = f"Registration Confirmed: {event_title}"
    text_body = (
        f"Hello {user_display_name},\n\n"
        f"Your registration for '{event_title}' has been confirmed.\n"
        f"Please check in at the tournament lobby before the check-in window closes.\n\n"
        f"— TypeVector Arena Tournament Team"
    )
    html_body = (
        f"<p>Hello <strong>{safe_name}</strong>,</p>"
        f"<p>Your registration for <strong>{safe_event}</strong> has been confirmed.</p>"
        f"<p>Please check in at the tournament lobby before the check-in window closes.</p>"
        f"<hr><p><small>TypeVector Arena Tournament Team</small></p>"
    )
    return subject, text_body, html_body


def render_round_starting(
    user_display_name: str,
    event_title: str,
    round_number: int,
    scheduled_time_str: str,
) -> tuple[str, str, str]:
    """Template for round start notification."""
    safe_name = html.escape(user_display_name)
    safe_event = html.escape(event_title)

    subject = f"Round {round_number} Starting Soon: {event_title}"
    text_body = (
        f"Hello {user_display_name},\n\n"
        f"Round {round_number} of '{event_title}' is scheduled to start at {scheduled_time_str}.\n"
        f"Please connect to the arena and prepare your station.\n\n"
        f"— TypeVector Arena Tournament Team"
    )
    html_body = (
        f"<p>Hello <strong>{safe_name}</strong>,</p>"
        f"<p>Round {round_number} of <strong>{safe_event}</strong> is scheduled to start at {scheduled_time_str}.</p>"
        f"<p>Please connect to the arena and prepare your station.</p>"
        f"<hr><p><small>TypeVector Arena Tournament Team</small></p>"
    )
    return subject, text_body, html_body


def render_export_ready(
    user_display_name: str,
    export_type: str,
    download_url: str,
    expires_at_str: str,
) -> tuple[str, str, str]:
    """Template for data export completion notification."""
    safe_name = html.escape(user_display_name)
    safe_type = html.escape(export_type)

    subject = f"Your Export is Ready: {export_type}"
    text_body = (
        f"Hello {user_display_name},\n\n"
        f"Your requested '{export_type}' export has finished processing.\n"
        f"Download URL: {download_url}\n"
        f"This file will expire and be automatically deleted on {expires_at_str}.\n\n"
        f"— TypeVector Arena Operations"
    )
    html_body = (
        f"<p>Hello <strong>{safe_name}</strong>,</p>"
        f"<p>Your requested <strong>{safe_type}</strong> export has finished processing.</p>"
        f'<p><a href="{download_url}">Click here to download your export</a></p>'
        f"<p><small>This file will expire and be automatically deleted on {expires_at_str}.</small></p>"
        f"<hr><p><small>TypeVector Arena Operations</small></p>"
    )
    return subject, text_body, html_body


def render_appeal_decision(
    user_display_name: str,
    event_title: str,
    decision_status: str,
    decision_reason: str,
) -> tuple[str, str, str]:
    """Template for integrity appeal resolution notification."""
    safe_name = html.escape(user_display_name)
    safe_event = html.escape(event_title)
    safe_decision = html.escape(decision_status)
    safe_reason = html.escape(decision_reason)

    subject = f"Appellate Decision Notice: {event_title}"
    text_body = (
        f"Hello {user_display_name},\n\n"
        f"An independent appellate decision has been issued regarding your submission in '{event_title}'.\n"
        f"Decision: {decision_status}\n"
        f"Reason: {decision_reason}\n\n"
        f"— TypeVector Arena Integrity Committee"
    )
    html_body = (
        f"<p>Hello <strong>{safe_name}</strong>,</p>"
        f"<p>An independent appellate decision has been issued regarding your submission in <strong>{safe_event}</strong>.</p>"
        f"<p>Decision: <strong>{safe_decision}</strong></p>"
        f"<p>Reason: {safe_reason}</p>"
        f"<hr><p><small>TypeVector Arena Integrity Committee</small></p>"
    )
    return subject, text_body, html_body
