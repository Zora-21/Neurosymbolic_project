import os
import shutil
import argparse # Per accettare argomenti da linea di comando
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_chroma import Chroma

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = SCRIPT_DIR # Dato che è già nella root

BASE_DOCS_PATH = os.path.join(PROJECT_ROOT, "documenti_medici")
BASE_DB_PATH = os.path.join(PROJECT_ROOT, "vector_dbs")

def create_specialist_vector_store(specialty: str):
    """
    Crea o ricrea il database vettoriale per una specifica specializzazione medica.
    """
    docs_path = os.path.join(BASE_DOCS_PATH, specialty)
    db_path = os.path.join(BASE_DB_PATH, specialty)

    if not os.path.exists(docs_path):
        print(f"Errore: La cartella dei documenti per '{specialty}' non esiste: '{docs_path}'")
        return

    # Rimuove il DB esistente per questa specialità per ricrearlo
    if os.path.exists(db_path):
        print(f"Rimuovo il database esistente per '{specialty}' in '{db_path}'...")
        shutil.rmtree(db_path)

    all_docs = []
    pdf_files = [f for f in os.listdir(docs_path) if f.endswith('.pdf')]
    if not pdf_files:
        print(f"Nessun file PDF trovato per '{specialty}' in '{docs_path}'.")
        # Crea comunque la cartella del DB vuota se non ci sono file
        os.makedirs(db_path, exist_ok=True)
        print(f"Cartella DB vuota creata per '{specialty}' in '{db_path}'.")
        return

    print(f"Caricamento di {len(pdf_files)} file PDF per '{specialty}'...")
    for pdf_file in pdf_files:
        try:
            loader = PyPDFLoader(os.path.join(docs_path, pdf_file))
            loaded_docs = loader.load()
            # Aggiungi metadati per sapere da quale file proviene il chunk
            for doc in loaded_docs:
                doc.metadata["source"] = pdf_file
            all_docs.extend(loaded_docs)
        except Exception as e:
            print(f"Errore durante il caricamento di {pdf_file}: {e}")
            continue # Salta il file problematico

    if not all_docs:
        print(f"Nessun documento caricato con successo per '{specialty}'.")
        return

    print("Suddivisione dei documenti in chunk...")
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = text_splitter.split_documents(all_docs)

    print("Creazione degli embedding e del Vector Store...")
    embedding_function = SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")

    try:
        db = Chroma.from_documents(
            chunks,
            embedding_function,
            persist_directory=db_path
        )
        print(f"✅ Database vettoriale per '{specialty}' creato con successo in '{db_path}'.")
    except Exception as e:
         print(f"❌ Errore durante la creazione del DB per '{specialty}': {e}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Crea un database vettoriale per una specializzazione medica.")
    parser.add_argument("specialty", type=str, help="Nome della specializzazione (deve corrispondere a una sottocartella in 'documenti'). Es: 'cardiologia'")
    
    args = parser.parse_args()
    
    # Crea la cartella base per i DB se non esiste
    os.makedirs(BASE_DB_PATH, exist_ok=True)
    
    create_specialist_vector_store(args.specialty.lower()) # Usa lowercase per coerenza