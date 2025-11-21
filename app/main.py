from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import os
import json
import threading # Per il thread di pulizia
import time      # Per il thread di pulizia
from datetime import datetime, timedelta # Per controllare l'inattività

# Import Agenti e Handler
from app.agents.router_agent import RouterAgent
from app.agents.specialist_agent import SpecialistAgent
from app.logic.rag_handler import RAGHandler
from app.logic.symbolic_engine import TriageEngine
# Potresti voler importare la tua config qui se l'hai creata
# from app.config import ...

# --- SETUP APPLICAZIONE ---
app = FastAPI(title="Multi-Agent Conversational RAG Triage Bot API")

# --- Percorso Relativo per i DB (Corretto) ---
MAIN_PY_DIR = os.path.dirname(os.path.abspath(__file__)) 
PROJECT_ROOT = os.path.dirname(MAIN_PY_DIR) 

# --- ERRORE PRECEDENTE CORRETTO: Percorso per RAG Handler ---
# Questo è il percorso che passeremo al RAGHandler
CORRECT_BASE_DB_PATH = os.path.join(PROJECT_ROOT, "vector_dbs") 

AVAILABLE_SPECIALISTS = []
if os.path.exists(CORRECT_BASE_DB_PATH):
    try:
        AVAILABLE_SPECIALISTS = [
            d for d in os.listdir(CORRECT_BASE_DB_PATH)
            if os.path.isdir(os.path.join(CORRECT_BASE_DB_PATH, d)) and not d.startswith('.')
        ]
        AVAILABLE_SPECIALISTS = [s.lower() for s in AVAILABLE_SPECIALISTS]
    except Exception as e:
        print(f"❌ Errore durante la lettura delle cartelle degli specialisti in {CORRECT_BASE_DB_PATH}: {e}")

if not AVAILABLE_SPECIALISTS:
    print(f"⚠️ ATTENZIONE: Nessun database vettoriale valido trovato in '{CORRECT_BASE_DB_PATH}'.")
else:
     print(f"✅ Specialisti disponibili rilevati: {AVAILABLE_SPECIALISTS}")

# --- Inizializzazione Handler e Agenti (Corretta) ---
# Inietta il percorso corretto nel RAGHandler
rag_handler = RAGHandler(base_db_path=CORRECT_BASE_DB_PATH) 
triage_engine = TriageEngine()
router_agent = RouterAgent(available_specialists=AVAILABLE_SPECIALISTS)
specialist_agents_instances = {}


# --- *** MODIFICA: GESTIONE STATO SESSIONE CON TIMESTAMP *** ---

# La sessione ora contiene lo stato E il timestamp dell'ultimo accesso
# Esempio: "session_id_xyz": { "state": {...}, "last_access_time": datetime_obj }
global_sessions: Dict[str, Dict[str, Any]] = {}

# Lock per rendere la modifica di global_sessions thread-safe
# (sicuro da usare sia dall'API che dal thread di pulizia)
session_lock = threading.Lock()

def get_default_session_state() -> Dict[str, Any]:
    """Ritorna uno stato di sessione pulito."""
    return {
        "current_agent": "router",
        "chat_history": [],
        "last_summary": None
    }

def get_session(session_id: str) -> Dict[str, Any]:
    """
    Recupera lo stato della sessione per un dato ID.
    Se non esiste, ne crea una nuova.
    Aggiorna il timestamp di ultimo accesso.
    """
    with session_lock: # Blocca l'accesso mentre leggiamo/scriviamo
        if session_id not in global_sessions:
            print(f"Creazione nuova sessione: {session_id}")
            global_sessions[session_id] = {
                "state": get_default_session_state(),
                "last_access_time": datetime.utcnow() # Usa UTC per coerenza
            }
        else:
            # Aggiorna il timestamp perché c'è stata attività
            global_sessions[session_id]["last_access_time"] = datetime.utcnow()
            
        return global_sessions[session_id]["state"] # Ritorna solo lo stato

def delete_session(session_id: str):
    """Rimuove in sicurezza una sessione."""
    with session_lock:
        if session_id in global_sessions:
            del global_sessions[session_id]
            print(f"Sessione {session_id} rimossa.")
# --- *** FINE MODIFICA STATO *** ---


