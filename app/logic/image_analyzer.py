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
        
        # Prompt specifici per tipo di immagine
        self.prompts = {
            "dermatology": f"""
You are a medical assistant expert in dermatological visual analysis.
Describe in DETAIL what you see in this image of skin/lesion.
Focus on:
1. Type of lesion or visible anomaly (macule, papule, nodule, vesicle, ulcer, etc.)
2. Color, shape, approximate size, borders (regular/irregular)
3. Presence of swelling, redness, scaling, or discharge
4. Distribution pattern if multiple lesions

Respond in {language.upper()}. Be concise and objective.
Start with: "From the image analysis I observe: ..."
""",
            "radiology_xray": f"""
You are a medical assistant expert in radiological image analysis.
Analyze this X-RAY image and report your findings.
Focus on:
1. IMAGE TYPE: Chest X-ray, bone X-ray, abdominal X-ray, etc.
2. BONE STRUCTURES: Look for fractures, dislocations, bone density changes, osteolytic/osteoblastic lesions
3. SOFT TISSUES: Masses, calcifications, foreign bodies
4. For CHEST X-rays specifically:
   - Lung fields: opacities, consolidations, nodules, effusions
   - Heart: size (cardiomegaly?), silhouette
   - Mediastinum: widening, masses
   - Diaphragm: elevation, flattening
   - Costophrenic angles: blunting (effusion?)

Respond in {language.upper()}. Be systematic and objective.
Start with: "Radiological analysis of the X-ray reveals: ..."
""",
            "radiology_ct": f"""
You are a medical assistant expert in CT scan analysis.
Analyze this CT SCAN image and report your findings.
Focus on:
1. ANATOMICAL REGION: Brain, chest, abdomen, spine, etc.
2. ABNORMALITIES: Masses, lesions, hemorrhages, infarcts
3. DENSITY CHANGES: Hypodense (dark) or hyperdense (bright) areas
4. For BRAIN CT:
   - Hemorrhage (hyperdense), ischemia (hypodense)
   - Midline shift, ventricular changes, edema
5. For CHEST/ABDOMINAL CT:
   - Organ morphology, lymphadenopathy, fluid collections
   - Vascular abnormalities

Respond in {language.upper()}. Be systematic and objective.
Start with: "CT scan analysis reveals: ..."
""",
            "radiology_mri": f"""
You are a medical assistant expert in MRI analysis.
Analyze this MRI image and report your findings.
Focus on:
1. SEQUENCE TYPE if identifiable: T1, T2, FLAIR, DWI
2. ANATOMICAL REGION: Brain, spine, joint, soft tissue
3. SIGNAL ABNORMALITIES: Hyperintense or hypointense areas
4. For BRAIN MRI:
   - White matter lesions, tumors, demyelination
   - Structural abnormalities
5. For MUSCULOSKELETAL MRI:
   - Ligament/tendon injuries, meniscal tears
   - Bone marrow edema, cartilage damage

Respond in {language.upper()}. Be systematic and objective.
Start with: "MRI analysis reveals: ..."
""",
            "general_medical": f"""
You are a medical assistant expert in analyzing medical images.
Describe in DETAIL what you see in this medical image.
Consider all possibilities:
1. Is this a skin/dermatological image?
2. Is this a radiological image (X-ray, CT, MRI)?
3. Is this an endoscopic or ultrasound image?

Provide a detailed description focusing on:
- Any visible abnormalities or pathological findings
- Normal vs abnormal structures
- Clinical significance of the findings

Respond in {language.upper()}. Be systematic and objective.
Start with: "Medical image analysis reveals: ..."
"""
        }

    def _detect_image_type(self, image: Image.Image) -> str:
        """
        Attempts to detect the type of medical image based on visual characteristics.
        Returns: 'dermatology', 'radiology_xray', 'radiology_ct', 'radiology_mri', or 'general_medical'
        """
        # Convert to grayscale for analysis
        gray_image = image.convert('L')
        pixels = list(gray_image.getdata())
        
        # Calculate basic statistics
        avg_brightness = sum(pixels) / len(pixels)
        
        # Count approximate color distribution
        dark_pixels = sum(1 for p in pixels if p < 50)
        light_pixels = sum(1 for p in pixels if p > 200)
        total_pixels = len(pixels)
        
        dark_ratio = dark_pixels / total_pixels
        light_ratio = light_pixels / total_pixels
        
        # Heuristics for image type detection:
        # X-rays typically have dark backgrounds with lighter structures
        # CT/MRI are often grayscale with specific patterns
        # Dermatology images are typically colorful (RGB variance)
        
        # Check if image is predominantly grayscale (radiology)
        rgb_image = image.convert('RGB')
        rgb_pixels = list(rgb_image.getdata())
        
        # Calculate color variance (low variance = grayscale = likely radiology)
        color_variance = 0
        for r, g, b in rgb_pixels[:1000]:  # Sample first 1000 pixels
            avg_color = (r + g + b) / 3
            color_variance += abs(r - avg_color) + abs(g - avg_color) + abs(b - avg_color)
        color_variance /= min(1000, len(rgb_pixels))
        
        logger.debug(f"Image analysis - Brightness: {avg_brightness:.1f}, Dark ratio: {dark_ratio:.2f}, Color variance: {color_variance:.1f}")
        
        # Decision logic
        if color_variance < 10:  # Very grayscale
            if dark_ratio > 0.5:  # Predominantly dark background
                return "radiology_xray"
            elif avg_brightness > 100 and avg_brightness < 180:
                return "radiology_ct"
            else:
                return "radiology_mri"
        elif color_variance < 30:  # Somewhat grayscale
            return "general_medical"
        else:  # Colorful image
            return "dermatology"

    def analyze_image(self, image_base64: str, image_type: str = None) -> str:
        """
        Analizza un'immagine codificata in base64 usando un modello Vision (es. LLaVA).
        
        Args:
            image_base64: Immagine in formato base64
            image_type: Tipo di immagine opzionale ('dermatology', 'radiology_xray', 
                       'radiology_ct', 'radiology_mri', 'general_medical')
                       Se None, verrà rilevato automaticamente.
        
        Returns:
            Descrizione testuale dettagliata dei reperti visivi.
        """
        logger.info(f"ImageAnalyzer: Analisi immagine in corso con {self.model_name}...")
        
        # --- OTTIMIZZAZIONE: Ridimensiona immagine se troppo grande ---
        try:
            image_data = base64.b64decode(image_base64)
            image = Image.open(io.BytesIO(image_data))
            
            # Detect image type if not specified
            if image_type is None:
                image_type = self._detect_image_type(image)
                logger.info(f"Tipo immagine rilevato automaticamente: {image_type}")
            
            # Ridimensiona se lato maggiore > 1024px
            max_size = 1024
            if max(image.size) > max_size:
                logger.info(f"Ridimensionamento immagine da {image.size} a max {max_size}px...")
                image.thumbnail((max_size, max_size))
                
                # Ricodifica in base64
                buffered = io.BytesIO()
                # Use PNG for radiology to preserve grayscale details
                img_format = "PNG" if "radiology" in image_type else "JPEG"
                image.save(buffered, format=img_format, quality=90)
                image_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                
        except Exception as e:
            logger.warning(f"Errore durante il preprocessing immagine: {e}")
            image_type = "general_medical"

        # Select appropriate prompt
        prompt = self.prompts.get(image_type, self.prompts["general_medical"])

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
                    "temperature": 0.1,  # Slightly more creative for complex analysis
                    "num_ctx": 4096      # Increased context for detailed analysis
                }
            )
            description = response['message']['content']
            logger.info(f"Analisi completata (tipo: {image_type}).")
            return description

        except Exception as e:
            logger.error(f"Errore ImageAnalyzer: {e}")
            return "Impossibile analizzare l'immagine. Assicurati che Ollama sia attivo e abbia risorse sufficienti."
