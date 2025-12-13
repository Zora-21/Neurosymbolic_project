"""
Questo file contiene tool simbolici e deterministici (funzioni Python pure)
che possono essere chiamati da qualsiasi agente.
Ogni funzione DEVE ritornare un dizionario (o un oggetto serializzabile JSON).
"""
from typing import Dict, Any
from app.logger import get_triage_logger

# Logger per questo modulo
logger = get_triage_logger()

# --- HELPER INTERNI ---

def _safe_float(value: Any) -> float:
    """
    Tenta di convertire l'input in float gestendo virgole e stringhe.
    Solleva ValueError se non riesce.
    """
    # Gestisce None e stringa "None"
    if value is None or str(value).strip().lower() == 'none':
        raise ValueError("Value is None")
    
    if isinstance(value, (float, int)):
        return float(value)
    
    val_str = str(value).strip().replace(',', '.')
    return float(val_str)

def _safe_int(value: Any) -> int:
    """
    Tenta di convertire l'input in int.
    """
    if isinstance(value, int):
        return value
    # Gestisce casi come "5.0" -> 5
    return int(_safe_float(value))

# --- TOOL GENERICI ---

def classify_fever(temperature_celsius: Any) -> Dict[str, Any]:
    """
    Classifica la temperatura corporea in categorie mediche standard.
    Gestisce input come "38,5" o 38.5.
    """
    try:
        temp = _safe_float(temperature_celsius)
        category = "Indeterminata"
        interpretation = "Valore non valido."

        if temp < 35.0:
            category = "Ipotermia"
            interpretation = "Temperatura pericolosamente bassa."
        elif 35.0 <= temp < 37.6:
            category = "Normale"
            interpretation = "Temperatura corporea normale."
        elif 37.6 <= temp <= 38.2:
            category = "Febbricola (Subfebbrilità)"
            interpretation = "Temperatura leggermente elevata."
        elif 38.3 <= temp <= 39.4:
            category = "Febbre Moderata"
            interpretation = "Febbre significativa."
        elif temp >= 39.5:
            category = "Febbre Alta"
            interpretation = "Febbre molto alta, monitorare con attenzione."

        result = {
            "tool_name": "classify_fever",
            "temperature_input_celsius": temp,
            "category": category,
            "interpretation": interpretation
        }
        logger.debug(f"Tool Simbolico Eseguito: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Errore nel tool classify_fever: {e}")
        return {"error": f"Impossibile calcolare la febbre per valore '{temperature_celsius}': {e}"}

def classify_pain_level(score: Any) -> Dict[str, Any]:
    """
    Classifica il livello di dolore basato sulla Numeric Rating Scale (NRS) da 0 a 10.
    """
    try:
        score_int = _safe_int(score)
        if not (0 <= score_int <= 10):
            raise ValueError("Il punteggio deve essere tra 0 e 10.")

        category = "Indeterminata"
        if score_int == 0:
            category = "Nessun Dolore"
        elif 1 <= score_int <= 3:
            category = "Dolore Lieve"
        elif 4 <= score_int <= 6:
            category = "Dolore Moderato"
        elif 7 <= score_int <= 10:
            category = "Dolore Severo"

        result = {
            "tool_name": "classify_pain_level",
            "score_input": score_int,
            "category": category
        }
        logger.debug(f"Tool Simbolico Eseguito: {result}")
        return result

    except Exception as e:
        logger.error(f"Errore nel tool classify_pain_level: {e}")
        return {"error": f"Errore nella classificazione del dolore: {e}"}

def classify_symptom_duration(duration_value: Any, duration_unit: str) -> Dict[str, Any]:
    """
    Normalizza la durata dei sintomi in giorni e la classifica come acuta, subacuta o cronica.
    """
    try:
        val = _safe_int(duration_value)
        unit = str(duration_unit).lower().strip()
        total_days = 0

        # Gestione un po' più robusta delle unità
        if any(x in unit for x in ["giorno", "giorni", "day"]):
            total_days = val
        elif any(x in unit for x in ["settimana", "settimane", "week"]):
            total_days = val * 7
        elif any(x in unit for x in ["mese", "mesi", "month"]):
            total_days = val * 30  # Approssimazione
        elif any(x in unit for x in ["ora", "ore", "hour"]):
             total_days = 0 # Meno di un giorno
        else:
            raise ValueError(f"Unità di tempo '{unit}' non riconosciuta.")

        category = "Indeterminata"
        if total_days <= 14:
            category = "Acuta"
        elif 14 < total_days <= 90:
            category = "Subacuta"
        elif total_days > 90:
            category = "Cronica"

        result = {
            "tool_name": "classify_symptom_duration",
            "total_days_approx": total_days,
            "category": category
        }
        logger.debug(f"Tool Simbolico Eseguito: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Errore nel tool classify_symptom_duration: {e}")
        return {"error": f"Errore nel calcolo della durata: {e}"}

