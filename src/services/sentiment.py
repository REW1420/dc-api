from transformers import pipeline
from typing import Dict, Union
import torch


class AnalizadorTransformers:
    def __init__(self):
        # Cargar modelos específicos para español
        self.modelo_principal = pipeline(
            "text-classification",
            model="finiteautomata/beto-sentiment-analysis",
            tokenizer="finiteautomata/beto-sentiment-analysis",
            device=0 if torch.cuda.is_available() else -1
        )

        # Modelo secundario para desempates
        self.modelo_secundario = pipeline(
            "sentiment-analysis",
            model="nlptown/bert-base-multilingual-uncased-sentiment"
        )

    def analizar(self, texto: str) -> Dict[str, Union[str, float]]:
        if not texto.strip():
            return {"sentimiento": "neutral", "confianza": 0.0}

        # 1. Análisis con modelo principal (BETO)
        resultado_principal = self.modelo_principal(texto)[0]
        etiqueta = resultado_principal['label'].lower()
        confianza = resultado_principal['score']

        # 2. Verificación con modelo secundario si la confianza es baja
        if confianza < 0.7:
            resultado_secundario = self.modelo_secundario(texto)[0]
            if abs(resultado_secundario['score'] - confianza) > 0.2:
                etiqueta = "neutral"  # Caso de discordancia alta

        # 3. Mapeo a categorías estándar
        mapeo = {
            "pos": "positivo",
            "neg": "negativo",
            "1": "negativo",  # Para el modelo secundario
            "5": "positivo"
        }

        return {
            "sentimiento": mapeo.get(etiqueta, "neutral"),
            "confianza": round(confianza, 4),
            "modelo": "BETO" if confianza >= 0.7 else "BERT multilingual"
        }


# -------------------------------------------------------------------
# EJEMPLO DE USO
# -------------------------------------------------------------------
if __name__ == "__main__":
    analizador = AnalizadorTransformers()

    textos = [
        "El servicio fue excepcional, totalmente recomendado!",
        "Odio cuando no cumplen con lo prometido",
        "La atención es regular, podría mejorar",
        "No está mal, pero el precio es elevado para lo que ofrece"
    ]

    for texto in textos:
        print(f"\n📝 Texto: {texto}")
        resultado = analizador.analizar(texto)
        print(f"✅ Sentimiento: {resultado['sentimiento'].upper()}")
        print(f"🔍 Confianza: {resultado['confianza'] * 100:.2f}%")
        print(f"⚙️ Modelo usado: {resultado['modelo']}")
