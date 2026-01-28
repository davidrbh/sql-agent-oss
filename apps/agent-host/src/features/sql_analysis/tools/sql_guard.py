'''
Módulo de protección y validación de consultas SQL.

Este módulo implementa el SQLGuard, un componente de seguridad que utiliza 
análisis de AST (Abstract Syntax Tree) para garantizar que las consultas 
generadas sean seguras, de solo lectura y normalizadas.
'''

import sqlglot
import logging
from sqlglot import exp, parse_one, transpile
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

class SQLGuard:
    '''
    Proporciona validación de seguridad y transpilación defensiva para consultas SQL.
    '''

    def __init__(self, dialect: str = "mysql"):
        self.dialect = dialect
        # Operaciones prohibidas explícitamente en el AST
        self._forbidden_types = (
            exp.Drop, exp.Delete, exp.Insert, exp.Update, 
            exp.AlterTable, exp.Create
        )

    def validate_and_transpile(self, raw_sql: str) -> Tuple[bool, Optional[str], Optional[str]]:
        '''
        Valida la seguridad de la consulta y realiza una transpilación defensiva.
        '''
        try:
            transpiled = transpile(raw_sql, read=self.dialect, write=self.dialect)
            if not transpiled:
                return False, None, "No se pudo parsear ningún SQL válido."
            
            clean_sql = transpiled[0]
            parsed = parse_one(clean_sql, read=self.dialect)

            # 1. Análisis de Seguridad recursivo
            for node in parsed.find_all(self._forbidden_types):
                error = f"Operación prohibida detectada: {type(node).__name__.upper()}"
                logger.warning(f"SQLGuard BLOQUEO: {error} | Query: {raw_sql}")
                return False, None, error

            # 2. Verificación de comandos permitidos
            is_query = isinstance(parsed, (exp.Select, exp.Union, exp.Except, exp.Intersect))
            is_metadata = isinstance(parsed, (exp.Describe, exp.Show))
            
            # Manejo de Command (ej. SHOW TABLES) y bloqueo de TRUNCATE
            is_safe_command = False
            if isinstance(parsed, exp.Command):
                cmd_text = parsed.this.upper()
                if "TRUNCATE" in cmd_text:
                    logger.warning(f"SQLGuard BLOQUEO: TRUNCATE detectado | Query: {raw_sql}")
                    return False, None, "Operación prohibida detectada: TRUNCATE"
                
                safe_keywords = ["SHOW", "DESCRIBE", "DESC", "EXPLAIN"]
                is_safe_command = any(cmd_text.startswith(kw) for kw in safe_keywords)

            if not any([is_query, is_metadata, is_safe_command]):
                 error = "La consulta debe ser estrictamente de lectura (SELECT, DESCRIBE o SHOW)."
                 logger.warning(f"SQLGuard BLOQUEO: {error} | Type: {type(parsed)} | Query: {raw_sql}")
                 return False, None, error

            return True, clean_sql, None

        except Exception as e:
            logger.error(f"SQLGuard ERROR: {str(e)} | Query: {raw_sql}")
            return False, None, f"Error de Análisis SQL: {str(e)}"
