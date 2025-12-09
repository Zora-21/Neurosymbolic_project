import json
from pathlib import Path
from typing import Dict, Any, Optional
from app.logger import get_triage_logger

# Logger per questo modulo
logger = get_triage_logger()

def load_knowledge_base() -> dict:
    """Carica la base di conoscenza dal file JSON."""
    # Assicurati che il percorso sia corretto rispetto a questo file
    kb_path = Path(__file__).parent.parent / "data/knowledge_base.json"
    with open(kb_path, 'r', encoding='utf-8') as f:
        return json.load(f)

class TriageEngine:
    def __init__(self):
        """Inizializza il motore caricando la base di conoscenza."""
        self.kb = load_knowledge_base()

    def _apply_safety_rules(self, extracted_data: dict) -> dict:
        """
        Applica regole deterministiche (hard-coded) sui parametri vitali.
        Se una regola scatta, restituisce la raccomandazione corrispondente.
        Altrimenti restituisce None.
        """
        if not extracted_data:
            return None

        # --- REGOLA 1: FEBBRE ALTA ---
        temp = extracted_data.get("temperature_celsius")
        if temp and isinstance(temp, (int, float)):
            if temp > 39.5:
                logger.warning(f"RULE MATCH: Temperatura {temp}°C -> URGENTE")
                return self.kb['raccomandazioni']['cura_urgente']

        # --- REGOLA 2: DOLORE INTENSO ---
        pain = extracted_data.get("pain_score")
        if pain and isinstance(pain, (int, float)):
            if pain >= 9:
                logger.warning(f"RULE MATCH: Dolore {pain}/10 -> URGENTE")
                return self.kb['raccomandazioni']['cura_urgente']
            if pain >= 7:
                 logger.warning(f"RULE MATCH: Dolore {pain}/10 -> CONTATTA MEDICO")
                 return self.kb['raccomandazioni']['contatta_medico']

        # --- REGOLA 3: IPERTENSIONE GRAVE ---
        sys = extracted_data.get("systolic")
        dia = extracted_data.get("diastolic")
        if sys and dia and isinstance(sys, (int, float)) and isinstance(dia, (int, float)):
            if sys > 180 or dia > 120:
                logger.warning(f"RULE MATCH: Pressione {sys}/{dia} -> URGENTE (Crisi Ipertensiva)")
                return self.kb['raccomandazioni']['cura_urgente']

        return None

    def get_recommendation(self, rag_analysis: dict, extracted_data: dict = None) -> dict:
        """
        Combina regole deterministiche (Simboliche) e analisi probabilistica (Neurale).
        Priorità: Regole di Sicurezza > Probabilità Alta > Probabilità Media > Probabilità Bassa.
        """
        
        # 1. CONTROLLO REGOLE SIMBOLICHE (Priorità Assoluta)
        safety_override = self._apply_safety_rules(extracted_data)
        if safety_override:
            return safety_override

        # 2. ANALISI PROBABILISTICA (RAG)
        conditions = rag_analysis.get("potential_conditions", [])
        
        if not conditions or not isinstance(conditions, list):
            logger.warning("Analisi RAG non valida o vuota. Uso la risposta di default.")
            return self.kb['risposta_default']

        # Normalizzazione probabilità (supporta IT e EN)
        # Mappa sinonimi -> livello normalizzato
        probability_mapping = {
            # Italiano
            "alta": "high", "alto": "high",
            "media": "medium", "medio": "medium",
            "bassa": "low", "basso": "low",
            # Inglese
            "high": "high",
            "medium": "medium", "moderate": "medium",
            "low": "low"
        }
        
        # Estrai tutte le probabilità normalizzate
        normalized_probs = set()
        for cond in conditions:
            raw_prob = cond.get("probability", "").lower().strip()
            normalized = probability_mapping.get(raw_prob, None)
            if normalized:
                normalized_probs.add(normalized)

        # "Il rischio maggiore vince"
        if "high" in normalized_probs:
            return self.kb['raccomandazioni']['cura_urgente']
        
        if "medium" in normalized_probs:
            return self.kb['raccomandazioni']['contatta_medico']
        
        if "low" in normalized_probs:
            return self.kb['raccomandazioni']['cura_personale']

        # Fallback
        logger.warning(f"Nessuna probabilità valida trovata in {normalized_probs}. Uso la risposta di default.")
        return self.kb['risposta_default']