# --- MODELLI DATI Pydantic (Invariati) ---
class UserMessage(BaseModel):
    message: str
    session_id: str

class ResetRequest(BaseModel):
    session_id: Optional[str] = None

class AgentResponse(BaseModel):
    response: str
    agent_type: str
    is_final: bool = False
    referto: Optional[List[Dict]] = None
    sources: Optional[List[str]] = None

# --- FUNZIONE HELPER (Invariata) ---
def get_specialist_agent(specialist_name: str) -> Optional[SpecialistAgent]:
    specialist_name_lower = specialist_name.lower()
    if specialist_name_lower not in AVAILABLE_SPECIALISTS:
        return None
    if specialist_name_lower not in specialist_agents_instances:
        specialist_agents_instances[specialist_name_lower] = SpecialistAgent(
            specialist_name_lower, rag_handler, triage_engine
        )
    return specialist_agents_instances[specialist_name_lower]

# --- ENDPOINT API PRINCIPALE (Modificato per aggiornare timestamp) ---
@app.post("/chat", response_model=AgentResponse)
async def handle_chat(user_message: UserMessage):
    """
    Gestisce un messaggio dell'utente per una sessione specifica.
    L'accesso aggiorna il timestamp di ultimo accesso della sessione.
    """
    # *** MODIFICA: get_session ora aggiorna automaticamente il timestamp ***
    session_state = get_session(user_message.session_id)
    print(f"Gestione chat per sessione: {user_message.session_id} (Agente: {session_state['current_agent']})")
    
    # ... (Tutta la logica di /chat rimane invariata) ...
    # ... (Aggiungi la tua logica per router/specialista qui) ...
    
    session_state["chat_history"].append({"role": "user", "content": user_message.message})
    current_history = session_state["chat_history"]

    agent_response_content = "Mi dispiace, si è verificato un errore imprevisto."
    agent_type = session_state["current_agent"]
    is_final = False
    referto_data = None
    sources_data = None
    active_agent_name = session_state["current_agent"]

    try:
        if active_agent_name == "router":
            router_decision = router_agent.decide_routing(current_history)
            action = router_decision.get("action")
            if action == "ask_general_followup":
                agent_response_content = router_decision.get("question")
                agent_type = "router"
            elif action == "cannot_route":
                agent_response_content = router_decision.get("message")
                agent_type = "router"; is_final = True
            elif action == "route_to_specialist":
                specialist_name = router_decision.get("specialist").lower()
                summary = router_decision.get("summary")
                specialist_agent = get_specialist_agent(specialist_name)
                if not specialist_agent:
                    agent_response_content = f"Errore: specialista '{specialist_name}' non trovato."
                    agent_type = "system"; is_final = True
                else:
                    session_state["current_agent"] = specialist_name
                    session_state["last_summary"] = summary
                    agent_type = specialist_name
                    agent_response_content = f"La metto in contatto con l'assistente **{specialist_name.capitalize()}**..."
            else:
                agent_response_content = "Errore durante lo smistamento."; agent_type = "system"; is_final = True

        elif active_agent_name in AVAILABLE_SPECIALISTS:
            specialist_agent = get_specialist_agent(active_agent_name)
            specialist_decision = specialist_agent.decide_next_action(current_history)
            action = specialist_decision.get("action")

            if action == "ask_specialist_followup":
                agent_response_content = specialist_decision.get("question")
                agent_type = active_agent_name; is_final = False
            elif action == "perform_triage":
                summary = specialist_decision.get("summary", session_state.get("last_summary"))
                extracted_data = specialist_decision.get("extracted_data", {})
                triage_result = triage_result = specialist_agent.perform_analysis_and_triage(summary, extracted_data)
                if triage_result.get("type") == "triage_result":
                    triage_data = triage_result.get("data", {})
                    livello = triage_data.get("livello", "N/D")
                    messaggio = triage_data.get("messaggio", "Analisi completata.")

                    # --- RIGA DA AGGIUNGERE ---
                    tool_report_md = triage_data.get("tool_report", "") # Prendiamo il report dei tool
                    # ---------------------------

                    referto_data = triage_data.get("referto", [])
                    sources_data = triage_data.get("sources_consulted", [])
                    referto_md = ""
                    if referto_data:
                         referto_md += "\n\n---\n### Ipotesi Preliminari (Non Diagnosi)\n"
                         referto_md += f"*Basandomi sulle informazioni e sulle fonti della mia specializzazione ({active_agent_name.capitalize()})...*\n"
                         for item in referto_data:
                              motivazione = item.get('reasoning') or item.get('rationale') or 'N/A'
                              referto_md += f"\n- **{item.get('condition','N/A')}** (Probabilità: {item.get('probability','N/A')})\n  - *Motivazione:* {motivazione}\n"
                    agent_response_content = f"**{livello}**\n\n{messaggio}" + tool_report_md + referto_md
                    is_final = True
                else:
                    agent_response_content = "Errore durante l'analisi finale."; is_final = True
            else:
                 agent_response_content = "Errore assistente specializzato."; is_final = True
            agent_type = active_agent_name
        
        else:
            agent_response_content = "Errore di Stato. Resettare."; agent_type = "system"; is_final = True

    except Exception as e:
        agent_response_content = f"Errore generale: {e}"; agent_type = "system"; is_final = True
    
    session_state["chat_history"].append({"role": "assistant", "content": agent_response_content})

    # --- MODIFICA: Rimuovi la sessione se è finale ---
    if is_final:
        print(f"--- Conversazione Conclusa (Sessione: {user_message.session_id}) ---")
        delete_session(user_message.session_id) # Rimuove la sessione dalla memoria

    return AgentResponse(
        response=agent_response_content,
        agent_type=agent_type,
        is_final=is_final,
        referto=referto_data,
        sources=sources_data
    )

