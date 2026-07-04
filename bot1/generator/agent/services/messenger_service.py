"""Messenger Service-Bridge: Die Schnittstellen zur physischen Welt.

Koppelt LangBot (Multi-Messenger-Bridge), CowAgent (WhatsApp/WeChat),
und bot1 (eigene Bot-Generierung) als Kommunikations-Schicht.

Lokale Pfade:
  - n:\\allinall\\LangBot-master       (Discord, Slack, Telegram, WeChat)
  - n:\\allinall\\CowAgent-master      (WhatsApp, WeCom, DingTalk)
  - n:\\allinall\\bot1                  (Eigener Bot Generator)
"""
from __future__ import annotations

import logging
from .base_service import ServiceConfig, ServiceResult
from .http_service import HttpService

logger = logging.getLogger(__name__)


def create_langbot_config(repo_path: str = r"n:\allinall\LangBot-master") -> ServiceConfig:
    return ServiceConfig(
        name="langbot",
        display_name="LangBot (Multi-Messenger Gateway)",
        port=9000,
        health_endpoint="/health",
        start_command="python main.py",
        auto_start=False,
        scale_to_zero=False,  # Messenger-Bots müssen dauerhaft lauschen
        capabilities=[
            "discord", "slack", "telegram", "wechat",
            "messenger_gateway", "notification",
        ],
        tags=["messenger", "interface", "communication"],
        repo_path=repo_path,
    )


def create_cowagent_config(repo_path: str = r"n:\allinall\CowAgent-master") -> ServiceConfig:
    return ServiceConfig(
        name="cowagent",
        display_name="CowAgent (WhatsApp/WeCom Bridge)",
        port=9899,
        health_endpoint="/health",
        start_command="cow start",
        auto_start=False,
        scale_to_zero=False,
        capabilities=[
            "whatsapp", "wecom", "dingtalk",
            "messenger_gateway", "notification",
        ],
        tags=["messenger", "interface", "communication"],
        repo_path=repo_path,
    )


class MessengerService(HttpService):
    """Einheitliche Schnittstelle zu allen Messenger-Plattformen.

    Ermöglicht dem AI-OS:
      - Nachrichten an den Nutzer über WhatsApp/Discord/Telegram zu senden
      - Eingehende Nachrichten zu empfangen und als Tasks zu behandeln
      - Benachrichtigungen bei Fertigstellung von Langzeit-Tasks
    """

    def __init__(self, repo_path: str = r"n:\allinall\LangBot-master") -> None:
        config = create_langbot_config(repo_path)
        super().__init__(config)

    def send_message(self, platform: str, recipient: str, message: str,
                     *, attachments: list[str] | None = None) -> ServiceResult:
        """Sendet eine Nachricht über eine Messenger-Plattform.

        Args:
            platform: "whatsapp", "discord", "telegram", "slack", etc.
            recipient: Empfänger-ID oder Channel-Name
            message: Die Nachricht
            attachments: Optionale Dateipfade (Bilder, PDFs, APKs, etc.)
        """
        return self.execute("send", {
            "platform": platform,
            "recipient": recipient,
            "message": message,
            "attachments": attachments or [],
        })

    def notify_completion(self, task_name: str, result_summary: str,
                          *, platforms: list[str] | None = None) -> ServiceResult:
        """Benachrichtigt den Nutzer über die Fertigstellung eines Tasks."""
        return self.execute("notify", {
            "task_name": task_name,
            "result_summary": result_summary,
            "platforms": platforms or ["whatsapp"],
        })

    def get_pending_messages(self) -> ServiceResult:
        """Holt alle unbearbeiteten eingehenden Nachrichten."""
        return self._timed_execute("pending", self.get, "/api/messages/pending")