# --- TOOL SPECIFICI ---

def calculate_simple_curb65(age: Any, confusion: bool, respiratory_rate: Any, urea_mmol_l: Any = None, systolic_bp: Any = None, diastolic_bp: Any = None) -> Dict[str, Any]:
    """
    Calcola lo score CURB-65 completo (5 parametri).
    Criteri:
    - Confusione (+1)
    - Urea > 7 mmol/L (+1)
    - Respiri >= 30/min (+1)
    - Pressione: Sistolica < 90 OR Diastolica <= 60 (+1)
    - Età >= 65 (+1)
    """
    try:
        score = 0
        reasoning = []
        
        age_val = _safe_int(age)
        resp_rate_val = _safe_int(respiratory_rate)
        
        # 1. Età
        if age_val >= 65:
            score += 1
            reasoning.append("Età >= 65 anni (+1)")
        
        # 2. Confusione
        if bool(confusion):
            score += 1
            reasoning.append("Presenza di confusione mentale (+1)")
            
        # 3. Frequenza Respiratoria
        if resp_rate_val >= 30:
            score += 1
            reasoning.append("Frequenza respiratoria >= 30/min (+1)")

        # 4. Urea (Opzionale nel vecchio, ora richiesto se disponibile)
        if urea_mmol_l is not None:
             try:
                 urea_val = _safe_float(urea_mmol_l)
                 if urea_val > 7:
                     score += 1
                     reasoning.append(f"Urea SIERICA > 7 mmol/L ({urea_val}) (+1)")
             except ValueError:
                 reasoning.append("Dato Urea non valido/assente (assumo normale)")

        # 5. Pressione Sanguigna
        if systolic_bp is not None and diastolic_bp is not None:
            try:
                sys_val = _safe_int(systolic_bp)
                dia_val = _safe_int(diastolic_bp)
                if sys_val < 90 or dia_val <= 60:
                    score += 1
                    reasoning.append(f"Pressione bassa ({sys_val}/{dia_val}) -> Sistolica < 90 o Diastolica <= 60 (+1)")
            except ValueError:
                 reasoning.append("Dati Pressione non validi (assumo stabili)")

        # Interpretazione (Scala 0-5)
        if score == 0:
            interpretation = "Rischio Basso (0,7% mortalità). Trattabile a domicilio."
        elif score == 1:
             interpretation = "Rischio Basso (2,1% mortalità). Probabile trattamento domiciliare."
        elif score == 2:
            interpretation = "Rischio Moderato (9,2% mortalità). Considerare ricovero ospedaliero breve."
        elif score == 3:
            interpretation = "Rischio Alto (14,5% mortalità). Ricovero necessario, considerare Terapia Intensiva."
        elif score >= 4:
             interpretation = f"Rischio Molto Alto (Score {score}). Ricovero immediato, considerare Terapia Intensiva."

        result = {
            "tool_name": "Full_CURB-65_Score",
            "score": score,
            "interpretation": interpretation,
            "factors": reasoning
        }
        return result
    except Exception as e:
        return {"error": f"Errore nel tool calculate_simple_curb65: {e}"}


def classify_blood_pressure(systolic: Any, diastolic: Any) -> Dict[str, Any]:
    """
    Classifica la pressione sanguigna basandosi sulle linee guida (es. AHA/ACC).
    """
    try:
        sys_val = _safe_int(systolic)
        dia_val = _safe_int(diastolic)
        
        category = "Indeterminata"
        interpretation = "Dati non sufficienti per una classificazione."

        if sys_val > 180 or dia_val > 120:
            category = "Crisi Ipertensiva"
            interpretation = "Crisi ipertensiva. Consultare immediatamente un medico."
        elif sys_val >= 140 or dia_val >= 90:
            category = "Ipertensione (Stadio 2)"
            interpretation = "Ipertensione di Stadio 2. Consulto medico necessario."
        elif 130 <= sys_val <= 139 or 80 <= dia_val <= 89:
            category = "Ipertensione (Stadio 1)"
            interpretation = "Ipertensione di Stadio 1. Si raccomanda un consulto medico."
        elif 120 <= sys_val <= 129 and dia_val < 80:
            category = "Elevata"
            interpretation = "Pressione elevata. Rischio di sviluppare ipertensione."
        elif sys_val < 120 and dia_val < 80:
            category = "Normale"
            interpretation = "Pressione sanguigna ottimale."
        else:
            category = "Ipotensione (o dati insoliti)"
            interpretation = "Valori di pressione bassi (ipotensione) o insoliti."
        
        result = {
            "tool_name": "Blood_Pressure_Classifier",
            "category": category,
            "interpretation": interpretation,
            "systolic_input": sys_val,
            "diastolic_input": dia_val
        }
        return result
    except Exception as e:
        return {"error": f"Errore nel tool classify_blood_pressure: {e}"}