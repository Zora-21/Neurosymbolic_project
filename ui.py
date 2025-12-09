import streamlit as st
import requests
import time
import uuid
from app.config import API_BASE_URL

# Configurazione Pagina
st.set_page_config(page_title="Clinica Virtuale Multi-Agente", page_icon="🏥", layout="wide")
st.title("🏥 Clinica Virtuale AI")

# --- GESTIONE SESSIONE ---
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    print(f"🖥️ Nuova Sessione UI: {st.session_state.session_id}")

if "chat_log" not in st.session_state:
    st.session_state.chat_log = [{
        "role": "assistant",
        "agent": "System",
        "content": "Benvenuto. Descrivi i tuoi sintomi per iniziare."
    }]

import base64

# --- SIDEBAR ---
with st.sidebar:
    st.header("Controlli")
    if st.button("🗑️ Reset Conversazione"):
        try:
            # Chiamata all'endpoint di reset del backend
            requests.post(f"{API_BASE_URL}/reset", json={"session_id": st.session_state.session_id})
        except Exception:
            pass
        # Genera nuovo ID e pulisce UI
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.chat_log = []
        st.rerun()
    
    st.divider()
    st.header("Allegati")
    uploaded_file = st.file_uploader("Carica una foto medica", type=["jpg", "png", "jpeg"])
    
    image_base64 = None
    if uploaded_file is not None:
        st.image(uploaded_file, caption="Immagine caricata", use_column_width=True)
        # Converti in base64
        bytes_data = uploaded_file.getvalue()
        image_base64 = base64.b64encode(bytes_data).decode('utf-8')

# --- LAYOUT A DUE COLONNE ---
col_chat, col_info = st.columns([2, 1])

# --- COLONNA SINISTRA: CHAT ---
with col_chat:
    chat_container = st.container()
    
    # Renderizza messaggi
    with chat_container:
        for msg in st.session_state.chat_log:
            with st.chat_message(msg["role"]):
                prefix = ""
                if msg["role"] == "assistant" and "agent" in msg:
                    prefix = f"**{msg['agent'].capitalize()}**: "
                st.markdown(prefix + msg["content"])

    # Input Utente
    if prompt := st.chat_input("Descrivi qui i tuoi sintomi..."):
        # 1. Mostra subito messaggio utente
        st.session_state.chat_log.append({"role": "user", "content": prompt})
        with chat_container:
            with st.chat_message("user"):
                st.markdown(prompt)
                if image_base64:
                    st.info("📸 Immagine inviata per analisi.")

        # 2. Chiama il Backend
        with chat_container:
            with st.chat_message("assistant"):
                placeholder = st.empty()
                placeholder.markdown("⏳ *Analisi in corso...*")
                
                try:
                    payload = {
                        "message": prompt,
                        "session_id": st.session_state.session_id
                    }
                    # Gestione invio immagine (solo se nuova)
                    should_mark_processed = False
                    image_id_to_mark = None

                    if image_base64:
                        # Identificativo univoco per l'immagine corrente
                        image_id = f"{uploaded_file.name}_{uploaded_file.size}"
                        
                        if "processed_images" not in st.session_state:
                            st.session_state.processed_images = set()
                        
                        if image_id not in st.session_state.processed_images:
                            payload["image_data"] = image_base64
                            should_mark_processed = True
                            image_id_to_mark = image_id
                        else:
                            print(f"ℹ️ Immagine '{uploaded_file.name}' già analizzata. Salto invio dati.")

                    response = requests.post(
                        f"{API_BASE_URL}/chat",
                        json=payload
                    )
                    response.raise_for_status()
                    data = response.json()

                    # Se l'invio è andato a buon fine, segniamo l'immagine come processata
                    if should_mark_processed and image_id_to_mark:
                        st.session_state.processed_images.add(image_id_to_mark)

                    # Estrai dati
                    text_response = data.get("response", "Errore.")
                    agent_name = data.get("agent_type", "AI")
                    extracted_info = data.get("extracted_info", {}) # Nuovi dati estratti
                    extra_messages = data.get("extra_messages", []) # Messaggi extra (es. transizioni)
                    
                    # Aggiorna stato per il pannello laterale
                    st.session_state["current_agent"] = agent_name
                    st.session_state["extracted_info"] = extracted_info

                    # 1. Renderizza eventuali messaggi extra (es. Router)
                    # Costruiamo la lista completa dei messaggi da mostrare in questo turno
                    messages_to_render = []
                    
                    # 1. Messaggi Extra (es. Router)
                    if extra_messages:
                        for msg in extra_messages:
                            messages_to_render.append({
                                "role": msg["role"],
                                "agent": msg.get("agent", "System"),
                                "content": msg["content"]
                            })
                            # Aggiungiamo anche alla storia
                            st.session_state.chat_log.append(msg)

                    # 2. Risposta Finale (es. Specialista)
                    messages_to_render.append({
                        "role": "assistant",
                        "agent": agent_name,
                        "content": text_response
                    })
                    st.session_state.chat_log.append({
                        "role": "assistant",
                        "agent": agent_name,
                        "content": text_response
                    })

                    # RENDERIZZAZIONE ORDINATA
                    # Il primo messaggio usa il placeholder esistente (che è in cima)
                    if messages_to_render:
                        first_msg = messages_to_render[0]
                        formatted_first = f"**{first_msg['agent'].capitalize()}**: {first_msg['content']}"
                        placeholder.markdown(formatted_first)
                        
                        # I successivi vengono appesi sotto
                        for msg in messages_to_render[1:]:
                            with chat_container:
                                with st.chat_message(msg["role"]):
                                    prefix = f"**{msg['agent'].capitalize()}**: "
                                    st.markdown(prefix + msg["content"])
                    
                    if data.get("is_final"):
                        st.success("Sessione conclusa. La chat verrà resettata al prossimo messaggio.")
                        st.session_state.session_id = str(uuid.uuid4())
                        # Reset dati laterali
                        st.session_state["extracted_info"] = {}

                except Exception as e:
                    placeholder.error(f"Errore di connessione: {e}")

# --- COLONNA DESTRA: PANNELLO MEDICO ---
with col_info:
    st.markdown("### 📋 Cartella Clinica")
    st.divider()
    
    # 1. Agente Attivo
    current_agent = st.session_state.get("current_agent", "Router")
    st.info(f"👨‍⚕️ **Specialista Attivo**:\n\n{current_agent.capitalize()}")
    
    # 2. Immagine Caricata (se presente)
    if image_base64:
        st.markdown("#### 📸 Reperti Visivi")
        st.image(uploaded_file, caption="Immagine Utente", use_column_width=True)
        st.divider()

    # 3. Dati Vitali Estratti
    extracted = st.session_state.get("extracted_info", {})
    if extracted:
        st.markdown("#### 📊 Parametri Rilevati")
        
        # Mappatura chiavi -> etichette leggibili
        labels = {
            "temperatura_celsius": "Temperatura (°C)",
            "pain_score": "Livello Dolore (0-10)",
            "systolic": "Pressione Sistolica",
            "diastolic": "Pressione Diastolica",
            "heart_rate": "Battito Cardiaco"
        }
        
        for key, value in extracted.items():
            label = labels.get(key, key.replace("_", " ").capitalize())
            st.metric(label=label, value=value)
    else:
        st.caption("Nessun parametro vitale rilevato al momento.")