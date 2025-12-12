from pydantic import BaseModel, Field, field_validator
from typing import List, Literal, Optional

class Condition(BaseModel):
    condition: str = Field(..., description="Il nome della patologia identificata.")
    probability: str = Field(..., description="La probabilità della condizione basata sui sintomi (High, Medium, Low).")
    reasoning: str = Field(..., description="Breve spiegazione (max 2 frasi) del perché questa condizione è rilevante.")
    treatment: str = Field(default="", description="Suggested treatment or therapy for this condition.")
    
    @field_validator('probability')
    @classmethod
    def normalize_probability(cls, v):
        """Normalizza la probabilità in formato capitalizzato (High/Medium/Low)."""
        normalized = v.lower().strip()
        # Supporta italiano e inglese
        mapping = {
            "alta": "High", "alto": "High", "high": "High",
            "media": "Medium", "medio": "Medium", "medium": "Medium", "moderate": "Medium",
            "bassa": "Low", "basso": "Low", "low": "Low"
        }
        if normalized in mapping:
            return mapping[normalized]
        raise ValueError(f"Invalid probability '{v}'. Must be High, Medium, or Low (or Italian equivalents).")

class MedicalAnalysis(BaseModel):
    potential_conditions: List[Condition] = Field(default_factory=list, description="Lista delle condizioni mediche identificate.")
    sources_consulted: List[str] = Field(default_factory=list, description="Elenco dei file sorgente utilizzati.")

class AgentAction(BaseModel):
    action: Literal["ask_specialist_followup", "perform_triage"]
    question: Optional[str] = Field(None, description="La domanda da porre all'utente se action è 'ask_specialist_followup'.")
    summary: Optional[str] = Field(None, description="Il riassunto dei sintomi se action è 'perform_triage'.")
    extracted_data: Optional[dict] = Field(default_factory=dict, description="Dati numerici estratti (temp, dolore, etc).")