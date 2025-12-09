import json
import os
from typing import Dict, Any
from filelock import FileLock
from app.logger import get_api_logger

# Logger per questo modulo
logger = get_api_logger()

class SessionManager:
    def __init__(self, sessions_dir: str = "sessions"):
        self.sessions_dir = sessions_dir
        if not os.path.exists(self.sessions_dir):
            os.makedirs(self.sessions_dir)

    def _get_file_path(self, session_id: str) -> str:
        return os.path.join(self.sessions_dir, f"{session_id}.json")
    
    def _get_lock_path(self, session_id: str) -> str:
        return os.path.join(self.sessions_dir, f"{session_id}.lock")

    def load_session(self, session_id: str) -> Dict[str, Any]:
        """
        Carica lo stato della sessione da file con file locking.
        Se non esiste, restituisce una struttura vuota di default.
        """
        file_path = self._get_file_path(session_id)
        lock_path = self._get_lock_path(session_id)
        
        with FileLock(lock_path, timeout=5):
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r") as f:
                        data = json.load(f)
                        # Backfill defaults for existing sessions
                        if "current_agent" not in data:
                            data["current_agent"] = "router"
                        if "asked_questions" not in data:
                            data["asked_questions"] = []
                        return data
                except Exception as e:
                    logger.warning(f" Errore caricamento sessione {session_id}: {e}")
        
        # Struttura Default
        return {
            "chat_history": [],
            "current_agent": "router",
            "last_summary": "",
            "asked_questions": [] 
        }

    def save_session(self, session_id: str, data: Dict[str, Any]):
        """
        Salva lo stato della sessione su file con file locking.
        """
        file_path = self._get_file_path(session_id)
        lock_path = self._get_lock_path(session_id)
        
        try:
            with FileLock(lock_path, timeout=5):
                with open(file_path, "w") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f" Errore salvataggio sessione {session_id}: {e}")