# --- Endpoint Ausiliari (Modificato) ---
@app.post("/reset")
def reset_session(request: ResetRequest):
    """Resetta (elimina) una specifica sessione utente nel backend."""
    session_id = request.session_id
    if session_id:
        print(f"--- Reset Manuale della Sessione Richiesto (Sessione: {session_id}) ---")
        delete_session(session_id) # Usa la funzione thread-safe
        return {"message": f"Stato della sessione {session_id} resettato con successo."}
    return {"message": "Sessione non trovata o ID non fornito."}


@app.get("/")
def read_root():
    return {"status": f"Server Multi-Agente attivo! Specialisti: {AVAILABLE_SPECIALISTS}"}


# --- *** NUOVA SEZIONE: PULIZIA AUTOMATICA SESSIONI IN BACKGROUND *** ---

SESSION_EXPIRATION_MINUTES = 60
CLEANUP_INTERVAL_SECONDS = 900 # 15 minuti

def cleanup_inactive_sessions():
    """
    Scansiona global_sessions e rimuove le sessioni inattive
    da più di SESSION_EXPIRATION_MINUTES.
    """
    print(f"[{datetime.utcnow()}] Esecuzione pulizia sessioni inattive...")
    expiration_time = datetime.utcnow() - timedelta(minutes=SESSION_EXPIRATION_MINUTES)
    
    # Crea una lista di sessioni da eliminare per evitare di modificare
    # il dizionario mentre lo si sta iterando
    sessions_to_delete = []
    
    with session_lock: # Blocca l'accesso
        for session_id, data in global_sessions.items():
            if data["last_access_time"] < expiration_time:
                sessions_to_delete.append(session_id)

        # Ora elimina le sessioni scadute
        for session_id in sessions_to_delete:
            del global_sessions[session_id]
            print(f"Pulizia: Sessione {session_id} scaduta e rimossa.")
            
    print(f"Pulizia terminata. Sessioni attive: {len(global_sessions)}")

def background_cleanup_task():
    """
    Funzione eseguita in un thread separato che chiama
    la pulizia a intervalli regolari.
    """
    print("Avvio del thread di pulizia sessioni in background...")
    while True:
        try:
            time.sleep(CLEANUP_INTERVAL_SECONDS)
            cleanup_inactive_sessions()
        except Exception as e:
            print(f"Errore nel thread di pulizia: {e}")

# Avvia il thread di pulizia quando l'applicazione FastAPI parte
# 'daemon=True' assicura che il thread si chiuda quando il programma principale (FastAPI) si ferma
cleanup_thread = threading.Thread(target=background_cleanup_task, daemon=True)
cleanup_thread.start()