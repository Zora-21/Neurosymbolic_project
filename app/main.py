from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import os
import threading 
import time      

# --- IMPORTS DEL PROGETTO ---
from app.agents.router_agent import RouterAgent
from app.agents.specialist_agent import SpecialistAgent
from app.agents.assistant_agent import AssistantAgent
from app.logic.rag_handler import RAGHandler
from app.logic.symbolic_engine import TriageEngine
# Importiamo il gestore di sessione
from app.logic.session_manager import SessionManager 

from app.logic.image_analyzer import ImageAnalyzer
from app.logger import get_api_logger
from app.translations import get_translation, DEFAULT_LANGUAGE

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Logger per questo modulo
logger = get_api_logger()

# --- SETUP APPLICAZIONE ---
app = FastAPI(title="Multi-Agent Conversational RAG Triage Bot API")

# --- CONFIGURAZIONE PERCORSI ---
# Calcoliamo i percorsi assoluti per evitare errori "File not found"
MAIN_PY_DIR = os.path.dirname(os.path.abspath(__file__)) 
PROJECT_ROOT = os.path.dirname(MAIN_PY_DIR) 
VECTOR_DB_PATH = os.path.join(PROJECT_ROOT, "vector_dbs") 

# Mount Static Files
app.mount("/static", StaticFiles(directory=os.path.join(MAIN_PY_DIR, "static")), name="static")

# --- RILEVAMENTO SPECIALISTI DISPONIBILI ---
AVAILABLE_SPECIALISTS = []
if os.path.exists(VECTOR_DB_PATH):
    try:
        AVAILABLE_SPECIALISTS = [
            d.lower() for d in os.listdir(VECTOR_DB_PATH)
            if os.path.isdir(os.path.join(VECTOR_DB_PATH, d)) and not d.startswith('.')
        ]
    except Exception as e:
        logger.error(f"Errore lettura directory vector_dbs: {e}")

if not AVAILABLE_SPECIALISTS:
    logger.warning(f"Nessun DB vettoriale trovato in '{VECTOR_DB_PATH}'.")
else:
     logger.info(f"Specialisti attivi: {AVAILABLE_SPECIALISTS}")

# --- INIZIALIZZAZIONE COMPONENTI ---
logger.info("Inizializzazione Motori IA...")
rag_handler = RAGHandler(base_db_path=VECTOR_DB_PATH) 
triage_engine = TriageEngine()
router_agent = RouterAgent(available_specialists=AVAILABLE_SPECIALISTS)
assistant_agent = AssistantAgent() # Agente Scriba
image_analyzer = ImageAnalyzer() # Inizializza Analizzatore Immagini
session_manager = SessionManager() # Inizializza Gestore Sessioni

# Cache per le istanze degli specialisti (per non ricrearli ad ogni chiamata)
specialist_agents_instances = {}

# --- MODELLI DATI API (Pydantic) ---
class UserMessage(BaseModel):
    message: str
    session_id: str
    image_data: Optional[str] = None  # Base64 string
    language: Optional[str] = "en"  # "en" or "it", default English

class ResetRequest(BaseModel):
    session_id: Optional[str] = None

class AgentResponse(BaseModel):
    response: str
    agent_type: str
    is_final: bool = False
    referto: Optional[List[Dict]] = None
    sources: Optional[List[str]] = None
    extracted_info: Optional[Dict] = None
    extra_messages: Optional[List[Dict]] = None
    patient_data: Optional[Dict] = None

# --- FUNZIONI HELPER ---
def get_specialist_agent(specialist_name: str, language: str = "en") -> Optional[SpecialistAgent]:
    """Factory per ottenere o creare l'agente specialista richiesto."""
    name_lower = specialist_name.lower()
    if name_lower not in AVAILABLE_SPECIALISTS:
        return None
    
    if name_lower not in specialist_agents_instances:
        specialist_agents_instances[name_lower] = SpecialistAgent(
            name_lower, rag_handler, triage_engine, language=language
        )
    else:
        # Aggiorna la lingua se già esiste
        specialist_agents_instances[name_lower].set_language(language)
    return specialist_agents_instances[name_lower]

