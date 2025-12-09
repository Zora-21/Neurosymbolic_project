import ollama
import json
import os
from typing import Dict, Any
from app.logger import get_agent_logger
from app.config import DEFAULT_LANGUAGE
from app.translations import ASSISTANT_EXTRACTION_PROMPTS

# Logger per questo modulo
logger = get_agent_logger()

class AssistantAgent:
    def __init__(self, data_dir: str = "patient_data", language: str = DEFAULT_LANGUAGE):
        self.data_dir = data_dir
        self.language = language
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        
        self._update_prompt()
    
    def set_language(self, language: str):
        """Aggiorna la lingua dell'assistente dinamicamente."""
        if language in ["en", "it"]:
            self.language = language
            self._update_prompt()
    
    def _update_prompt(self):
        """Ricarica il prompt nella lingua corrente."""
        self.extraction_prompt = ASSISTANT_EXTRACTION_PROMPTS.get(self.language, ASSISTANT_EXTRACTION_PROMPTS["en"])

    def _load_data(self, session_id: str) -> Dict[str, Any]:
        file_path = os.path.join(self.data_dir, f"{session_id}.json")
        if os.path.exists(file_path):
            try:
                with open(file_path, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {
            "symptoms": [],
            "duration": [],
            "negative_findings": [],
            "medical_history": [],
            "medications": [],
            "allergies": [],
            "vital_signs": {},
            "notes": ""
        }

    def _save_data(self, session_id: str, data: Dict[str, Any]):
        file_path = os.path.join(self.data_dir, f"{session_id}.json")
        with open(file_path, "w") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def _merge_data(self, current_data: Dict[str, Any], new_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Unisce i nuovi dati estratti con quelli esistenti in modo sicuro.
        """
        merged = current_data.copy()
        
        # Liste: Append unique
        for key in ["symptoms", "duration", "negative_findings", "medical_history", "medications", "allergies"]:
            if key in new_data and isinstance(new_data[key], list):
                for item in new_data[key]:
                    if item not in merged[key]:
                        merged[key].append(item)
        
        # Dizionari (Vital Signs): Update keys
        if "vital_signs" in new_data and isinstance(new_data["vital_signs"], dict):
            merged["vital_signs"].update(new_data["vital_signs"])
            
        # Stringhe (Notes): Append
        if "notes" in new_data and new_data["notes"]:
            if merged["notes"]:
                merged["notes"] += f"; {new_data['notes']}"
            else:
                merged["notes"] = new_data["notes"]
                
        return merged

    def update_patient_data(self, session_id: str, user_message: str, last_agent_message: str = None) -> Dict[str, Any]:
        """
        Analizza il messaggio e aggiorna il file JSON del paziente.
        Restituisce i dati aggiornati.
        """
        current_data = self._load_data(session_id)
        
        context_str = ""
        if last_agent_message:
            context_str = f"Context (Previous Agent Question): \"{last_agent_message}\""

        # Nota: Non passiamo più current_data al prompt per evitare confusione
        prompt = self.extraction_prompt.format(
            context=context_str,
            user_message=user_message
        )

        try:
            response = ollama.chat(
                model='llama3:8b',
                messages=[{'role': 'system', 'content': prompt}],
                format='json',
                options={'temperature': 0.0}
            )
            
            # Pulizia JSON prima del parsing
            raw_content = response['message']['content']
            clean_content = raw_content.strip()
            # Rimuovi eventuali markdown
            if clean_content.startswith("```"):
                clean_content = clean_content.split("```")[1]
                if clean_content.startswith("json"):
                    clean_content = clean_content[4:]
            clean_content = clean_content.strip()
            
            new_data_delta = json.loads(clean_content)
            
            # Merging sicuro in Python
            updated_data = self._merge_data(current_data, new_data_delta)
            
            # Salvataggio
            self._save_data(session_id, updated_data)
            logger.info(f"Assistant Agent: Updated Data (Merge) for session {session_id[:8]}")
            return updated_data

        except Exception as e:
            logger.error(f"Assistant Agent Error: {e}")
            return current_data
