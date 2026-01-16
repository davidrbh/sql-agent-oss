import os
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from agent_core.config.loader import ConfigLoader

class LLMFactory:
    """
    Fábrica actualizada con soporte nativo para DeepSeek V3/R1
    según la documentación oficial.
    """
    
    @staticmethod
    def create(temperature: float = None) -> BaseChatModel:
        settings = ConfigLoader.load_settings()
        
        provider = settings.get('llm', {}).get('provider', 'google').lower()
        model_name = settings.get('llm', {}).get('model', 'gemini-2.0-flash')
        
        # Si no pasan temperatura, usamos la del settings, o 0 por defecto
        if temperature is None:
            temperature = settings.get('llm', {}).get('temperature', 0)

        print(f"🏭 LLM Factory: Conectando con {provider.upper()} ({model_name}) | Temp: {temperature}...")

        if provider == "google":
            return ChatGoogleGenerativeAI(
                model=model_name,
                temperature=temperature,
                max_retries=2
            )
        
        elif provider == "deepseek":
            api_key = os.environ.get("DEEPSEEK_API_KEY")
            if not api_key:
                raise ValueError("Falta DEEPSEEK_API_KEY en el archivo .env")
            
            # Configuración específica según Docs de DeepSeek
            return ChatOpenAI(
                model=model_name,
                temperature=temperature,
                api_key=api_key,
                base_url="https://api.deepseek.com", # 👈 URL Oficial
                max_retries=2,
                # DeepSeek soporta hasta 64k tokens de salida en algunos casos, 
                # pero por seguridad para SQL dejamos default o ajustamos si cortara.
            )
            
        else:
            raise ValueError(f"Proveedor no soportado: {provider}")