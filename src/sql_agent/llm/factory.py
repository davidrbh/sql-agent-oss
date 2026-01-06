import os
from langchain_core.language_models.chat_models import BaseChatModel

# Importamos las implementaciones concretas (pero solo las usamos aquí)
from langchain_google_genai import ChatGoogleGenerativeAI
# from langchain_openai import ChatOpenAI  <-- Si en el futuro lo instalas, lo descomentas

from sql_agent.config.loader import ConfigLoader

class LLMFactory:
    """
    Patrón Factory: Centraliza la creación de modelos de lenguaje (LLMs).
    Permite cambiar de proveedor (Google, OpenAI, Anthropic) tocando solo este archivo.
    """
    
    @staticmethod
    def create(temperature: float = 0, structured: bool = False) -> BaseChatModel:
        settings = ConfigLoader.load_settings()
        
        # Leemos el proveedor desde la configuración (o default a google)
        provider = settings.get('llm', {}).get('provider', 'google').lower()
        model_name = settings.get('llm', {}).get('model', 'gemini-2.0-flash')

        print(f"🏭 LLM Factory: Creando instancia de {provider.upper()} ({model_name})...")

        if provider == "google":
            llm = ChatGoogleGenerativeAI(
                model=model_name,
                temperature=temperature,
                max_retries=2
            )
        
        elif provider == "openai":
            # Nota: Esto fallará si no tienes langchain-openai instalado, 
            # pero así es como se vería la arquitectura.
            # return ChatOpenAI(model=model_name, temperature=temperature)
            raise NotImplementedError("OpenAI driver no está instalado actualmente.")
            
        else:
            raise ValueError(f"Proveedor de IA no soportado: {provider}")

        return llm
