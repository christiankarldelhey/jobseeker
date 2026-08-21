"""Email notifications via SMTP (works with Gmail app passwords or any SMTP provider).

Set JOBWATCH_DRY_RUN=1 to print emails to stdout instead of actually sending
them -- useful while testing config.yaml/registry.yaml changes without
burning email-provider credits.
"""

from __future__ import annotations

import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .adapters.base import Job


def _is_dry_run() -> bool:
    return os.environ.get("JOBWATCH_DRY_RUN", "").lower() in ("1", "true", "yes")


class EmailConfig:
    def __init__(self):
        self.host = os.environ["SMTP_HOST"]
        self.port = int(os.environ.get("SMTP_PORT", "587"))
        self.user = os.environ["SMTP_USER"]
        self.password = os.environ["SMTP_PASSWORD"]
        self.to_addr = os.environ.get("NOTIFY_EMAIL_TO", self.user)
        self.from_addr = os.environ.get("NOTIFY_EMAIL_FROM", self.user)


def _send(subject: str, html_body: str) -> None:
    if _is_dry_run():
        print(f"\n[DRY RUN] Email that would be sent:\nSubject: {subject}\n{html_body}\n")
        return

    cfg = EmailConfig()
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg.from_addr
    msg["To"] = cfg.to_addr
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(cfg.host, cfg.port) as server:
        server.starttls()
        server.login(cfg.user, cfg.password)
        server.sendmail(cfg.from_addr, [cfg.to_addr], msg.as_string())


def _humanize_age(posted_at: datetime | None) -> str:
    """Renders a relative "time ago" label, e.g. 'hace 2 horas', 'hace 3 meses'.
    Returns a fallback string when the ATS didn't provide a date at all."""
    if posted_at is None:
        return "fecha desconocida"

    now = datetime.now(timezone.utc)
    delta = now - posted_at
    seconds = delta.total_seconds()

    if seconds < 0:
        return "recién publicada"
    if seconds < 3600:
        minutes = int(seconds // 60)
        return "hace menos de 1 minuto" if minutes < 1 else f"hace {minutes} minuto{'s' if minutes != 1 else ''}"
    if seconds < 86400:
        hours = int(seconds // 3600)
        return f"hace {hours} hora{'s' if hours != 1 else ''}"
    days = int(seconds // 86400)
    if days < 30:
        return f"hace {days} día{'s' if days != 1 else ''}"
    if days < 365:
        months = days // 30
        return f"hace {months} mes{'es' if months != 1 else ''}"
    years = days // 365
    return f"hace {years} año{'s' if years != 1 else ''}"


def _job_html(job: Job, score: int) -> str:
    age = _humanize_age(job.posted_at)
    return (
        f"<li><b>{job.company}</b> — {job.title} "
        f"(score {score}) — {job.location or 'sin ubicación'} — <i>{age}</i><br>"
        f'<a href="{job.url}">{job.url}</a></li>'
    )


def send_batch(jobs_with_scores: list[tuple[Job, int]], alerts: list[str] | None = None) -> None:
    """Sends ONE email with every new immediate-score job found in this run,
    plus an operational-alerts section (e.g. a source that broke/started
    returning nothing) if any were raised. Does nothing if both are empty --
    no email gets sent when there's nothing new and nothing broken."""
    alerts = alerts or []
    if not jobs_with_scores and not alerts:
        return

    parts = []
    if alerts:
        alert_items = "".join(f"<li>{a}</li>" for a in alerts)
        parts.append(f"<h3 style='color:#c0392b'>⚠️ Alertas operativas</h3><ul>{alert_items}</ul>")
    if jobs_with_scores:
        job_items = "".join(_job_html(job, score) for job, score in jobs_with_scores)
        parts.append(f"<ul>{job_items}</ul>")
    body = "".join(parts)

    if jobs_with_scores and alerts:
        subject = f"[JobWatch] {len(jobs_with_scores)} oferta(s) nueva(s) + {len(alerts)} alerta(s)"
    elif jobs_with_scores:
        subject = f"[JobWatch] {len(jobs_with_scores)} oferta(s) nueva(s)"
    else:
        subject = f"[JobWatch] {len(alerts)} alerta(s) operativa(s)"

    _send(subject, body)


def send_digest(jobs_with_scores: list[tuple[Job, int]]) -> None:
    if not jobs_with_scores:
        return
    subject = f"[JobWatch] Digest diario — {len(jobs_with_scores)} ofertas"
    items = "".join(_job_html(job, score) for job, score in jobs_with_scores)
    body = f"<ul>{items}</ul>"
    _send(subject, body)


def send_alert(message: str) -> None:
    """For operational alerts, e.g. an ATS token that suddenly returns 0 jobs."""
    _send("[JobWatch] Alerta operativa", f"<p>{message}</p>")
