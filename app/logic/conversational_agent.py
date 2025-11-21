import ollama
import json

class ConversationalAgent:
    def __init__(self, triage_handler_func):
        """
        Inizializza l'agente.
        :param triage_handler_func: La funzione da chiamare quando si decide di eseguire il triage.
        """
        self.triage_handler = triage_handler_func
        self.system_prompt = """
        Sei un assistente medico empatico e professionale, specializzato nel triage.
        Il tuo obiettivo è dialogare con l'utente per raccogliere informazioni sui suoi sintomi.

        Analizza la cronologia della conversazione e decidi l'azione successiva:
        1.  Se le informazioni sono insufficienti, fai UNA SOLA domanda di approfondimento, chiara e pertinente. Chiedi dettagli come: durata, intensità del dolore (es. da 1 a 10), sintomi associati, ecc.
        2.  Se ritieni di avere abbastanza informazioni per un'analisi (solitamente dopo 2-4 scambi), rispondi ESATTAMENTE con il seguente comando JSON e nient'altro:
            ```json
            {
              "action": "triage",
              "summary": "Riassunto conciso di tutti i sintomi, durata e dettagli emersi nella conversazione."
            }
            ```

        NON eseguire mai la diagnosi tu stesso. Il tuo unico compito è decidere se chiedere di più o se attivare il triage.
        Sii conciso e amichevole.
        """

    def get_next_response(self, chat_history: list) -> dict:
        """
        Data la cronologia della chat, decide se fare un'altra domanda o avviare il triage.
        """
        messages = [{'role': 'system', 'content': self.system_prompt}]
        messages.extend(chat_history)

        try:
            # Chiama l'LLM per ottenere la prossima azione
            response = ollama.chat(model='llama3:8b', messages=messages)
            llm_output = response['message']['content'].strip()

            # Prova a interpretare l'output come un comando JSON per il triage
            try:
                # Cerca il blocco JSON nell'output, a volte l'LLM aggiunge testo extra
                json_block_start = llm_output.find('{')
                json_block_end = llm_output.rfind('}') + 1
                if json_block_start != -1 and json_block_end != -1:
                    json_command_str = llm_output[json_block_start:json_block_end]
                    command = json.loads(json_command_str)
                    
                    if command.get("action") == "triage":
                        print(f"🤖 Agente ha deciso di eseguire il triage. Riepilogo: {command['summary']}")
                        # Chiama la funzione di triage passata durante l'inizializzazione
                        return self.triage_handler(command['summary'])
                
                # Se non è un comando JSON valido, trattalo come una domanda di follow-up
                print(f"🤖 Agente ha generato una domanda di follow-up: {llm_output}")
                return {"type": "question", "content": llm_output}

            except (json.JSONDecodeError, KeyError):
                # Se il parsing fallisce, è una semplice domanda
                print(f"🤖 Agente ha generato una domanda di follow-up: {llm_output}")
                return {"type": "question", "content": llm_output}

        except Exception as e:
            print(f"❌ Errore nell'agente conversazionale: {e}")
            return {"type": "error", "content": "Mi dispiace, si è verificato un problema tecnico."}
