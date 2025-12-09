# Sistema di Triage Multi-Agente Neurosymbolico

Sistema di triage medico conversazionale basato su LLM con architettura multi-agente e approccio neurosimbolico.

## Struttura Essenziale

```
progetto-neurosymbolic/
│
├── app/                          # Core dell'applicazione
│   ├── main.py                   # Backend FastAPI + routing
│   ├── translations.py           # Prompt e traduzioni IT/EN
│   ├── agents/                   # Agenti del sistema
│   │   ├── router_agent.py       # Smista al specialista corretto
│   │   ├── specialist_agent.py   # Analisi specialistica + RAG
│   │   └── assistant_agent.py    # Estrae dati paziente
│   ├── logic/                    # Logica di supporto
│   │   ├── rag_handler.py        # Retrieval Augmented Generation
│   │   ├── session_manager.py    # Gestione sessioni
│   │   └── symbolic_engine.py    # Regole simboliche
│   └── tools/
│       └── medical_calculators.py # Calcolatori clinici
│
├── vector_dbs/                   # Database vettoriali (1 per specialista)
├── documenti_medici/             # Documenti sorgente per RAG
│
├── test_1/                       # Test Suite V1 (33 casi)
│   └── test_cases.py
├── test_2/                       # Test Suite V2 (55 casi)
│   └── test_cases_v2.py
├── test_3/                       # Test Suite V3 (33 casi)
│   └── test_cases_v3.py
│
├── ui.py                         # Frontend Streamlit
├── create_vector_store.py        # Script per creare vector DB
└── requirements.txt              # Dipendenze Python
```

## Avvio

```bash
# 1. Avvia LLM locale
ollama run llama3:8b

# 2. Avvia backend
uvicorn app.main:app --reload

# 3. Avvia frontend (opzionale)
streamlit run ui.py
```

## Test

```bash
# Esegui un singolo caso
python test_1/test_cases.py 5

# Esegui tutti i casi (modifica CASES_TO_RUN nel file)
python test_1/test_cases.py
```

## Specialisti Disponibili

| Specialista      | Stato |
|------------------|-------|
| Allergologo      | ✓     |
| Cardiologo       | ✓     |
| Dermatologo      | ✓     |
| Ematologo        | ✓     |
| Endocrinologo    | ✓     |
| Gastroenterologo | ✓     |
| Geriatra         | ✓     |
| Infettivologo    | ✓     |
| Nefrologo        | ✓     |
| Pneumologo       | ✓     |
| Reumatologo      | ✓     |