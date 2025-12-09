import ollama
import base64
import io
from PIL import Image
from app.logger import get_rag_logger

# Logger per questo modulo
logger = get_rag_logger()

class ImageAnalyzer:
    def __init__(self, model_name="llava", language="Italian"):
        self.model_name = model_name
        self.language = language

    def analyze_image(self, image_base64: str) -> str:
        """
        Analizza un'immagine codificata in base64 usando un modello Vision (es. LLaVA).
        Restituisce una descrizione testuale dettagliata dei reperti visivi.
        """
        logger.info(f"ImageAnalyzer: Analisi immagine in corso con {self.model_name}...")
        
        # --- OTTIMIZZAZIONE: Ridimensiona immagine se troppo grande ---
        try:
            image_data = base64.b64decode(image_base64)
            image = Image.open(io.BytesIO(image_data))
            
            # Ridimensiona se lato maggiore > 1024px
            max_size = 1024
            if max(image.size) > max_size:
                logger.info(f"Ridimensionamento immagine da {image.size} a max {max_size}px...")
                image.thumbnail((max_size, max_size))
                
                # Ricodifica in base64
                buffered = io.BytesIO()
                image.save(buffered, format="JPEG", quality=85)
                image_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        except Exception as e:
            logger.warning(f"Errore durante il ridimensionamento immagine: {e}")
            # Continua con l'originale se fallisce il resize

        prompt = f"""
        Sei un assistente medico esperto in analisi visiva.
        Descrivi DETTAGLIATAMENTE cosa vedi in questa immagine medica.
        Concentrati su:
        1. Tipo di lesione o anomalia visibile.
        2. Colore, forma, dimensioni approssimative.
        3. Presenza di gonfiore, arrossamento o secrezioni.
        
        Rispondi in {self.language.upper()}. Sii conciso e oggettivo.
        Inizia con: "Dall'analisi dell'immagine rilevo: ..."
        """

        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[
                    {
                        'role': 'user',
                        'content': prompt,
                        'images': [image_base64]
                    }
                ],
                options={
                    "temperature": 0.0, # Più deterministico
                    "num_ctx": 2048     # Limita contesto per risparmiare RAM
                }
            )
            description = response['message']['content']
            logger.info("Analisi completata.")
            return description

        except Exception as e:
            logger.error(f"Errore ImageAnalyzer: {e}")
            return "Impossibile analizzare l'immagine. Assicurati che Ollama sia attivo e abbia risorse sufficienti."
