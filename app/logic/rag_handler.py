import ollama
import json
import os
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_chroma import Chroma
from app.config import EMBEDDING_MODEL

BASE_DB_PATH = "vector_dbs" # Cartella base dei DB vettoriali
model_name=EMBEDDING_MODEL

class RAGHandler:
    # Modifica l'init per ACCETTARE il percorso
    def __init__(self, base_db_path: str):
        """
        Inizializza il gestore caricando la funzione di embedding.
        """
        print("Inizializzazione RAG Handler...")
        # Salva il percorso corretto
        self.BASE_DB_PATH = base_db_path 
        self.embedding_function = SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")
        self.loaded_dbs = {}

    def _load_db(self, specialty: str):
        """Carica il DB vettoriale per una data specializzazione (se non già caricato)."""
        specialty = specialty.lower()
        if specialty not in self.loaded_dbs:
            # Usa il percorso iniettato
            db_path = os.path.join(self.BASE_DB_PATH, specialty)
            if not os.path.exists(db_path):
                print(f"⚠️ Attenzione: Database vettoriale per '{specialty}' non trovato in '{db_path}'. La ricerca RAG fallirà.")
                return None
            try:
                print(f"Caricamento database vettoriale per '{specialty}'...")
                self.loaded_dbs[specialty] = Chroma(persist_directory=db_path, embedding_function=self.embedding_function)
                print(f"Database per '{specialty}' caricato.")
            except Exception as e:
                print(f"❌ Errore durante il caricamento del DB per '{specialty}': {e}")
                return None
        return self.loaded_dbs[specialty]

    def get_potential_conditions(self, symptoms_query: str, specialty: str) -> dict:
        """
        Esegue la ricerca RAG nel DB della specializzazione specificata
        e chiede all'LLM di identificare possibili condizioni.
        """
        db = self._load_db(specialty)
        if not db:
             return {"error": f"Database per la specializzazione '{specialty}' non disponibile."}

        print(f"Recupero contesto da '{specialty}' per query: '{symptoms_query}'")
        try:
            # Recupera documenti E i loro metadati (che contengono 'source')
            retrieved_docs = db.similarity_search_with_relevance_scores(symptoms_query, k=4)
            
            # Filtra per relevance score se necessario (es. > 0.7)
            # retrieved_docs = [doc for doc, score in retrieved_docs_with_scores if score > 0.7]

            context = "\n\n---\n\n".join([doc.page_content for doc, score in retrieved_docs])
            sources = list(set(doc.metadata.get("source", "N/A") for doc, score in retrieved_docs)) # Elenco univoco delle fonti usate

            if not context:
                 print(f"Nessun contesto rilevante trovato in '{specialty}' per la query.")
                 return {"potential_conditions": []} # Restituisce lista vuota se non trova nulla

        except Exception as e:
            print(f"❌ Errore durante la ricerca nel DB '{specialty}': {e}")
            return {"error": f"Errore nella ricerca RAG per {specialty}."}
        
        system_prompt = f"""
        Sei un esperto analista medico della specializzazione '{specialty.upper()}'. Il tuo compito è analizzare i SINTOMI DELL'UTENTE forniti e vedere se trovano riscontro nel CONTESTO MEDICO.

        DEVI SEGUIRE QUESTE REGOLE SCRUPOLOSAMENTE:
        1.  Leggi prima i SINTOMI DELL'UTENTE.
        2.  Leggi il CONTESTO MEDICO e cerca SOLO condizioni che corrispondano ai sintomi dell'utente (es. "tosse grassa", "febbre").
        3.  Se il contesto parla di sintomi diversi (es. "ginocchio" quando l'utente ha "polso"), DEVI IGNORARE quelle parti del contesto.
        4.  Formula ipotesi SOLO se trovi una corrispondenza diretta tra i sintomi dell'utente e il contesto.

        Restituisci la tua analisi ESCLUSIVAMENTE in formato JSON con una chiave "potential_conditions",
        che è una lista di oggetti. Ogni oggetto DEVE avere:
        - "condition": Nome della condizione.
        - "probability": Probabilità ("Alta", "Media", "Bassa").
        - "reasoning": Spiegazione (max 2 frasi) basata sul contesto che spiega come i sintomi dell'utente corrispondono.

        Se non trovi condizioni PERTINENTI ai sintomi specifici dell'utente nel contesto, restituisci una lista vuota: {{"potential_conditions": []}}.

        CONTESTO MEDICO FORNITO ({specialty.upper()}):
        ---
        {context}
        ---
        """
        user_prompt = f"SINTOMI DELL'UTENTE: {symptoms_query}"

        # --- FINE BLOCCO SOSTITUITO ---

        try:
            response = ollama.chat(
                model='llama3:8b',
                messages=[{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': user_prompt}],
                options={'temperature': 0.1},
                format='json'
            )
            analysis = json.loads(response['message']['content'])
            # Aggiungi le fonti all'analisi per riferimento (opzionale ma utile)
            analysis["sources_consulted"] = sources
            return analysis
        except Exception as e:
            print(f"❌ Errore durante l'analisi RAG LLM per '{specialty}': {e}")
            return {"error": f"Errore LLM durante l'analisi RAG per {specialty}."}