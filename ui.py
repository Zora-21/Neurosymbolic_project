import streamlit as st
import requests
import time
import uuid  # Importato per generare ID univoci

from app.config import API_BASE_URL

api_url = f"{API_BASE_URL}/chat"

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Clinica Virtuale Multi-Agente", page_icon="🏥", layout="wide")

st.title("🏥 Clinica Virtuale Multi-Agente")
st.caption("Descrivi i tuoi sintomi. Il sistema ti indirizzerà all'assistente specialista più adatto per approfondire.")

# --- DISCLAIMER ---
st.warning(
    "**Attenzione:** Sistema sperimentale AI. **Non è una diagnosi medica.** Consulta sempre un medico.",
    icon="⚠️"
)
st.divider()

# --- GESTIONE CRONOLOGIA CHAT ---

# *** MODIFICA: Gestione Session ID ***
# Genera un ID di sessione univoco per questo utente se non esiste già
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    print(f"Nuova Sessione UI creata: {st.session_state.session_id}")

# Usiamo 'chat_log' per la cronologia visualizzata nel frontend
if "chat_log" not in st.session_state:
    st.session_state.chat_log = [{
        "role": "assistant",
        "agent": "Router", # Agente iniziale
        "content": "Buongiorno! Sono l'assistente di smistamento. Descrivi brevemente i tuoi sintomi principali per indirizzarti allo specialista corretto."
    }]

# --- FUNZIONE PER RESETTARE LA CHAT ---
def reset_chat():
    current_session_id = st.session_state.get("session_id")
    try:
        # *** MODIFICA: Invia il session_id al backend per il reset ***
        if current_session_id:
            response = requests.post(
                f"{API_BASE_URL}/reset",
                json={"session_id": current_session_id} # Invia l'ID
            )
            response.raise_for_status()
            print(f"Stato backend resettato per la sessione: {current_session_id}")
        # *** FINE MODIFICA ***
    except Exception as e:
        st.error(f"Impossibile resettare lo stato del backend: {e}")
    
    # Resetta la cronologia nel frontend
    st.session_state.chat_log = [{
        "role": "assistant",
        "agent": "Router",
        "content": "Buongiorno! Sono l'assistente di smistamento. Descrivi brevemente i tuoi sintomi principali."
    }]
    # Genera un NUOVO session id per la nuova conversazione
    st.session_state.session_id = str(uuid.uuid4())
    # Ricarica l'interfaccia per mostrare lo stato resettato
    st.rerun()

# --- LAYOUT INTERFACCIA ---
# Colonna laterale per controlli opzionali
with st.sidebar:
    st.header("Opzioni")
    if st.button("🔄 Reset Conversazione", use_container_width=True):
        reset_chat()
    st.caption("Clicca qui per iniziare una nuova conversazione da zero.")

# Area principale della chat
chat_container = st.container()
with chat_container:
    # Mostra i messaggi della chat dalla cronologia di sessione
    for msg in st.session_state.chat_log:
        with st.chat_message(msg["role"]):
            agent_prefix = f"*{msg.get('agent', 'Assistente').capitalize()}:*\n" if msg["role"] == "assistant" else ""
            st.markdown(agent_prefix + msg["content"])

# Input utente in fondo
if prompt := st.chat_input("Scrivi qui il tuo messaggio..."):
    # Aggiungi messaggio utente alla cronologia locale e visualizzalo
    st.session_state.chat_log.append({"role": "user", "content": prompt})
    with chat_container: # Assicura che venga aggiunto nel container giusto
        with st.chat_message("user"):
            st.markdown(prompt)

    # Mostra messaggio di attesa e chiama l'API
    with chat_container:
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            message_placeholder.markdown("Sto pensando... 🤔")
            time.sleep(0.5)

            try:
                # *** MODIFICA: Invia il session_id al backend ***
                api_url = f"{API_BASE_URL}/chat"
                response = requests.post(
                    api_url, 
                    json={
                        "message": prompt,
                        "session_id": st.session_state.session_id # Invia l'ID di sessione
                    }
                )
                # *** FINE MODIFICA ***
                
                response.raise_for_status()
                data = response.json()

                agent_name = data.get("agent_type", "Assistente").capitalize()
                bot_response_content = data.get("response", "Nessuna risposta dal server.")

                # Mostra la risposta formattata
                agent_prefix_resp = f"*{agent_name}:*\n"
                message_placeholder.markdown(agent_prefix_resp + bot_response_content)

                # Aggiungi la risposta alla cronologia locale
                st.session_state.chat_log.append({
                    "role": "assistant",
                    "agent": agent_name,
                    "content": bot_response_content
                })

                # Se è la risposta finale (triage), mostra fonti se disponibili
                if data.get("is_final") and data.get("sources"):
                     st.expander("📄 Fonti consultate (nomi file)").write(data["sources"])

            except requests.exceptions.RequestException as e:
                error_content = f"Errore di comunicazione con il backend: {e}"
                message_placeholder.error(error_content)
                st.session_state.chat_log.append({"role": "assistant", "agent": "System", "content": error_content})
            except Exception as e:
                error_content = f"Errore imprevisto nell'interfaccia: {e}"
                message_placeholder.error(error_content)
                st.session_state.chat_log.append({"role": "assistant", "agent": "System", "content": error_content})