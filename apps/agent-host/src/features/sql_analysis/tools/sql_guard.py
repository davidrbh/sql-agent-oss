"""
Módulo de protección y validación de consultas SQL.

Este módulo implementa el SQLGuard, un componente de seguridad que utiliza 
análisis de AST para garantizar que las consultas generadas sean seguras,
de solo lectura y normalizadas.
"""

import sqlglot
from sqlglot import exp, parse_one, transpile
from typing import Optional, Tuple

class SQLGuard:
    """
    Proporciona validación de seguridad y transpilación defensiva para consultas SQL.
    
    Esta clase actúa como un 'Cortafuegos Cognitivo', asegurando que las consultas 
    cumplan con los estándares de seguridad antes de ser ejecutadas.
    """

    def __init__(self, dialect: str = "mysql"):
        """
        Inicializa el guardián con un dialecto específico.

        Args:
            dialect: El dialecto SQL objetivo (ej. 'mysql', 'postgres').
        """
        self.dialect = dialect
        # Definición de nodos AST que representan operaciones prohibidas (DML/DDL)
        self._forbidden_nodes = (
            exp.Drop, exp.Delete, exp.Insert, exp.Update, 
            exp.AlterTable, exp.Create, exp.Command
        )

    def validate_and_transpile(self, raw_sql: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Valida la seguridad de la consulta y realiza una transpilación defensiva.

        Este método normaliza el SQL y bloquea operaciones peligrosas.

        Args:
            raw_sql: La cadena SQL generada por el LLM.

        Returns:
            tuple: (es_segura, sql_limpio, mensaje_error)
        """
        try:
            # Normalización mediante transpilación
            transpiled = transpile(raw_sql, read=None, write=self.dialect)
            if not transpiled:
                return False, None, "No se pudo parsear ningún SQL válido."
            
            clean_sql = transpiled[0]
            parsed = parse_one(clean_sql, read=self.dialect)

            # Verificación de operaciones prohibidas en el AST
            if parsed.find(*self._forbidden_nodes):
                found_node = parsed.find(*self._forbidden_nodes)
                return False, None, f"Operación prohibida detectada: {found_node.key.upper()}"

            # Verificación estricta de operaciones de lectura
            is_read_only = any([
                isinstance(parsed, exp.Select),
                isinstance(parsed, exp.Describe),
                isinstance(parsed, exp.Show),
                any(isinstance(parsed, t) for t in (exp.Union, exp.Except, exp.Intersect))
            ])

            if not is_read_only:
                 return False, None, "La consulta debe ser una sentencia de lectura (SELECT, DESCRIBE o SHOW)."

            return True, clean_sql, None

        except Exception as e:
            return False, None, f"Error de Análisis SQL: {str(e)}"
