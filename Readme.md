progetto-neurosymbolic/
|
├── venv/                   # La cartella dell'ambiente virtuale (già creata)
|
├── app/                    # Qui vivrà la logica principale della nostra applicazione
│   ├── __init__.py         # File vuoto, rende 'app' un modulo Python
│   ├── main.py             # Il file principale del nostro backend FastAPI
│   ├── config.py
│   ├── tools/              
│   │   └── medical_calculators.py
│   ├── logic/              # Cartella per la logica neurosimbolica
│   │   ├── __init__.py
│   │   ├── llm_extractor.py # Modulo per estrarre info con l'LLM
│   │   ├── conversional_agent.py
│   │   ├── rag_handler.py
│   │   └── symbolic_engine.py # Modulo per le regole e la KB
│   └── data/
│       └── knowledge_base.json # La nostra base di conoscenza
|
├── documenti_medici/
│       ├── (documenti per ogni specializzazione)
│       └── ...
├── vectors_dbs/
│       ├── (db per ogni specializzazione)
│       └── ...
│
├── ui.py                   # Il nostro frontend con Streamlit
│
├── create_vector_store.py
|
└── .gitignore              # Un file per dire a Git cosa ignorare



1) ollama run llama3:8b        
2) uvicorn app.main:app --reload   
3) streamlit run ui.py