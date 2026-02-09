"""Email notification system for application updates."""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

from job_agent.config import AgentConfig
from job_agent.models import ApplicationRecord, ApplicationStatus

logger = logging.getLogger(__name__)


class NotificationService:
    """Sends email notifications for application events."""

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.notif = config.notifications

    def _send_email(self, subject: str, body_html: str) -> bool:
        """Send an HTML email."""
        if not self.notif.enabled:
            logger.debug("Notifications disabled, skipping email")
            return False

        if not all(
            [
                self.notif.smtp_host,
                self.notif.smtp_email,
                self.notif.smtp_password,
                self.notif.recipient_email,
            ]
        ):
            logger.warning("Email notification not configured properly")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = self.notif.smtp_email
            msg["To"] = self.notif.recipient_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body_html, "html"))

            with smtplib.SMTP(self.notif.smtp_host, self.notif.smtp_port) as server:
                server.starttls()
                server.login(self.notif.smtp_email, self.notif.smtp_password)
                server.send_message(msg)

            logger.info(f"Email sent: {subject}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    def notify_application_submitted(self, app: ApplicationRecord) -> bool:
        """Send notification when an application is submitted."""
        if not self.notif.notify_on_apply:
            return False

        subject = f"Application Submitted: {app.job.title} at {app.job.company}"
        body = f"""\
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px;">
            <h2 style="color: #2563eb;">Application Submitted</h2>
            <table style="border-collapse: collapse; width: 100%;">
                <tr>
                    <td style="padding: 8px; font-weight: bold;">Position:</td>
                    <td style="padding: 8px;">{app.job.title}</td>
                </tr>
                <tr style="background: #f3f4f6;">
                    <td style="padding: 8px; font-weight: bold;">Company:</td>
                    <td style="padding: 8px;">{app.job.company}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; font-weight: bold;">Location:</td>
                    <td style="padding: 8px;">{app.job.location or 'N/A'}</td>
                </tr>
                <tr style="background: #f3f4f6;">
                    <td style="padding: 8px; font-weight: bold;">Board:</td>
                    <td style="padding: 8px;">{app.job.board.value.title()}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; font-weight: bold;">Match Score:</td>
                    <td style="padding: 8px;">{app.match_score:.0%}</td>
                </tr>
                <tr style="background: #f3f4f6;">
                    <td style="padding: 8px; font-weight: bold;">Applied At:</td>
                    <td style="padding: 8px;">{app.applied_at or datetime.utcnow()}</td>
                </tr>
            </table>
            <p><a href="{app.job.url}" style="color: #2563eb;">View Job Listing</a></p>
        </body>
        </html>
        """
        return self._send_email(subject, body)

    def notify_error(self, app: ApplicationRecord, error: str) -> bool:
        """Send notification when an application fails."""
        if not self.notif.notify_on_error:
            return False

        subject = f"Application Failed: {app.job.title} at {app.job.company}"
        body = f"""\
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px;">
            <h2 style="color: #dc2626;">Application Failed</h2>
            <p><strong>Position:</strong> {app.job.title}</p>
            <p><strong>Company:</strong> {app.job.company}</p>
            <p><strong>Board:</strong> {app.job.board.value.title()}</p>
            <p><strong>Error:</strong></p>
            <pre style="background: #f3f4f6; padding: 12px; border-radius: 4px;">{error}</pre>
            <p><a href="{app.job.url}" style="color: #2563eb;">View Job Listing</a></p>
        </body>
        </html>
        """
        return self._send_email(subject, body)

    def send_daily_summary(self, stats: dict, recent_apps: list[dict]) -> bool:
        """Send daily summary email."""
        if not self.notif.daily_summary:
            return False

        subject = f"Job Agent Daily Summary - {datetime.utcnow().strftime('%Y-%m-%d')}"

        rows = ""
        for app in recent_apps[:20]:
            rows += f"""\
            <tr>
                <td style="padding: 6px; border-bottom: 1px solid #e5e7eb;">{app.get('title', 'N/A')}</td>
                <td style="padding: 6px; border-bottom: 1px solid #e5e7eb;">{app.get('company', 'N/A')}</td>
                <td style="padding: 6px; border-bottom: 1px solid #e5e7eb;">{app.get('status', 'N/A')}</td>
                <td style="padding: 6px; border-bottom: 1px solid #e5e7eb;">{app.get('board', 'N/A')}</td>
            </tr>
            """

        status_breakdown = ""
        for status, count in stats.get("by_status", {}).items():
            status_breakdown += f"<li><strong>{status}:</strong> {count}</li>"

        body = f"""\
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 700px;">
            <h2 style="color: #2563eb;">Daily Summary</h2>

            <h3>Statistics</h3>
            <ul>
                <li><strong>Total applications:</strong> {stats.get('total', 0)}</li>
                <li><strong>Applied today:</strong> {stats.get('applied_today', 0)}</li>
                {status_breakdown}
            </ul>

            <h3>Recent Applications</h3>
            <table style="border-collapse: collapse; width: 100%;">
                <thead>
                    <tr style="background: #2563eb; color: white;">
                        <th style="padding: 8px; text-align: left;">Title</th>
                        <th style="padding: 8px; text-align: left;">Company</th>
                        <th style="padding: 8px; text-align: left;">Status</th>
                        <th style="padding: 8px; text-align: left;">Board</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </body>
        </html>
        """
        return self._send_email(subject, body)
