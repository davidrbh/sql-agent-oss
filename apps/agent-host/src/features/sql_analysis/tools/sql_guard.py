import sqlglot
from sqlglot import exp, parse_one, transpile
from typing import Optional, Tuple

class SQLGuard:
    """
    Proporciona validación de seguridad y transpilación defensiva para consultas SQL.
    
    Esta clase actúa como un 'Cortafuegos Cognitivo', asegurando que las consultas SQL 
    generadas sean estrictamente de solo lectura y cumplan con los patrones sintácticos esperados.
    """

    def __init__(self, dialect: str = "mysql"):
        """
        Inicializa el guardián con el dialecto objetivo.

        Args:
            dialect: El dialecto SQL de la base de datos objetivo (ej. 'mysql', 'postgres').
        """
        self.dialect = dialect
        # Operaciones DDL y DML que están estrictamente prohibidas
        self._forbidden_nodes = (
            exp.Drop, exp.Delete, exp.Insert, exp.Update, 
            exp.Alter, exp.Truncate, exp.Create, exp.Command
        )

    def validate_and_transpile(self, raw_sql: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Valida la consulta por seguridad y la transpila para normalización.

        Args:
            raw_sql: La cadena SQL cruda generada por el LLM.

        Returns:
            Tuple conteniendo:
            - is_safe (bool): True si la consulta pasó todos los chequeos de seguridad.
            - safe_sql (str): La cadena SQL normalizada y transpilada.
            - error_msg (str): Mensaje de error si la consulta es insegura o inválida.
        """
        try:
            # 1. Parsing y Normalización
            # Transpilar de vuelta al mismo dialecto normaliza la sintaxis y 
            # elimina comentarios potencialmente maliciosos u ofuscaciones.
            transpiled = transpile(raw_sql, read=None, write=self.dialect)
            if not transpiled:
                return False, None, "No se pudo parsear ningún SQL válido."
            
            clean_sql = transpiled[0]
            parsed = parse_one(clean_sql, read=self.dialect)

            # 2. Chequeo de Seguridad: Operaciones Prohibidas
            # Buscamos en el AST cualquier nodo que represente una operación de modificación de datos.
            if parsed.find(*self._forbidden_nodes):
                found_node = parsed.find(*self._forbidden_nodes)
                return False, None, f"Operación prohibida detectada: {found_node.key.upper()}"

            # 3. Aplicación de Solo-Lectura
            # Asegurar que la consulta sea fundamentalmente una sentencia SELECT.
            if not isinstance(parsed, exp.Select):
                # Chequear si es una Unión u otras expresiones de solo lectura si es necesario
                if not any(isinstance(parsed, t) for t in (exp.Union, exp.Except, exp.Intersect)):
                     return False, None, "La consulta debe ser una sentencia SELECT."

            return True, clean_sql, None

        except Exception as e:
            return False, None, f"Error de Análisis SQL: {str(e)}"