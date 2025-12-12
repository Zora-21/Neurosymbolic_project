import ollama
import json
import os
import numpy as np
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_chroma import Chroma
from sentence_transformers import CrossEncoder
from app.config import EMBEDDING_MODEL, RERANKER_MODEL
from app.logger import get_rag_logger

# Logger per questo modulo
logger = get_rag_logger()

class RAGHandler:
    def __init__(self, base_db_path: str):
        """
        Inizializza il gestore caricando embedding e reranker.
        """
        logger.info("Inizializzazione RAG Handler...")
        self.BASE_DB_PATH = base_db_path 
        
        # Modello per la ricerca vettoriale (multilingue)
        self.embedding_function = SentenceTransformerEmbeddings(
            model_name=EMBEDDING_MODEL,
            encode_kwargs={'normalize_embeddings': True}
        )
        
        # Modello per il Reranking (multilingue IT/ES/PT/EN)
        logger.info(f"Caricamento Reranker ({RERANKER_MODEL})...")
        self.reranker = CrossEncoder(RERANKER_MODEL)
        logger.info("Reranker caricato.")
        
        self.loaded_dbs = {}

    def _load_db(self, specialty: str):
        """Carica il DB vettoriale per una data specializzazione (se non già caricato)."""
        specialty = specialty.lower()
        if specialty not in self.loaded_dbs:
            db_path = os.path.join(self.BASE_DB_PATH, specialty)
            if not os.path.exists(db_path):
                logger.warning(f"Database vettoriale per '{specialty}' non trovato in '{db_path}'.")
                return None
            try:
                logger.info(f"Caricamento database vettoriale per '{specialty}'...")
                self.loaded_dbs[specialty] = Chroma(persist_directory=db_path, embedding_function=self.embedding_function)
                logger.info(f"Database per '{specialty}' caricato.")
            except Exception as e:
                logger.error(f"Errore durante il caricamento del DB per '{specialty}': {e}")
                return None
        return self.loaded_dbs[specialty]

    def get_potential_conditions(self, symptoms_query: str, specialty: str) -> dict:
        """
        Esegue la ricerca RAG nel DB con RERANKING.
        """
        db = self._load_db(specialty)
        if not db:
             return {"error": f"Database per la specializzazione '{specialty}' non disponibile."}

        logger.info(f"Ricerca Vettoriale in '{specialty}' per: '{symptoms_query}'")
        
        try:
            # --- FASE 1: RETRIEVAL (Setaccio Largo) ---
            # Recuperiamo più documenti per poi filtrarli con il reranker
            initial_docs = db.similarity_search_with_relevance_scores(symptoms_query, k=30)
            
            if not initial_docs:
                logger.info("Nessun documento trovato nella fase vettoriale.")
                return {"potential_conditions": []}

            # --- FASE 2: RERANKING (Filtro di Precisione) ---
            # Il reranker multilingue assegna un punteggio di rilevanza query-documento
            pairs = [(symptoms_query, doc.page_content) for doc, _ in initial_docs]
            rerank_scores = self.reranker.predict(pairs)
            
            # Ordina per score decrescente e prendi i top 10
            ranked_indices = np.argsort(rerank_scores)[::-1][:10]
            reranked_docs = [initial_docs[i][0] for i in ranked_indices]
            rerank_scores_sorted = [rerank_scores[i] for i in ranked_indices]

            logger.info(f"Top {len(reranked_docs)} documenti selezionati (Reranker attivo).")
            
            # --- DEBUG LOGGING ---
            logger.debug("DOCUMENTI DOPO RERANKING (TOP 5):")
            for i in range(min(5, len(reranked_docs))):
                doc = reranked_docs[i]
                score = rerank_scores_sorted[i]
                source = doc.metadata.get("source", "N/A")
                logger.debug(f"[{i+1}] RerankerScore: {score:.4f} | File: {os.path.basename(source)}")

            # Costruzione del contesto finale
            context = "\n\n---\n\n".join([d.page_content for d in reranked_docs])
            sources = list(set(d.metadata.get("source", "N/A") for d in reranked_docs))

        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"Errore CRITICO durante la ricerca '{specialty}': {e}")
            return {"error": f"Errore RAG: {e}"}
        
        # --- FASE 3: GENERAZIONE LLM (Invariata) ---
        
        system_prompt = f"""
        You are an expert medical analyst in the specialty '{specialty.upper()}'. 
        Analyze the USER SYMPTOMS and the MEDICAL CONTEXT (from scientific documents) to formulate hypotheses.

        OBJECTIVE:
        Identify possible pathologies compatible with the symptoms, based on the provided context.

        CRITICAL - USE COMMON DISEASE NAMES:
        Use well-known, standard medical terminology. Examples by specialty:
        - ALLERGOLOGO: "Allergic Rhinitis", "Food Allergy", "Urticaria", "Asthma"
        - CARDIOLOGO: "Hypertension", "Angina Pectoris", "Atrial Fibrillation", "Heart Failure"
        - DERMATOLOGO: "Psoriasis", "Atopic Dermatitis", "Melanoma"
        - ENDOCRINOLOGO: "Type 2 Diabetes", "Hypothyroidism", "Thyroid Nodule"
        - GASTROENTEROLOGO: "GERD", "Gastritis", "Irritable Bowel Syndrome"
        - PNEUMOLOGO: "Asthma", "COPD", "Pneumonia", "Chronic Bronchitis"
        - REUMATOLOGO: "Rheumatoid Arthritis", "Fibromyalgia", "Chronic Back Pain"
        
        DO NOT use overly specific or rare disease names unless the symptoms strongly suggest them.

        RULES:
        1. Use the MEDICAL CONTEXT as the primary source.
        2. The context may be in different languages (e.g., SPANISH). Mentally translate and extract relevant conditions in ENGLISH.
        3. PREFER COMMON CONDITIONS over rare ones when symptoms are ambiguous.
        4. IMPORTANT: NEVER return an empty list if symptoms are clear.
        5. If you don't find an exact match, return the most plausible conditions with "Low" probability.
        6. DO NOT INCLUDE fields like "status", "symptoms" or others. ONLY "potential_conditions".
        
        Return EXCLUSIVELY a valid JSON.
        DO NOT add text before or after the JSON.
        DO NOT use conversational markdown (e.g. "Here is the analysis...").
        ONLY THE PURE JSON.
        
        EXAMPLE OF CORRECT OUTPUT:
        {{
            "potential_conditions": [
                {{
                    "condition": "Rheumatoid Arthritis",
                    "probability": "High",
                    "reasoning": "Morning stiffness > 1 hour and bilateral hand pain match the description in document X...",
                    "treatment": "NSAIDs for pain relief, DMARDs (e.g., methotrexate) for disease modification, physical therapy"
                }},
                {{
                    "condition": "Osteoarthritis",
                    "probability": "Low",
                    "reasoning": "Missing systemic inflammatory component...",
                    "treatment": "Acetaminophen or NSAIDs, weight management, joint exercises"
                }}
            ]
        }}

        MANDATORY SCHEMA:
        {{
            "potential_conditions": [
                {{
                    "condition": "Condition Name",
                    "probability": "High/Medium/Low",
                    "reasoning": "Explanation based on text...",
                    "treatment": "Suggested therapy: medications, lifestyle changes, or specialist referral"
                }}
            ]
        }}

        MEDICAL CONTEXT ({specialty.upper()}):
        ---
        {context}
        ---
        """
        
        user_prompt = f"ANALYZE THE FOLLOWING SYMPTOMS AND IDENTIFY COMPATIBLE PATHOLOGIES: {symptoms_query}"

        # --- RETRY LOOP ---
        max_retries = 2
        for attempt in range(max_retries):
            try:
                logger.info(f"LLM Request (Tentativo {attempt+1}/{max_retries})...")
                response = ollama.chat(
                    model='llama3:8b',
                    messages=[{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': user_prompt}],
                    options={'temperature': 0.1},
                    format='json'
                )
                # Gestione robusta del parsing JSON
                content = response['message']['content']
                
                # A volte l'LLM include testo prima o dopo il JSON, cerchiamo le graffe
                start = content.find('{')
                end = content.rfind('}') + 1
                if start != -1 and end != -1:
                    analysis = json.loads(content[start:end])
                else:
                    analysis = json.loads(content)

                # VALIDAZIONE SCHEMA
                # Supporto per LLM che wrappano la risposta in "analysis" o "response"
                if "potential_conditions" not in analysis:
                    for key in ["analysis", "response", "result", "output"]:
                        if key in analysis:
                            content_to_check = analysis[key]
                            
                            # Caso 0: Il contenuto è una STRINGA che contiene JSON (es. "{\"potential_conditions\": ...}")
                            if isinstance(content_to_check, str):
                                try:
                                    # Tentiamo di pulire la stringa da eventuali markdown
                                    clean_str = content_to_check.replace("```json", "").replace("```", "").strip()
                                    parsed_inner = json.loads(clean_str)
                                    if isinstance(parsed_inner, dict) and "potential_conditions" in parsed_inner:
                                        analysis = parsed_inner
                                        break
                                    elif isinstance(parsed_inner, list):
                                        analysis = {"potential_conditions": parsed_inner}
                                        break
                                except:
                                    # If JSON parsing fails, it might be a conversational string (Summary)
                                    # Raise exception to trigger retry
                                    raise ValueError(f"LLM returned a string instead of JSON: {content_to_check[:50]}...")

                            # Caso 1: Wrapper contiene un altro oggetto con "potential_conditions"
                            if isinstance(content_to_check, dict):
                                if "potential_conditions" in content_to_check:
                                    analysis = content_to_check
                                    break
                                # Fallback per chiavi simili (es. "conditions", "diagnoses")
                                for alt_key in ["conditions", "diagnoses", "diseases"]:
                                    if alt_key in content_to_check and isinstance(content_to_check[alt_key], list):
                                        analysis = {"potential_conditions": content_to_check[alt_key]}
                                        break
                            
                            # Caso 2: Wrapper contiene DIRETTAMENTE la lista
                            elif isinstance(content_to_check, list):
                                analysis = {"potential_conditions": content_to_check}
                                break
                
                if "potential_conditions" not in analysis or not isinstance(analysis["potential_conditions"], list):
                    # If we are here, JSON is valid but structure is wrong.
                    # We can try to retry if it's the first attempt
                    if attempt < max_retries - 1:
                         raise ValueError(f"Valid JSON but wrong structure. Keys: {list(analysis.keys())}")
                    
                    logger.warning(f"Invalid LLM JSON Format. Keys: {list(analysis.keys())}")
                    logger.debug(f"Received content: {analysis}")
                    analysis = {"potential_conditions": []}

                # PULIZIA: Rimuovi elementi non-dict dalla lista (es. stringhe spurie)
                if "potential_conditions" in analysis and isinstance(analysis["potential_conditions"], list):
                    cleaned_conditions = [
                        item for item in analysis["potential_conditions"]
                        if isinstance(item, dict) and "condition" in item
                    ]
                    if len(cleaned_conditions) < len(analysis["potential_conditions"]):
                        logger.warning(f"Rimossi {len(analysis['potential_conditions']) - len(cleaned_conditions)} elementi non validi da potential_conditions")
                    analysis["potential_conditions"] = cleaned_conditions

                analysis["sources_consulted"] = sources
                return analysis
                
            except Exception as e:
                logger.warning(f"Error attempt {attempt+1}: {e}")
                if attempt < max_retries - 1:
                    # Add error message to user prompt for next attempt
                    user_prompt += f"\n\nPREVIOUS ERROR: You returned an invalid format ({str(e)}). YOU MUST return ONLY a valid JSON with the key 'potential_conditions'."
                else:
                    logger.error(f"LLM Error for '{specialty}' after {max_retries} attempts.")
                    return {"error": f"LLM Analysis Error: {e}", "potential_conditions": []}