import ollama
import json
from typing import Dict, Any, List, Optional

from app.config import LLM_MODEL, DEFAULT_LANGUAGE
from app.tools import medical_calculators
from app.models import MedicalAnalysis
from app.logger import get_agent_logger
from app.translations import SPECIALIST_DECIDE_PROMPTS, get_translation

# Logger per questo modulo
logger = get_agent_logger()

model = LLM_MODEL

class SpecialistAgent:
    def __init__(self, specialty: str, rag_handler, triage_engine, language: str = DEFAULT_LANGUAGE):
        """
        Inizializza un agente specialista conversazionale con Riflessione.
        """
        self.specialty = specialty.lower()
        self.rag_handler = rag_handler
        self.triage_engine = triage_engine
        self.language = language
        
        # Prompt to decide action (ask or analyze) - loaded from translations
        self._update_prompt()
        
    def set_language(self, language: str):
        """Aggiorna la lingua dello specialista dinamicamente."""
        if language in ["en", "it"]:
            self.language = language
            self._update_prompt()
    
    def _update_prompt(self):
        """Ricarica il prompt nella lingua corrente."""
        base_prompt = SPECIALIST_DECIDE_PROMPTS.get(self.language, SPECIALIST_DECIDE_PROMPTS["en"])
        self.decide_action_prompt = base_prompt.format(specialty=self.specialty.upper())
        
        # Prompt for Reflection step
        self.reflection_prompt_template = """
        You are an expert medical supervisor in {specialty_upper}. Review the preliminary JSON analysis ("initial_analysis") based on summarized symptoms ("symptoms_summary").
        
        Your task is to return a refined JSON. Your rules are:
        1. Evaluate the initial analysis: is it correct? Is it relevant to the symptoms?
        2. If the initial analysis is good, return it (adding treatment if missing).
        3. If the initial analysis is incorrect, irrelevant, or incomplete (or EMPTY), YOU MUST correct it or create a new one.
        4. CRITICAL: If "potential_conditions" is empty, USE YOUR GENERAL MEDICAL KNOWLEDGE to formulate at least 3 plausible hypotheses based on symptoms, marking them as "Low" or "Medium" probability. NEVER RETURN AN EMPTY LIST.
        
        IMPORTANT NOTE ON LANGUAGE:
        - The retrieved medical context (RAG) might be in SPANISH or ENGLISH.
        - YOU MUST analyze it, translate mentally, and respond EXCLUSIVELY IN ENGLISH.
        - If the context is hard to interpret, prioritize SYMPTOMS and use your general knowledge.

        The output format MUST be EXCLUSIVELY a JSON object with the key "potential_conditions",
        which is a list of objects. Each object MUST have:
        - "condition": Condition name (e.g., "Acute Bronchitis").
        - "probability": Probability ("High", "Medium", "Low").
        - "reasoning": Explanation (max 2 sentences).
        - "treatment": Suggested therapy (medications, lifestyle changes, or specialist referral).

        Summarized Symptoms: {symptoms_summary}
        Preliminary Analysis:
        ```json
        {initial_analysis_json}
        ```
        Refined JSON:
        """

    def decide_next_action(self, chat_history: list, patient_data: dict = None, asked_questions: list = None) -> dict:
        """
        Decide se fare un'altra domanda specifica o avviare l'analisi finale.
        """
        # Costruiamo il contesto dei dati paziente
        patient_context = ""
        if patient_data:
            patient_context = f"\nDATI PAZIENTE CONOSCIUTI:\n{json.dumps(patient_data, indent=2, ensure_ascii=False)}\n"
            patient_context += "NOTA: NON chiedere informazioni già presenti qui sopra (es. se c'è già la temperatura, non chiederla).\n"

        # Costruiamo il contesto delle domande già fatte
        asked_context = ""
        if asked_questions:
            asked_context = f"\nDOMANDE GIÀ FATTE (VIETATO RIPETERE):\n" + "\n".join(f"- {q}" for q in asked_questions) + "\n"
            asked_context += "CRITICO: Se la tua domanda è simile a una di queste, NON FARLA. Passa al triage o chiedi altro.\n"

        # --- VINCOLI DINAMICI (GLOBAL BLACKLIST) ---
        known_info_list = []
        if patient_data:
            # Raccogli tutte le informazioni note in una lista piatta
            for key, value in patient_data.items():
                if isinstance(value, list):
                    known_info_list.extend([str(v) for v in value])
                elif isinstance(value, dict):
                    known_info_list.extend([f"{k}: {v}" for k, v in value.items()])
                elif value:
                    known_info_list.append(str(value))

        constraints_str = ""
        if known_info_list:
            constraints_str = "\n⛔️ FORBIDDEN TOPICS (ALREADY STATED BY USER):\n" 
            constraints_str += f"The user has already communicated: {', '.join(known_info_list)}.\n"
            constraints_str += "DO NOT ASK ANYTHING RELATED TO THESE TOPICS. Look for other information.\n"
            # Add specific rules if key fields are present
            if patient_data.get("duration"):
                constraints_str += "- FORBIDDEN to ask 'how long' or duration.\n"
            if patient_data.get("symptoms"):
                constraints_str += "- FORBIDDEN to ask generically 'what are the symptoms'.\n"

        full_system_prompt = self.decide_action_prompt + patient_context + asked_context + constraints_str
        
        messages = [{'role': 'system', 'content': full_system_prompt}]
        messages.extend(chat_history[-12:]) # Finestra di contesto aumentata

        try:
            response = ollama.chat(model='llama3:8b', messages=messages, format='json')
            decision = json.loads(response['message']['content'])

            action = decision.get("action")
            
            # Validazione Azione
            if action == "ask_specialist_followup":
                 if not decision.get("question"):
                      # Safe fallback: if question is missing, ask for clarification
                      return {"action": "ask_specialist_followup", "question": "Could you describe your symptoms better?"}
                 return decision

            elif action == "perform_triage":
                 summary = decision.get("summary", "")
                 # Anti-placeholder check
                 if not summary or summary == "Full summary..." or len(summary) < 10:
                      logger.warning(f" {self.specialty.upper()} used a placeholder summary. Regenerating from messages.")
                      # Fallback: regenerate summary from user messages
                      summary_fallback = " ".join([m['content'] for m in chat_history if m['role'] == 'user'])
                      decision["summary"] = summary_fallback
                 return decision
            
            else: 
                # Unknown or invalid action
                logger.warning(f" {self.specialty.upper()} Unknown Action: '{action}'. Asking for clarification.")
                return {"action": "ask_specialist_followup", "question": "I'm not sure I understood. Can you give me more details?"}

        except (json.JSONDecodeError, Exception) as e:
            logger.error(f" Decision Error {self.specialty.upper()} Agent: {e}. Fallback to generic question.")
            # IMPORTANT: Do not go to triage on error, it's dangerous. Ask for info.
            return {"action": "ask_specialist_followup", "question": "Excuse me, I got confused for a moment. Can you repeat the last symptom?"}



    
    def _run_reflection(self, symptoms_summary: str, initial_analysis: dict, patient_data: dict = None) -> dict:
        """
        Esegue il passo di Riflessione usando Pydantic per validare la struttura.
        """
        logger.info(f" Inizio passo di Riflessione ({self.specialty.upper()})...")
        
        # Formattiamo i dati del paziente per il prompt
        patient_context = ""
        if patient_data:
            patient_context = f"Dati Paziente (Storia/Farmaci/Allergie): {json.dumps(patient_data, indent=2)}"

        reflection_system_prompt = f"""
        You are a senior medical supervisor specialized in {self.specialty.upper()}.
        Your task is to REVIEW and IMPROVE the preliminary medical analysis.
        
        CRITICAL RULES:
        1. The "Initial Analysis" contains conditions identified by the RAG system.
        2. You MUST PRESERVE these conditions unless they are clearly wrong.
        3. You can IMPROVE the reasoning or adjust probabilities if needed.
        4. NEVER return an empty list if the Initial Analysis has conditions.
        5. If the Initial Analysis is empty, generate conditions based on symptoms.
        
        OUTPUT FORMAT:
        Return a valid JSON with this EXACT structure:
        {{
            "potential_conditions": [
                {{"condition": "Name", "probability": "High|Medium|Low", "reasoning": "Explanation"}},
                ...
            ],
            "sources_consulted": []
        }}
        
        PROBABILITY VALUES: Use "High", "Medium", or "Low" (English, capitalized).
        
        PATIENT SYMPTOMS: {symptoms_summary}
        {patient_context}
        
        INITIAL ANALYSIS TO REVIEW:
        {json.dumps(initial_analysis, indent=2)}
        
        YOUR REVIEWED ANALYSIS (JSON only, no other text):
        """

        try:
            reflection_response = ollama.chat(
                model='llama3:8b',
                messages=[{'role': 'system', 'content': reflection_system_prompt}],
                options={'temperature': 0.0},
                format='json' 
            )
            
            content = reflection_response['message']['content']
            
            # --- DEBUG: Log della risposta raw ---
            logger.debug(f"Riflessione RAW response: {content[:500]}...")
            
            # --- VALIDAZIONE PYDANTIC ---
            # Qui avviene la magia: se il JSON è sbagliato, Pydantic solleva un errore
            # e noi lo catturiamo invece di far crashare l'app più avanti.
            validated_data = MedicalAnalysis.model_validate_json(content)
            
            # Convertiamo in dict per il resto del sistema
            refined_analysis = validated_data.model_dump()
            
            # --- DEBUG: Verifica contenuto ---
            if not refined_analysis.get("potential_conditions"):
                logger.warning(f"Riflessione ha ritornato lista VUOTA. Initial analysis aveva: {len(initial_analysis.get('potential_conditions', []))} condizioni")
            
            # Reinseriamo le fonti originali se l'LLM le ha perse
            if not refined_analysis.get("sources_consulted"):
                 refined_analysis["sources_consulted"] = initial_analysis.get("sources_consulted", [])

            logger.info(f"Riflessione Validata con successo ({len(refined_analysis['potential_conditions'])} condizioni).")
            return refined_analysis

        except Exception as e:
            logger.error(f"Errore Validazione Pydantic ({self.specialty.upper()}): {e}")
            logger.debug(f"Contenuto che ha causato errore: {content[:300] if 'content' in dir() else 'N/A'}...")
            logger.warning(f"Uso analisi iniziale come fallback (aveva {len(initial_analysis.get('potential_conditions', []))} condizioni).")
            return initial_analysis


    def _force_diagnosis(self, symptoms: str) -> dict:
        """
        Ultima spiaggia: Chiede all'LLM di generare ipotesi basandosi SOLO sui sintomi.
        Bypassa validazioni complesse per garantire un output.
        """
        prompt = f"""
        You are a medical specialist in {self.specialty.upper()}.
        The patient's symptoms are: "{symptoms}".
        
        The RAG system produced no results.
        YOU MUST list the 3 most probable conditions based on your general knowledge.
        For each condition, include a suggested treatment.
        
        Return ONLY a JSON:
        {{
            "potential_conditions": [
                {{ "condition": "Condition 1", "probability": "Medium", "reasoning": "...", "treatment": "Suggested therapy..." }},
                {{ "condition": "Condition 2", "probability": "Low", "reasoning": "...", "treatment": "Suggested therapy..." }}
            ]
        }}
        """
        try:
            response = ollama.chat(model='llama3:8b', messages=[{'role': 'user', 'content': prompt}], format='json')
            return json.loads(response['message']['content'])
        except Exception as e:
            logger.error(f" Errore Force Diagnosis: {e}")
            return {"potential_conditions": []}

    def perform_analysis_and_triage(self, symptoms_summary: str, extracted_data: dict = None, patient_data: dict = None) -> dict:
        """
        Esegue l'analisi RAG, la Riflessione e la decisione di triage.
        """
        logger.info(f" {self.specialty.upper()} AGENT: Analisi Finale ---")

        # --- COSTRUZIONE QUERY RAG DA PATIENT_DATA (più affidabile del summary LLM) ---
        rag_query = symptoms_summary  # Fallback al summary originale
        
        if patient_data:
            # Costruisci query strutturata dai dati estratti dall'AssistantAgent
            query_parts = []
            
            # Sintomi (campo più importante)
            if patient_data.get("symptoms"):
                symptoms_list = patient_data["symptoms"]
                # Prendi i sintomi più significativi (non "haven't been feeling well")
                meaningful_symptoms = [s for s in symptoms_list if len(s) > 15 and "well" not in s.lower()]
                if meaningful_symptoms:
                    query_parts.append("Patient with: " + ", ".join(meaningful_symptoms[:5]))
            
            # Durata
            if patient_data.get("duration"):
                query_parts.append("Duration: " + ", ".join(patient_data["duration"][:2]))
            
            # Allergie note
            if patient_data.get("allergies"):
                query_parts.append("Known allergies: " + ", ".join(patient_data["allergies"]))
            
            # Storia medica
            if patient_data.get("medical_history"):
                query_parts.append("History: " + ", ".join(patient_data["medical_history"][:2]))
            
            # Se abbiamo costruito qualcosa di significativo, usalo
            if query_parts and len(" ".join(query_parts)) > 30:
                rag_query = " | ".join(query_parts)
                logger.info(f"Query RAG costruita da patient_data: {rag_query[:100]}...")
            else:
                logger.info(f"Uso summary LLM per query RAG: {symptoms_summary[:100]}...")

        # 1. Esecuzione Tool Simbolici
        tool_report_items = []
        if extracted_data:
            try:
                if "temperature_celsius" in extracted_data:
                    # La funzione classify_fever ora gestisce stringhe e virgole internamente
                    result = medical_calculators.classify_fever(extracted_data["temperature_celsius"])
                    if "error" not in result:
                        tool_report_items.append(f"🌡️ Analisi Temperatura: {result['interpretation']}")
                
                if "pain_score" in extracted_data:
                    result = medical_calculators.classify_pain_level(extracted_data["pain_score"])
                    if "error" not in result:
                         tool_report_items.append(f"😖 Analisi Dolore: Livello {result.get('score_input', '?')} - {result['category']}")
                
                if "systolic" in extracted_data and "diastolic" in extracted_data:
                    result = medical_calculators.classify_blood_pressure(extracted_data["systolic"], extracted_data["diastolic"])
                    if "error" not in result:
                        tool_report_items.append(f"💓 Pressione: {result['category']} ({result['interpretation']})")

            except Exception as e:
                logger.warning(f" Errore esecuzione tool: {e}")

        tool_results_md = ""
        if tool_report_items:
            tool_results_md = "\n\n---\n### 📊 Analisi Parametri Vitali\n" + "\n".join(f"- {item}" for item in tool_report_items)

        # 2. Fase RAG (usa la query costruita da patient_data)
        initial_rag_analysis = self.rag_handler.get_potential_conditions(rag_query, self.specialty)
        
        # --- DEBUG: Log dell'analisi RAG ---
        rag_conditions_count = len(initial_rag_analysis.get("potential_conditions", []))
        logger.info(f"RAG ha ritornato {rag_conditions_count} condizioni iniziali.")

        # Controlla fallimento RAG
        if "error" in initial_rag_analysis or not isinstance(initial_rag_analysis.get("potential_conditions"), list):
            error_msg = initial_rag_analysis.get("error", "Formato non valido")
            logger.warning(f"RAG fallito. Motivo: {error_msg}")
            logger.debug(f"Dati ricevuti: {initial_rag_analysis}")
            
            # NON ritornare subito! Passiamo al Supervisore con una lista vuota.
            # Questo attiverà la generazione basata su conoscenza generale.
            initial_rag_analysis = {"potential_conditions": [], "error": error_msg}
        
        # 3. Fase di Riflessione (SEMPRE ATTIVA)
        # Anche se RAG non ha trovato nulla, chiediamo al Supervisore di ragionare sui sintomi.
        final_analysis = self._run_reflection(symptoms_summary, initial_rag_analysis, patient_data)

        # --- HARD FALLBACK: SE ANCORA VUOTO, FORZA GENERAZIONE ---
        if not final_analysis.get("potential_conditions"):
            logger.warning(f" {self.specialty.upper()}: Analisi ancora vuota dopo riflessione. FORZO GENERAZIONE.")
            final_analysis = self._force_diagnosis(symptoms_summary)

        # 4. Fase Simbolica (Decisione Triage)
        
        # --- ORDINAMENTO E LIMITAZIONE REFERTO ---
        conditions = final_analysis.get("potential_conditions", [])
        if conditions:
            # Mappa probabilità -> peso numerico (supporta IT e EN)
            prob_map = {
                # Italiano
                "alta": 3, "alto": 3,
                "media": 2, "medio": 2,
                "bassa": 1, "basso": 1,
                # Inglese
                "high": 3,
                "medium": 2, "moderate": 2,
                "low": 1
            }
            
            # Funzione helper per ottenere il peso (default 0 se sconosciuto)
            def get_weight(cond):
                p = cond.get("probability", "").lower().strip()
                return prob_map.get(p, 0)
            
            # Ordina decrescente (Alta -> Media -> Bassa)
            conditions.sort(key=get_weight, reverse=True)
            
            # Tieni solo i Top 3
            final_analysis["potential_conditions"] = conditions[:3]
            
            # --- LOGGING TERMINALE REFERTO ---
            logger.info(f"REFERTO MEDICO ({self.specialty.upper()})")
            for i, cond in enumerate(final_analysis["potential_conditions"]):
                logger.info(f"{i+1}. {cond.get('condition')} ({cond.get('probability')})")
                logger.debug(f"   Reasoning: {cond.get('reasoning')}")

        recommendation = self.triage_engine.get_recommendation(final_analysis, extracted_data)

        # 5. Costruzione Output Finale
        final_response_data = {
            "specialist_consulted": self.specialty,
            "livello": recommendation.get('livello', 'Insufficient Info'),
            "messaggio": recommendation.get('messaggio', self.triage_engine.kb['risposta_default']['messaggio']),
            "referto": final_analysis.get("potential_conditions", []),
            "sources_consulted": final_analysis.get("sources_consulted", []),
            "tool_report": tool_results_md 
        }
        
        return {"type": "triage_result", "data": final_response_data}