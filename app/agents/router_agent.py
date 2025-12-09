import ollama
import json
from typing import Literal, Optional
from pydantic import BaseModel, Field, ValidationError
from app.logger import get_agent_logger
from app.translations import ROUTER_SYSTEM_PROMPTS, get_translation, DEFAULT_LANGUAGE

# Logger per questo modulo
logger = get_agent_logger()

# --- DEFINIZIONE MODELLI DI OUTPUT (Pydantic) ---
class RouterOutput(BaseModel):
    action: Literal["ask_general_followup", "route_to_specialist", "cannot_route"] = Field(
        ..., description="L'azione decisa dal router."
    )
    question: Optional[str] = Field(
        None, description="La domanda da porre all'utente (solo se action è ask_general_followup)."
    )
    specialist: Optional[str] = Field(
        None, description="Il nome dello specialista in minuscolo (solo se action è route_to_specialist)."
    )
    summary: Optional[str] = Field(
        None, description="Riassunto dei sintomi per lo specialista (solo se action è route_to_specialist)."
    )
    message: Optional[str] = Field(
        None, description="Messaggio di spiegazione (solo se action è cannot_route)."
    )

class RouterAgent:
    def __init__(self, available_specialists: list, language: str = DEFAULT_LANGUAGE):
        """
        Inizializza l'agente Router.
        """
        self.specialists = [s.lower() for s in available_specialists]
        self.language = language
        
        # Skill map to help routing (descrizioni generiche)
        self.specialist_descriptions = {
            "cardiologo": "Heart, chest pain, palpitations, arrhythmias, high blood pressure.",
            "dermatologo": "Skin, moles, rashes, itching, acne, eczema.",
            "endocrinologo": "Hormones, thyroid, diabetes, metabolism, fatigue.",
            "gastroenterologo": "Stomach, digestion, reflux, abdominal pain, nausea.",
            "geriatra": "Elderly, age-related problems, dementia, frailty.",
            "infettivologo": "Infections, fever, urinary infections, viruses, bacteria.",
            "nefrologo": "Kidneys, kidney failure, kidney stones, dialysis.",
            "oncologo": "Tumors, cancer, masses, chemotherapy.",
            "pneumologo": "Lungs, cough, asthma, bronchitis, breathing problems.",
            "reumatologo": "Joints, arthritis, autoimmune diseases, fibromyalgia.",
            "allergologo": "Allergies, allergic reactions, food allergies, hay fever.",
            "ematologo": "Blood, anemia, bleeding, platelets, leukemia."
        }
        
        # Mappa sinonimi per normalizzare l'output dell'LLM
        self.synonyms = {
            "cardiologia": "cardiologo", "cuore": "cardiologo",
            "dermatologia": "dermatologo", "pelle": "dermatologo",
            "endocrinologia": "endocrinologo",
            "gastroenterologia": "gastroenterologo", "stomaco": "gastroenterologo",
            "geriatria": "geriatra",
            "infettivologia": "infettivologo", "infezioni": "infettivologo",
            "nefrologia": "nefrologo", "reni": "nefrologo",
            "oncologia": "oncologo", "tumori": "oncologo",
            "pneumologia": "pneumologo", "polmoni": "pneumologo",
            "reumatologia": "reumatologo", "reumi": "reumatologo", "ossa": "reumatologo",
            "allergologia": "allergologo",
            "ematologia": "ematologo", "sangue": "ematologo"
        }
        
        # Costruiamo una stringa descrittiva per il prompt
        specialist_info = []
        for s in self.specialists:
            desc = self.specialist_descriptions.get(s, "General medical specialist.")
            specialist_info.append(f"- {s}: {desc}")
        
        specialist_list_str = "\n".join(specialist_info)
        
        # Prompt multilingua
        self.system_prompt = ROUTER_SYSTEM_PROMPTS.get(self.language, ROUTER_SYSTEM_PROMPTS["en"]).format(
            specialist_list=specialist_list_str
        )
    
    def set_language(self, language: str):
        """Aggiorna la lingua del router dinamicamente."""
        if language in ["en", "it"]:
            self.language = language
            # Ricostruisci il prompt
            specialist_info = []
            for s in self.specialists:
                desc = self.specialist_descriptions.get(s, "General medical specialist.")
                specialist_info.append(f"- {s}: {desc}")
            specialist_list_str = "\n".join(specialist_info)
            self.system_prompt = ROUTER_SYSTEM_PROMPTS.get(self.language, ROUTER_SYSTEM_PROMPTS["en"]).format(
                specialist_list=specialist_list_str
            )

    def decide_routing(self, chat_history: list, patient_data: dict = None) -> dict:
        """
        Analizza la cronologia e i dati paziente per decidere il routing.
        """
        # Costruzione contesto paziente dai dati estratti dall'AssistantAgent
        patient_context = ""
        if patient_data:
            context_parts = []
            if patient_data.get("symptoms"):
                context_parts.append(f"SYMPTOMS: {', '.join(patient_data['symptoms'][:5])}")
            if patient_data.get("allergies"):
                context_parts.append(f"ALLERGIES: {', '.join(patient_data['allergies'])}")
            if patient_data.get("medical_history"):
                context_parts.append(f"⚠️ MEDICAL HISTORY: {', '.join(patient_data['medical_history'][:3])}")
            if patient_data.get("duration"):
                context_parts.append(f"DURATION: {', '.join(patient_data['duration'][:2])}")
            if patient_data.get("medications"):
                context_parts.append(f"MEDICATIONS: {', '.join(patient_data['medications'][:3])}")
            
            if context_parts:
                patient_context = "\n\n--- EXTRACTED PATIENT DATA (what you already know) ---\n" + "\n".join(context_parts)
                patient_context += "\n\nBased on this data, decide: do you have enough to route, or do you need more info?"
        
        full_prompt = self.system_prompt + patient_context
        
        messages = [{'role': 'system', 'content': full_prompt}]
        messages.extend(chat_history[-12:])

        try:
            response = ollama.chat(
                model='llama3:8b', 
                messages=messages, 
                format='json',
                options={'temperature': 0.0}
            )
            
            raw_content = response['message']['content']
            
            # --- VALIDAZIONE PYDANTIC ---
            try:
                validated_output = RouterOutput.model_validate_json(raw_content)
                decision = validated_output.model_dump()
                
                # Logica extra di validazione (controllo se lo specialista esiste davvero)
                if decision['action'] == 'route_to_specialist':
                    chosen_spec = decision.get('specialist', '').lower().strip()
                    
                    # Normalizzazione Sinonimi
                    if chosen_spec in self.synonyms:
                        chosen_spec = self.synonyms[chosen_spec]
                    
                    if chosen_spec not in self.specialists:
                        logger.warning(f"Router hallucinated specialist '{chosen_spec}'. Fallback.")
                        return {
                            "action": "cannot_route", 
                            "message": f"I don't have a specialist available for '{chosen_spec}'."
                        }
                    decision['specialist'] = chosen_spec # Normalize
                
                logger.info(f"Router Decision Validated: {decision['action']}")
                return decision

            except ValidationError as e:
                logger.error(f"Router Pydantic Validation Error: {e}")
                # Intelligent fallback: if JSON is broken, ask to rephrase
                return {"action": "ask_general_followup", "question": "Sorry, I didn't understand well. Can you repeat the main symptom?"}

        except Exception as e:
            logger.error(f"Generic Router Error: {e}")
            return {"action": "cannot_route", "message": "Technical error in routing system."}