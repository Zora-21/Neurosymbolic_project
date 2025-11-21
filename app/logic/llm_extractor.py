# app/logic/llm_extractor.py (MODIFICATO)

import ollama
import json

def get_symptoms_query(user_input: str) -> str:
    """
    Usa Ollama per estrarre una stringa di ricerca pulita dai sintomi dell'utente.
    """
    system_prompt = """
    Sei un assistente che estrae i sintomi principali da un testo.
    Riassumi i sintomi in una stringa di testo concisa, separati da virgole,
    adatta per una ricerca in una base di conoscenza medica.
    Rispondi solo con la stringa di sintomi. Esempio: "febbre alta, tosse secca, mal di gola".
    """
    try:
        response = ollama.chat(
            model='llama3:8b',
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_input}
            ],
            options={'temperature': 0.0}
        )
        return response['message']['content'].strip()
    except Exception as e:
        print(f"❌ Errore nell'estrazione della query: {e}")
        return user_input # Fallback: usa l'input originale come query