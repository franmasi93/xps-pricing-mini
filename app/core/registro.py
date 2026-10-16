"""Logs estructurados para Cloud Run (F5-B5): una línea JSON por evento, con severity, que Cloud Logging entiende.

Nunca se registran cuerpos, encabezados (Authorization) ni la cadena de conexión: el log de acceso de uvicorn solo
trae método, ruta y estado. Se activa con --log-config app/core/log_config.json (Dockerfile).
"""
import json
import logging
from datetime import datetime, timezone


class FormatoJSON(logging.Formatter):
    def format(self, registro: logging.LogRecord) -> str:
        datos = {
            "severity": registro.levelname,
            "time": datetime.fromtimestamp(registro.created, timezone.utc).isoformat(),
            "logger": registro.name,
            "message": registro.getMessage(),
        }
        if registro.exc_info:
            datos["error"] = self.formatException(registro.exc_info).splitlines()[-1]  # solo la última línea
        return json.dumps(datos, ensure_ascii=False)