# --- BACKGROUND TASK: PULIZIA SESSIONI ---
# --- BACKGROUND TASK: PULIZIA SESSIONI ---
# TODO: Implementare cleanup in SessionManager se necessario
# def background_cleanup_task():
#     """Thread che gira ogni 15 min per pulire le sessioni scadute."""
#     print("🧹 Avvio thread di pulizia sessioni background...")
#     while True:
#         time.sleep(900) # 900 secondi = 15 minuti
#         try:
#             # session_manager.cleanup_expired_sessions()
#             pass
#         except Exception as e:
#             print(f"❌ Errore nel thread di pulizia: {e}")
# 
# # Avvia il thread come demone (si chiude se l'app si chiude)
# # cleanup_thread = threading.Thread(target=background_cleanup_task, daemon=True)
# # cleanup_thread.start()


# --- ENDPOINT: CHAT PRINCIPALE ---
@app.post("/chat", response_model=AgentResponse)
async def handle_chat(user_message: UserMessage):
    """
    Gestisce il flusso conversazionale.
    1. Recupera stato sessione da SQLite.
    2. Esegue logica Agente (Router o Specialista).
    3. Salva nuovo stato su SQLite (o cancella se finito).
    """
    session_id = user_message.session_id

    # 1. Recupera la sessione dal DB
    session_state = session_manager.load_session(session_id)

    # Gestione Reset
    if user_message.message == "/reset":
        session_state = {
            "chat_history": [],
            "current_agent": "router",
            "last_summary": "",
            "asked_questions": [],
            "language": user_message.language or DEFAULT_LANGUAGE
        }
        session_manager.save_session(session_id, session_state)
        # Resetta anche i dati clinici
        assistant_agent._save_data(session_id, {
            "symptoms": [], "duration": [], "negative_findings": [],
            "medical_history": [], "medications": [], "allergies": [],
            "vital_signs": {}, "notes": ""
        })
        lang = session_state.get("language", DEFAULT_LANGUAGE)
        return AgentResponse(
            response=get_translation(lang, "session_reset"),
            agent_type="system",
            is_final=False,
            patient_data={}
        )

    # Gestione Diagnosi Forzata
    if user_message.message == "/diagnose":
        try:
            if session_state["current_agent"] in AVAILABLE_SPECIALISTS:
                logger.warning(f"DIAGNOSI FORZATA RICHIESTA (Sessione: {session_id})")
                active_specialist = get_specialist_agent(session_state["current_agent"])
                
                # Genera un sommario al volo dai messaggi utente
                summary_forced = " ".join([m['content'] for m in session_state["chat_history"] if m['role'] == 'user'])
                
                # Carica i dati del paziente (senza aggiornarli con "/diagnose")
                patient_data = assistant_agent._load_data(session_id)

                # Forza l'analisi
                triage_result = active_specialist.perform_analysis_and_triage(summary_forced, {}, patient_data)
                
                if triage_result.get("type") == "triage_result":
                    data = triage_result.get("data", {})
                    
                    # Build final response
                    md_response = f"**FORCED DIAGNOSIS (Outcome: {data.get('livello', 'N/A')})**\n\n{data.get('messaggio', '')}"
                    if data.get("tool_report"):
                        md_response += f"\n{data.get('tool_report')}"
                    
                    if data.get("referto"):
                        md_response += "\n\n---\n### Clinical Hypotheses (AI)\n"
                        for item in data.get("referto"):
                            treatment = item.get('treatment', '')
                            md_response += f"- **{item.get('condition')}** ({item.get('probability')})\n  _{item.get('reasoning')}_\n"
                            if treatment:
                                md_response += f"  💊 **Suggested Treatment:** {treatment}\n"

                    # Resetta sessione dopo diagnosi
                    session_manager.save_session(session_id, {
                        "chat_history": [], "current_agent": "router", "last_summary": "", "asked_questions": []
                    })
                    
                    return AgentResponse(
                        response=md_response,
                        agent_type=session_state["current_agent"],
                        is_final=True,
                        referto=data.get("referto"),
                        sources=data.get("sources_consulted"),
                        patient_data=patient_data
                    )
            else:
                return AgentResponse(
                    response="You must be in contact with a specialist to force a diagnosis.",
                    agent_type="system",
                    is_final=False
                )
        except Exception as e:
            import traceback
            traceback.print_exc()
            return AgentResponse(
                response=f"Error during forced diagnosis: {str(e)}",
                agent_type="system",
                is_final=False
            )

    logger.info(f"Messaggio ricevuto (Sessione: {session_id[:8]}...) - Agente attuale: {session_state['current_agent']}")

    # --- GESTIONE LINGUA ---
    # Salva la lingua nella sessione (la prima volta o quando cambia)
    request_lang = user_message.language or DEFAULT_LANGUAGE
    if "language" not in session_state or session_state["language"] != request_lang:
        session_state["language"] = request_lang
        # Aggiorna la lingua degli agenti
        router_agent.set_language(request_lang)
        assistant_agent.set_language(request_lang)
    lang = session_state.get("language", DEFAULT_LANGUAGE)

    # --- GESTIONE IMMAGINE ---
    image_context = ""
    if user_message.image_data:
        logger.info("Immagine ricevuta. Avvio analisi...")
        image_description = image_analyzer.analyze_image(user_message.image_data)
        image_context = f"\n\n[SYSTEM NOTE: User uploaded an image. Visual analysis detects: {image_description}]"
        # Add analysis to history as system message
        session_state["chat_history"].append({"role": "system", "content": f"User Image Analysis: {image_description}"})

    # Aggiungi messaggio utente alla cronologia (con eventuale contesto immagine appeso per chiarezza)
    full_user_message = user_message.message + image_context
    session_state["chat_history"].append({"role": "user", "content": full_user_message})
    current_history = session_state["chat_history"]

    # --- AGENTE ASSISTENTE (SCRIBA) ---
    # Aggiorna i dati del paziente in background
    logger.info("Assistant Agent: Analisi messaggio utente...")
    
    # Recupera l'ultimo messaggio dell'agente per il contesto (se esiste)
    last_agent_msg = None
    if session_state["chat_history"]:
        for msg in reversed(session_state["chat_history"][:-1]): # Escludi l'ultimo che è l'utente
            if msg["role"] == "assistant":
                last_agent_msg = msg["content"]
                break

    patient_data = assistant_agent.update_patient_data(session_id, user_message.message, last_agent_msg)

    # Response variables
    agent_response_content = "Unexpected error."
    agent_type = session_state["current_agent"]
    is_final = False
    referto_data = None
    sources_data = None
    extracted_info = None
    extra_messages = None  # Inizializzazione sicura

    try:
        # --- CASO 1: ROUTER (Smistamento) ---
        if agent_type == "router":
            router_decision = router_agent.decide_routing(current_history, patient_data)
            action = router_decision.get("action")

            if action == "ask_general_followup":
                agent_response_content = router_decision.get("question")
                # Rimaniamo sul router
            
            elif action == "route_to_specialist":
                specialist_name = router_decision.get("specialist").lower()
                summary = router_decision.get("summary")
                
                # Verifichiamo che lo specialista esista
                if get_specialist_agent(specialist_name, lang):
                    session_state["current_agent"] = specialist_name
                    session_state["last_summary"] = summary
                    agent_type = specialist_name
                    
                    # 1. Router Message (Transition) - tradotto
                    router_msg = get_translation(lang, "connecting_specialist", specialist=specialist_name.capitalize())
                    session_state["chat_history"].append({"role": "assistant", "agent": "router", "content": router_msg})
                    
                    # 2. Specialist Message (Greeting) - tradotto
                    agent_response_content = get_translation(lang, "specialist_greeting")
                    
                    # Prepare extra messages for frontend
                    extra_messages = [{"role": "assistant", "agent": "router", "content": router_msg}]
                else:
                    agent_response_content = get_translation(lang, "specialist_unavailable", specialist=specialist_name)
                    is_final = True  # Close if critical routing error

            elif action == "cannot_route":
                agent_response_content = router_decision.get("message", get_translation(lang, "cannot_route"))
                is_final = True
            
            else:
                agent_response_content = get_translation(lang, "did_not_understand")

        # --- CASO 2: SPECIALISTA (Analisi) ---
        elif agent_type in AVAILABLE_SPECIALISTS:
            active_specialist = get_specialist_agent(agent_type, lang)
            
            # Decide se chiedere altro o fare triage
            asked_questions = session_state.get("asked_questions", [])
            decision = active_specialist.decide_next_action(current_history, patient_data, asked_questions)
            action = decision.get("action")

            if action == "ask_specialist_followup":
                question = decision.get("question")
                agent_response_content = question
                is_final = False
                
                # Salviamo la domanda fatta per evitare ripetizioni
                if question:
                    session_state["asked_questions"].append(question)

            elif action == "perform_triage":
                # Recupera dati per l'analisi
                summary = decision.get("summary", session_state.get("last_summary"))
                extracted_data = decision.get("extracted_data", {})
                
                # Esegue RAG + Logica Simbolica (Passiamo anche i dati del paziente!)
                triage_result = active_specialist.perform_analysis_and_triage(summary, extracted_data, patient_data)

                if triage_result.get("type") == "triage_result":
                    data = triage_result.get("data", {})
                    
                    livello = data.get("livello", "N/A")
                    messaggio = data.get("messaggio", "Analysis complete.")
                    tool_report = data.get("tool_report", "")
                    referto_data = data.get("referto", [])
                    sources_data = data.get("sources_consulted", [])

                    # Build final Markdown response
                    md_response = f"**Outcome: {livello}**\n\n{messaggio}"
                    if tool_report:
                        md_response += f"\n{tool_report}"
                    
                    # Aggiungi referto al markdown (spostato PRIMA del return)
                    if referto_data:
                        md_response += "\n\n---\n### Clinical Hypotheses (AI)\n"
                        for item in referto_data:
                            nome = item.get('condition', 'N/A')
                            prob = item.get('probability', 'N/A')
                            reason = item.get('reasoning', '')
                            treatment = item.get('treatment', '')
                            md_response += f"- **{nome}** ({prob})\n  _{reason}_\n"
                            if treatment:
                                md_response += f"  💊 **Suggested Treatment:** {treatment}\n"
                    
                    agent_response_content = md_response
                    is_final = True  # Triage completato
                    
                    # Passiamo i dati estratti alla risposta API
                    return AgentResponse(
                        response=agent_response_content,
                        agent_type=agent_type,
                        is_final=is_final,
                        referto=referto_data,
                        sources=sources_data,
                        extracted_info=extracted_data,
                        extra_messages=extra_messages,
                        patient_data=patient_data
                    )
                else:
                    agent_response_content = "An error occurred during report generation."
                    is_final = True
            else:
                agent_response_content = "I didn't understand. Try again."

        else:
            # Inconsistent state (e.g., agent removed)
            agent_response_content = "Session state error. Please restart."
            is_final = True

    except Exception as e:
        logger.error(f"CRITICAL ERROR in /chat: {e}")
        agent_response_content = "A technical error occurred on the server."
        is_final = True

    # Aggiungi risposta assistente alla storia
    session_state["chat_history"].append({"role": "assistant", "content": agent_response_content})

    # 3. SALVATAGGIO O CANCELLAZIONE SESSIONE
    # 3. SALVATAGGIO O CANCELLAZIONE SESSIONE
    if is_final:
        logger.info(f"Sessione conclusa: {session_id}")
        # Per ora resettiamo solo lo stato in memoria/file
        session_state = {
            "chat_history": [],
            "current_agent": "router",
            "last_summary": "",
            "asked_questions": []
        }
        session_manager.save_session(session_id, session_state)
    else:
        session_manager.save_session(session_id, session_state)

    return AgentResponse(
        response=agent_response_content,
        agent_type=agent_type,
        is_final=is_final,
        referto=referto_data,
        sources=sources_data,
        extra_messages=extra_messages,
        patient_data=patient_data
    )

# --- ALTRI ENDPOINT ---
@app.post("/reset")
def reset_session_endpoint(request: ResetRequest):
    """Resetta manualmente una sessione."""
    if request.session_id:

        # Reset manuale
        empty_state = {
            "chat_history": [],
            "current_agent": "router",
            "last_summary": "",
            "asked_questions": []
        }
        session_manager.save_session(request.session_id, empty_state)
        return {"message": f"Sessione {request.session_id} resettata."}
    return {"message": "ID sessione mancante."}

@app.get("/")
def read_root():
    return FileResponse(os.path.join(MAIN_PY_DIR, "static", "index.html"))

@app.get("/favicon.ico")
async def favicon():
    return FileResponse(os.path.join(MAIN_PY_DIR, "static", "favicon.ico")) if os.path.exists(os.path.join(MAIN_PY_DIR, "static", "favicon.ico")) else None