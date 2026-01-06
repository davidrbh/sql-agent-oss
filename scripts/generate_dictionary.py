import asyncio
import sys
import os

# Ajuste de path para que Python pueda encontrar el módulo 'src'
# Agregamos el directorio padre de 'scripts' al path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from sql_agent.semantic.hydrator import SemanticHydrator

if __name__ == "__main__":
    print("--- 🧠 Iniciando Generador de Diccionario Semántico ---")
    
    # Instanciamos el hidratador
    # table_limit=5 es para probar rápido y no gastar tokens. 
    # Sube este número (ej: 100) cuando quieras documentar TODA la base de datos.
    hydrator = SemanticHydrator(table_limit=None) 
    
    # Corremos el proceso asíncrono
    asyncio.run(hydrator.run())
