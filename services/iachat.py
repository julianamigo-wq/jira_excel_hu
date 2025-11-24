import os
from pypdf import PdfReader
from openai import OpenAI  # Recuerda que estamos usando openrouter para probar de manera gratuita

# ******************************************************************
# BASE DEL PROMPT
textoInicial = """
A continuación, te proporcionaré la información de una Historia de Usuario.Tu tarea es 
analizar esta historia, identificar los requisitos clave, y generar una lista de Casos 
de Prueba (Test Cases) que cubran las funcionalidades descritas, incluyendo escenarios 
positivos, negativos y de borde cuando sea pertinente.El formato de respuesta debe ser 
una tabla sencilla (formato básico) con las siguientes columnas para cada caso de 
prueba:
ID del Caso Nombre/Descripción del Caso, Pasos a Seguir, Resultado Esperado. 
Necesito que lo muestres como si fuera un formato csv, y no escribas nada adicional ni 
sugerencias finales, ni caracteres especiales o adornos de emojis, ni negritas o formatos 
de texto, solo el resultado de manera sobria. La información es la siguiente: 

"""

# ******************************************************************
def send_chat(text_doc: str) -> str:
    try:
        # Concatenando la extraccion con el textoInicial para generar prompt
        prompt = textoInicial+text_doc
        
        # generamos la consulta a chatgpt
        client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key= os.getenv('APIKEY_OPENROUTER'), # Usamos la apikey obtenida en OpenRouter (es generica)
        )

        completion = client.chat.completions.create(
        extra_headers={
            "HTTP-Referer": "<YOUR_SITE_URL>", # Optional. Site URL for rankings on openrouter.ai.
            "X-Title": "<YOUR_SITE_NAME>", # Optional. Site title for rankings on openrouter.ai.
        },
        extra_body={},
        model="google/gemma-3-4b-it:free",
        messages=[
                    {
                        "role": "user",
                        "content": prompt 
                    }
                ]
        )
        # la respuesta la podemos almacenar en una variable
        csv_text = completion.choices[0].message.content
        return csv_text


    except FileNotFoundError:
        print(f"ERROR: Incluso con la ruta absoluta, el archivo '{text_doc}' no se encontró en la ubicación mostrada.")
        print("Por favor, verifica la capitalización (mayúsculas/minúsculas) y las extensiones ocultas (ej: .pdf.pdf).")
        return ""