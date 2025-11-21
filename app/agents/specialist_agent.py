import ollama
import json

from app.config import LLM_MODEL
from app.tools import medical_calculators

model=LLM_MODEL

class SpecialistAgent:
    def __init__(self, specialty: str, rag_handler, triage_engine):
        """
        Inizializza un agente specialista conversazionale con Riflessione.
        """
        self.specialty = specialty.lower()
        self.rag_handler = rag_handler
        self.triage_engine = triage_engine
        # Prompt per decidere l'azione (chiedere o analizzare)
        self.decide_action_prompt = f"""
        Sei un assistente medico specializzato in {self.specialty.upper()}. Dialoga con l'utente per approfondire i sintomi.
        Analizza la cronologia e decidi:
        1. Se servono dettagli SPECIFICI per {self.specialty}, fai UNA domanda mirata. JSON: {{"action": "ask_specialist_followup", "question": "..."}}
        2. Se hai abbastanza info per l'analisi RAG, avvia il triage. JSON: {{"action": "perform_triage", "summary": "Riassunto completo...", "extracted_data": {{"temperature_celsius": 39.5, "pain_score": 8, "systolic": 130, "diastolic": 90}} }}
        Se l'utente ha fornito dati numerici specifici (temperatura, punteggio dolore 0-10, pressione), inseriscili nell'oggetto "extracted_data". Altrimenti, lascia "extracted_data" come oggetto vuoto {{}}.
        Rispondi SOLO con il JSON richiesto.
        """
        # Prompt per il passo di Riflessione
        self.reflection_prompt_template = """
        Sei un supervisore medico esperto in {specialty_upper}. Revisiona l'analisi preliminare JSON ("initial_analysis") basata sui sintomi riassunti ("symptoms_summary").
        
        Il tuo compito è restituire un JSON raffinato. Le tue regole sono:
        1.  Valuta l'analisi iniziale: è corretta? È pertinente ai sintomi? (es. "Deformidade" per "tosse e febbre" è ERRATO).
        2.  Se l'analisi iniziale è buona, restituiscila.
        3.  Se l'analisi iniziale è errata, irrilevante o incompleta, DEVI correggerla o crearne una nuova basandoti TU sui sintomi riassunti.
        4.  Se crei nuove condizioni (es. 'Bronchite acuta', 'Pneumonia'), DEVI formattarle correttamente.

        Il formato di output DEVE essere ESCLUSIVAMENTE un oggetto JSON con la chiave "potential_conditions",
        che è una lista di oggetti. Ogni oggetto DEVE avere:
        - "condition": Nome della condizione (es. "Bronchite acuta").
        - "probability": Probabilità ("Alta", "Media", "Bassa").
        - "reasoning": Spiegazione (max 2 frasi) che collega i SINTOMI alla condizione.

        Sintomi Riepilogati: {symptoms_summary}
        Analisi Preliminare da Revisionare:
        ```json
        {initial_analysis_json}
        ```
        Fornisci il JSON raffinato:
        """

    def decide_next_action(self, chat_history: list) -> dict:
        """
        Decide se fare un'altra domanda specifica o avviare l'analisi finale.
        (Codice identico alla versione precedente)
        """
        messages = [{'role': 'system', 'content': self.decide_action_prompt}]
        messages.extend(chat_history[-6:]) # Considera una finestra di contesto

        try:
            response = ollama.chat(model='llama3:8b', messages=messages, format='json')
            decision = json.loads(response['message']['content'])

            action = decision.get("action")
            # Validazione più robusta
            if action == "ask_specialist_followup":
                 if not decision.get("question"):
                      print(f"⚠️ {self.specialty.upper()} Action 'ask' senza domanda. Tento il triage.")
                      summary_fallback = " ".join([m['content'] for m in chat_history if m['role'] == 'user'])
                      return {"action": "perform_triage", "summary": summary_fallback}
            elif action == "perform_triage":
                 if not decision.get("summary"):
                      print(f"⚠️ {self.specialty.upper()} Action 'triage' senza summary. Tento il triage con fallback.")
                      summary_fallback = " ".join([m['content'] for m in chat_history if m['role'] == 'user'])
                      decision["summary"] = summary_fallback # Correggi decisione
            else: # Azione non valida
                print(f"⚠️ {self.specialty.upper()} Agent ha restituito azione non valida: '{action}'. Tento il triage.")
                summary_fallback = " ".join([m['content'] for m in chat_history if m['role'] == 'user'])
                return {"action": "perform_triage", "summary": summary_fallback}

            print(f"🤖 {self.specialty.upper()} Agent Decision: {action}")
            return decision

        except Exception as e:
            print(f"❌ Errore decisione {self.specialty.upper()} Agent: {e}")
            summary_fallback = " ".join([m['content'] for m in chat_history if m['role'] == 'user'])
            return {"action": "perform_triage", "summary": summary_fallback}


    def _run_reflection(self, symptoms_summary: str, initial_analysis: dict) -> dict:
        """
        Esegue il passo di Riflessione sull'analisi RAG iniziale.
        *** MODIFICATO CON VALIDAZIONE ROBUSTA DELLO SCHEMA ***
        """
        print(f"🤔 Inizio passo di Riflessione ({self.specialty.upper()})...")
        
        reflection_system_prompt = self.reflection_prompt_template.format(
            specialty_upper=self.specialty.upper(),
            symptoms_summary=symptoms_summary,
            initial_analysis_json=json.dumps(initial_analysis, indent=2)
        )
        
        refined_analysis = initial_analysis # Default

        try:
            reflection_response = ollama.chat(
                model='llama3:8b',
                messages=[{'role': 'system', 'content': reflection_system_prompt}],
                options={'temperature': 0.0},
                format='json'
            )

            try:
                refined_analysis_json = json.loads(reflection_response['message']['content'])

                # --- VALIDAZIONE ROBUSTA (SOSTITUITA) ---
                if "potential_conditions" in refined_analysis_json and isinstance(refined_analysis_json.get("potential_conditions"), list):
                    
                    validated_conditions = []
                    is_valid_schema = True

                    # Itera su ogni item restituito dall'LLM
                    for item in refined_analysis_json["potential_conditions"]:
                        # Controlla se l'item è un DIZIONARIO e ha le chiavi MINIME richieste
                        if isinstance(item, dict) and "condition" in item and "probability" in item:
                            validated_conditions.append(item)
                        else:
                            # L'item è una stringa (es. 'Fibromialgia') o un dizionario malformato
                            print(f"⚠️ Riflessione ({self.specialty.upper()}) ha restituito un item non valido: '{item}'. Scartato.")
                            is_valid_schema = False
                    
                    if not is_valid_schema:
                         print(f"⚠️ Riflessione ({self.specialty.upper()}) ha restituito dati misti. Uso solo gli {len(validated_conditions)} item validati.")
                    else:
                         print(f"✨ Analisi RAG Raffinata ({self.specialty.upper()}) (Schema Valido): {refined_analysis_json}")

                    # Ricostruisci l'analisi solo con gli item validi
                    refined_analysis = refined_analysis_json
                    refined_analysis["potential_conditions"] = validated_conditions
                    
                    # Aggiungi le fonti originali (come prima)
                    if "sources_consulted" not in refined_analysis:
                        refined_analysis["sources_consulted"] = initial_analysis.get("sources_consulted", [])
                
                else:
                     print(f"⚠️ Riflessione ({self.specialty.upper()}) JSON non valido (manca 'potential_conditions' o non è una lista). Uso analisi iniziale.")
            
            except json.JSONDecodeError:
                print(f"❌ Errore parsing JSON riflessione ({self.specialty.upper()}). Uso analisi iniziale. Risposta LLM: {reflection_response['message']['content']}")

        except Exception as e:
            print(f"❌ Errore durante Riflessione ({self.specialty.upper()}): {e}. Uso analisi iniziale.")
            
        return refined_analysis


    def perform_analysis_and_triage(self, symptoms_summary: str, extracted_data: dict = None) -> dict:
        """
        Esegue l'analisi RAG, la Riflessione e la decisione di triage.
        """
        print(f"--- {self.specialty.upper()} AGENT: Esecuzione Analisi Finale per '{symptoms_summary}' ---")

        tool_results_md = ""
        tool_report_items = []
        if extracted_data:
            try:
                if "temperature_celsius" in extracted_data:
                    result = medical_calculators.classify_fever(extracted_data["temperature_celsius"])
                    tool_report_items.append(f"Analisi Temperatura: {result['interpretation']}")
                if "pain_score" in extracted_data:
                    result = medical_calculators.classify_pain_level(extracted_data["pain_score"])
                    tool_report_items.append(f"Analisi Dolore: {result['category']}")
                if "duration_value" in extracted_data and "duration_unit" in extracted_data:
                     result = medical_calculators.classify_symptom_duration(extracted_data["duration_value"], extracted_data["duration_unit"])
                     tool_report_items.append(f"Analisi Durata: {result['category']} (circa {result['total_days_approx']} giorni)")


            except Exception as e:
                print(f"⚠️ Errore durante l'esecuzione dei tool simbolici: {e}")
                tool_report_items.append("Errore nell'analisi dei dati numerici.")

        if tool_report_items:
            tool_results_md = "\n\n---\n### Analisi Dati Simbolici\n" + "\n".join(f"- {item}" for item in tool_report_items)

        # 1. Fase RAG (ottiene analisi iniziale)
        initial_rag_analysis = self.rag_handler.get_potential_conditions(symptoms_summary, self.specialty)
        print(f"🧠 {self.specialty.upper()} RAG Analysis Iniziale: {initial_rag_analysis}")

        # Controlla se RAG iniziale ha fallito
        if "error" in initial_rag_analysis or not isinstance(initial_rag_analysis.get("potential_conditions"), list):
            print(f"⚠️ {self.specialty.upper()} RAG iniziale fallito o formato non valido.")
            default_resp = self.triage_engine.kb['risposta_default'].copy()
            default_resp["specialist_consulted"] = self.specialty
            return {"type": "triage_result", "data": default_resp}
        
        # Se RAG iniziale non ha trovato condizioni, non serve riflessione
        if not initial_rag_analysis.get("potential_conditions"):
            print(f"ℹ️ {self.specialty.upper()} RAG iniziale non ha trovato condizioni. Salto riflessione.")
            final_analysis = initial_rag_analysis # Usa l'analisi vuota
        else:
            # 2. Fase di Riflessione
            final_analysis = self._run_reflection(symptoms_summary, initial_rag_analysis)

        # 3. Fase Simbolica (usa l'analisi finale, che sia quella iniziale o quella raffinata)
        recommendation = self.triage_engine.get_recommendation(final_analysis)
        print(f"🛡️ {self.specialty.upper()} Decisione Simbolica (post-riflessione): '{recommendation['livello']}'")

        # 4. Combina Risultati
        final_response_data = {
            "specialist_consulted": self.specialty,
            "livello": recommendation.get('livello', 'Info Insufficienti'),
            "messaggio": recommendation.get('messaggio', self.triage_engine.kb['risposta_default']['messaggio']),
            "referto": final_analysis.get("potential_conditions", []),
            "sources_consulted": final_analysis.get("sources_consulted", []),
            # --- RIGA DA AGGIUNGERE ---
            "tool_report": tool_results_md 
        }
        return {"type": "triage_result", "data": final_response_data}
