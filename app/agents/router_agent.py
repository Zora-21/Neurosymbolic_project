import ollama
import json

class RouterAgent:
    def __init__(self, available_specialists: list):
        """
        Inizializza l'agente Router.
        :param available_specialists: Lista delle specializzazioni disponibili (es. ['cardiologia', 'dermatologia']).
                                      I nomi devono corrispondere esattamente alle cartelle in 'vector_dbs'.
        """
        # Assicura che la lista interna sia sempre in minuscolo per i confronti
        self.specialists = [s.lower() for s in available_specialists]
        specialist_list_str = ", ".join(self.specialists) # Stringa esatta per il prompt

        self.system_prompt = f"""
        Sei un assistente medico di smistamento (Router). Il tuo compito è capire, dalla conversazione con l'utente,
        quale specialista medico è più appropriato.

        Le specializzazioni disponibili sono ESATTAMENTE le seguenti (usa uno di questi nomi in minuscolo): {specialist_list_str}.

        Dialoga brevemente con l'utente (massimo 1-2 domande GENERALI) solo se strettamente necessario per identificare l'area problematica principale.
        Appena hai un'idea chiara, DEVI scegliere uno degli specialisti dalla lista fornita.

        La tua risposta DEVE essere un oggetto JSON con una delle seguenti azioni:
        1.  Se hai bisogno di UNA SOLA domanda generale di chiarimento:
            ```json
            {{
              "action": "ask_general_followup",
              "question": "La tua domanda generale."
            }}
            ```
        2.  Se hai identificato lo specialista:
            ```json
            {{
              "action": "route_to_specialist",
              "specialist": "nome_dello_specialista_scelto_in_minuscolo", // DEVE essere uno tra: {specialist_list_str}
              "summary": "Breve riassunto dei sintomi chiave per lo specialista."
            }}
            ```
        3.  Se i sintomi non corrispondono chiaramente a nessuno specialista disponibile:
             ```json
            {{
              "action": "cannot_route",
              "message": "Messaggio per l'utente che spiega che non c'è uno specialista adatto disponibile."
            }}
            ```
        Rispondi SOLO con l'oggetto JSON. Non aggiungere altro testo. Sii rapido nello scegliere lo specialista ESATTO dalla lista.
        """

    def decide_routing(self, chat_history: list) -> dict:
        """
        Analizza la cronologia e decide se chiedere ancora o instradare.
        """
        messages = [{'role': 'system', 'content': self.system_prompt}]
        # Considera solo gli ultimi messaggi per efficienza e contesto
        messages.extend(chat_history[-4:])

        try:
            response = ollama.chat(model='llama3:8b', messages=messages, format='json')
            decision = json.loads(response['message']['content'])

            # Validazione più robusta dell'output
            action = decision.get("action")

            if action == "route_to_specialist":
                specialist_raw = decision.get("specialist", "") # Nome restituito dall'LLM
                specialist = specialist_raw.lower().strip() # Converti in minuscolo e rimuovi spazi extra

                # --- RIGA DI DEBUG ---
                print(f"DEBUG Router: LLM ha scelto='{specialist_raw}' -> (processato: '{specialist}'). Lista attesa: {self.specialists}")
                # ---------------------

                # Controlla se lo specialista scelto è valido E presente nella lista
                if not specialist or specialist not in self.specialists:
                    print(f"⚠️ Router ha scelto uno specialista non valido o non disponibile: '{specialist_raw}'. Provo cannot_route.")
                    # Messaggio di errore più informativo per l'utente
                    available_list_str = ", ".join(s.capitalize() for s in self.specialists) # Lista leggibile
                    return {"action": "cannot_route", "message": f"Non sono riuscito a identificare uno specialista valido tra quelli disponibili ({available_list_str}) per '{specialist_raw}'. Potresti descrivere il problema in modo diverso?"}
                # Se valido, la decisione è corretta
                decision["specialist"] = specialist # Assicura che sia minuscolo nella decisione restituita
            
            elif action == "ask_general_followup":
                if not decision.get("question"):
                    print(f"⚠️ Router ha scelto 'ask_general_followup' ma manca la domanda. Provo cannot_route.")
                    return {"action": "cannot_route", "message": "Ho avuto difficoltà a formulare una domanda di chiarimento."}
            
            elif action == "cannot_route":
                 if not decision.get("message"):
                     decision["message"] = "Non sono sicuro di quale specialista sia più adatto in base alla descrizione." # Messaggio di default
            
            else: # Azione non riconosciuta
                 print(f"⚠️ Router ha restituito un'azione JSON non valida: '{action}'. Provo cannot_route.")
                 return {"action": "cannot_route", "message": "Ho avuto difficoltà a interpretare la richiesta. Potresti riprovare?"}

            # Se tutto ok, restituisce la decisione validata
            print(f"🤖 Router Decision: {decision}")
            return decision

        except json.JSONDecodeError:
             print(f"❌ Errore JSON nel Router Agent. Risposta LLM: {response['message']['content']}")
             return {"action": "cannot_route", "message": "Si è verificato un problema tecnico (JSON invalido). Riprova a descrivere i sintomi."}
        except Exception as e:
            print(f"❌ Errore generico nel Router Agent: {e}")
            return {"action": "cannot_route", "message": f"Si è verificato un problema tecnico durante lo smistamento: {e}"}