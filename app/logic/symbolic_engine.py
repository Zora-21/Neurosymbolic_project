import json
from pathlib import Path

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

    def get_recommendation(self, rag_analysis: dict) -> dict:
            """
            Applica regole fisse basate sulla lista di condizioni identificata dal sistema RAG.
            La raccomandazione si basa sulla condizione con la probabilità PIÙ ALTA trovata.
            La logica è "il rischio maggiore vince".
            """
            conditions = rag_analysis.get("potential_conditions", [])
            
            if not conditions or not isinstance(conditions, list):
                print("⚠️ Analisi RAG non valida o vuota. Uso la risposta di default.")
                return self.kb['risposta_default']
    
            # Estrai tutte le probabilità in minuscolo
            probabilities = set(cond.get("probability", "").lower() for cond in conditions if cond.get("probability"))
    
            # --- REGOLE SIMBOLICHE DI SICUREZZA (ROBUSTE) ---
            # "Il rischio maggiore vince"
            if "alta" in probabilities:
                return self.kb['raccomandazioni']['cura_urgente']
            
            if "media" in probabilities:
                return self.kb['raccomandazioni']['contatta_medico']
            
            if "bassa" in probabilities:
                return self.kb['raccomandazioni']['cura_personale']
    
            # Fallback se la lista condizioni era presente ma vuota 
            # o non conteneva nessuna probabilità valida
            print(f"⚠️ Nessuna probabilità valida trovata in {probabilities}. Uso la risposta di default.")
            return self.kb['risposta_default']