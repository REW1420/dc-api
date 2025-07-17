import os
import requests
from dotenv import load_dotenv

load_dotenv()

HF_API_URL = "https://api-inference.huggingface.co/models/nlptown/bert-base-multilingual-uncased-sentiment"
HF_API_KEY = os.getenv("HF_API_KEY")

def analizar_sentimiento_hf(texto: str) -> str:
    headers = {
        "Authorization": f"Bearer {HF_API_KEY}"
    }

    payload = {
        "inputs": texto
    }

    response = requests.post(HF_API_URL, headers=headers, json=payload)

    if response.status_code != 200:
        print("Error en la API de Hugging Face:", response.text)
        return "neutral"  # Puedes devolver neutral por defecto si hay error

    predictions = response.json()[0]  # Lista de etiquetas con score

    # Escoger la predicción con mayor score
    top = max(predictions, key=lambda x: x["score"])
    estrellas = int(top["label"][0])  # Ej: '5 stars' → 5

    if estrellas <= 2:
        return "negativo"
    elif estrellas == 3:
        return "neutral"
    else:
        return "positivo"
