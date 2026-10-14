"""
Sinfonia — Self Healer

Diagnostica gli errori dei provider e suggerisce azioni di recupero.
"""

from __future__ import annotations

from enum import Enum

import structlog

log = structlog.get_logger()


class ErrorType(str, Enum):
    RATE_LIMIT = "rate_limit"
    AUTH_ERROR = "auth_error"
    MODEL_NOT_FOUND = "model_not_found"
    SERVER_ERROR = "server_error"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


class SelfHealer:
    """Diagnostica gli errori e suggerisce azioni di recupero."""

    @staticmethod
    def diagnose(status_code: int, error_body: str) -> ErrorType:
        if status_code == 429:
            return ErrorType.RATE_LIMIT
        if status_code in (401, 403):
            return ErrorType.AUTH_ERROR
        if status_code == 404:
            if "model" in error_body.lower():
                return ErrorType.MODEL_NOT_FOUND
            return ErrorType.UNKNOWN
        if 500 <= status_code < 600:
            return ErrorType.SERVER_ERROR
        if status_code == 0:
            return ErrorType.NETWORK_ERROR
        return ErrorType.UNKNOWN

    @staticmethod
    def suggest_action(error_type: ErrorType) -> str:
        actions = {
            ErrorType.RATE_LIMIT: "Attendere il reset della quota o passare al provider successivo.",
            ErrorType.AUTH_ERROR: "Verificare la chiave API nel file .env.",
            ErrorType.MODEL_NOT_FOUND: "Aggiornare il nome del modello in providers.yaml.",
            ErrorType.SERVER_ERROR: "Ritentare dopo un breve intervallo.",
            ErrorType.NETWORK_ERROR: "Verificare la connessione di rete.",
            ErrorType.UNKNOWN: "Analizzare i log per maggiori dettagli.",
        }
        return actions.get(error_type, "Azione sconosciuta.")

    async def heal(self, provider_id: str, status_code: int, error_body: str) -> dict:
        error_type = self.diagnose(status_code, error_body)
        action = self.suggest_action(error_type)

        log.warning(
            "self_healer.diagnosis",
            provider=provider_id,
            error_type=error_type.value,
            action=action,
        )

        return {
            "provider_id": provider_id,
            "error_type": error_type.value,
            "suggested_action": action,
            "should_retry": error_type in (
                ErrorType.RATE_LIMIT,
                ErrorType.SERVER_ERROR,
                ErrorType.NETWORK_ERROR,
            ),
            "should_update_config": error_type == ErrorType.MODEL_NOT_FOUND,
        }
