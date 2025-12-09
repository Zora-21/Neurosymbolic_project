"""
Modulo centralizzato per il logging strutturato.
Sostituisce i print() con un sistema di logging configurabile.
"""
import logging
import sys
from typing import Optional

# Formattazione colorata per il terminale
class ColoredFormatter(logging.Formatter):
    """Formatter con colori per distinguere i livelli di log."""
    
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record: logging.LogRecord) -> str:
        # Aggiungi emoji per leggibilità
        emoji_map = {
            'DEBUG': '🔍',
            'INFO': '✅',
            'WARNING': '⚠️',
            'ERROR': '❌',
            'CRITICAL': '🚨',
        }
        
        color = self.COLORS.get(record.levelname, '')
        emoji = emoji_map.get(record.levelname, '')
        
        # Formato: [LEVEL] emoji messaggio
        record.msg = f"{color}[{record.levelname}]{self.RESET} {emoji} {record.msg}"
        return super().format(record)


def get_logger(name: str, level: Optional[int] = None) -> logging.Logger:
    """
    Ritorna un logger configurato per il modulo specificato.
    
    Args:
        name: Nome del modulo (usa __name__ per il nome automatico)
        level: Livello di logging (default: INFO)
    
    Returns:
        Logger configurato
    """
    logger = logging.getLogger(name)
    
    # Evita handler duplicati
    if logger.handlers:
        return logger
    
    # Livello di default
    logger.setLevel(level or logging.INFO)
    
    # Handler per console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ColoredFormatter('%(message)s'))
    logger.addHandler(console_handler)
    
    # Previene propagazione a root logger
    logger.propagate = False
    
    return logger


# Logger pre-configurati per i moduli principali
def get_rag_logger() -> logging.Logger:
    """Logger per RAG Handler."""
    return get_logger('neurosymbolic.rag')

def get_agent_logger() -> logging.Logger:
    """Logger per gli Agenti."""
    return get_logger('neurosymbolic.agents')

def get_triage_logger() -> logging.Logger:
    """Logger per il Triage Engine."""
    return get_logger('neurosymbolic.triage')

def get_api_logger() -> logging.Logger:
    """Logger per le API."""
    return get_logger('neurosymbolic.api')
