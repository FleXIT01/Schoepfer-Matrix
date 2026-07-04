"""Services-Paket: API-Bridges zu den 36+ externen Repositories und Tools.

Jeder Service kapselt die Kommunikation mit einem externen System
(OpenClaw, agenticSeek, MaxKB, ComfyUI, etc.) hinter einer einheitlichen
Schnittstelle. Der Orchestrator spricht nie direkt mit APIs — immer über Services.
"""
from .base_service import BaseService, ServiceStatus, ServiceConfig
from .service_registry import ServiceRegistry

__all__ = ["BaseService", "ServiceStatus", "ServiceConfig", "ServiceRegistry"]
