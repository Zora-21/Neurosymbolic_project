"""
Questo file contiene tool simbolici e deterministici (funzioni Python pure)
che possono essere chiamati da qualsiasi agente.
Ogni funzione DEVE ritornare un dizionario (o un oggetto serializzabile JSON).
"""
import math
from typing import Dict, Any

# --- TOOL GENERICI ---

def classify_fever(temperature_celsius: float) -> Dict[str, Any]:
    """
    Classifica la temperatura corporea in categorie mediche standard.
    Tool puramente simbolico.
    """
    try:
        temp = float(temperature_celsius)
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
            interpretation = "Febbre."
        elif temp >= 39.5:
            category = "Febbre Alta"
            interpretation = "Febbre molto alta, monitorare con attenzione."

        result = {
            "tool_name": "classify_fever",
            "temperature_input_celsius": temp,
            "category": category,
            "interpretation": interpretation
        }
        print(f"Tool Simbolico Eseguito: {result}")
        return result
        
    except Exception as e:
        print(f"Errore nel tool classify_fever: {e}")
        return {"error": f"Errore nel calcolo della febbre: {e}"}

def classify_pain_level(score: int) -> Dict[str, Any]:
    """
    Classifica il livello di dolore basato sulla Numeric Rating Scale (NRS) da 0 a 10.
    Tool puramente simbolico.
    """
    try:
        score = int(score)
        if not (0 <= score <= 10):
            raise ValueError("Il punteggio deve essere tra 0 e 10.")

        category = "Indeterminata"
        if score == 0:
            category = "Nessun Dolore"
        elif 1 <= score <= 3:
            category = "Dolore Lieve"
        elif 4 <= score <= 6:
            category = "Dolore Moderato"
        elif 7 <= score <= 10:
            category = "Dolore Severo"

        result = {
            "tool_name": "classify_pain_level",
            "score_input": score,
            "category": category
        }
        print(f"Tool Simbolico Eseguito: {result}")
        return result

    except Exception as e:
        print(f"Errore nel tool classify_pain_level: {e}")
        return {"error": f"Errore nella classificazione del dolore: {e}"}

def classify_symptom_duration(duration_value: int, duration_unit: str) -> Dict[str, Any]:
    """
    Normalizza la durata dei sintomi in giorni e la classifica come acuta, subacuta o cronica.
    Tool puramente simbolico.
    """
    try:
        duration_value = int(duration_value)
        duration_unit = str(duration_unit).lower().strip()
        total_days = 0

        if duration_unit in ["giorno", "giorni"]:
            total_days = duration_value
        elif duration_unit in ["settimana", "settimane"]:
            total_days = duration_value * 7
        elif duration_unit in ["mese", "mesi"]:
            total_days = duration_value * 30  # Approssimazione
        else:
            raise ValueError(f"Unità di tempo '{duration_unit}' non riconosciuta. Usare 'giorni', 'settimane' o 'mesi'.")

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
        print(f"Tool Simbolico Eseguito: {result}")
        return result
        
    except Exception as e:
        print(f"Errore nel tool classify_symptom_duration: {e}")
        return {"error": f"Errore nel calcolo della durata: {e}"}

# --- TOOL SPECIFICI (Esempi che avevamo già) ---

def calculate_simple_curb65(age: int, confusion: bool, respiratory_rate: int) -> Dict[str, Any]:
    """
    Calcola uno score CURB-65 semplificato (basato su 3 fattori)
    per la gravità della polmonite.
    """
    try:
        score = 0
        reasoning = []

        if int(age) >= 65:
            score += 1
            reasoning.append("Età >= 65 anni (+1)")
        
        if bool(confusion):
            score += 1
            reasoning.append("Presenza di confusione mentale (+1)")
            
        if int(respiratory_rate) >= 30:
            score += 1
            reasoning.append("Frequenza respiratoria >= 30/min (+1)")

        if score == 0:
            interpretation = "Rischio Basso. Generalmente trattabile a domicilio."
        elif score == 1:
            interpretation = "Rischio Medio-Basso. Considerare valutazione medica."
        elif score == 2:
            interpretation = "Rischio Moderato. Considerare ricovero ospedaliero."
        else: # score 3
            interpretation = "Rischio Alto. Ricovero urgente raccomandato."

        result = {
            "tool_name": "Simple_CURB-65_Score",
            "score": score,
            "interpretation": interpretation,
            "factors": reasoning
        }
        print(f"Tool Simbolico Eseguito: {result}")
        return result
    except Exception as e:
        return {"error": f"Errore nel tool calculate_simple_curb65: {e}"}


def classify_blood_pressure(systolic: int, diastolic: int) -> Dict[str, Any]:
    """
    Classifica la pressione sanguigna basandosi sulle linee guida (es. AHA/ACC).
    """
    try:
        systolic = int(systolic)
        diastolic = int(diastolic)
        category = "Indeterminata"
        interpretation = "Dati non sufficienti per una classificazione."

        if systolic > 180 or diastolic > 120:
            category = "Crisi Ipertensiva"
            interpretation = "Crisi ipertensiva. Consultare immediatamente un medico."
        elif systolic >= 140 or diastolic >= 90:
            category = "Ipertensione (Stadio 2)"
            interpretation = "Ipertensione di Stadio 2. Consulto medico necessario."
        elif 130 <= systolic <= 139 or 80 <= diastolic <= 89:
            category = "Ipertensione (Stadio 1)"
            interpretation = "Ipertensione di Stadio 1. Si raccomanda un consulto medico."
        elif 120 <= systolic <= 129 and diastolic < 80:
            category = "Elevata"
            interpretation = "Pressione elevata. Rischio di sviluppare ipertensione."
        elif systolic < 120 and diastolic < 80:
            category = "Normale"
            interpretation = "Pressione sanguigna ottimale."
        else:
            category = "Ipotensione (o dati insoliti)"
            interpretation = "Valori di pressione bassi (ipotensione) o insoliti."
        
        result = {
            "tool_name": "Blood_Pressure_Classifier",
            "category": category,
            "interpretation": interpretation,
            "systolic_input": systolic,
            "diastolic_input": diastolic
        }
        print(f"Tool Simbolico Eseguito: {result}")
        return result
    except Exception as e:
        return {"error": f"Errore nel tool classify_blood_pressure: {e}"}

