import os

# Configuración: Archivos y carpetas a ignorar para no hacer ruido
IGNORE_DIRS = {
    "node_modules", "__pycache__", ".venv", ".git", ".idea", ".vscode", 
    "dist", "build", "coverage", "logs", "mysql_dump", "waha_sessions", ".waha_sessions"
}
IGNORE_EXT = {".lock", ".log", ".pyc", ".png", ".jpg", ".sqlite3", ".wal", ".shm"}
# Archivos clave que SIEMPRE queremos leer completos
CRITICAL_FILES = [
    "docker-compose.yml",
    "graph.py",
    "router.py",
    "loader.py",
    "manager.py",
    "server.py",
    "business_context.yaml",
    "index.ts" # El sidecar
]

def print_tree(startpath):
    print("\n=== 1. ESTRUCTURA DEL PROYECTO (TREE) ===")
    for root, dirs, files in os.walk(startpath):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        level = root.replace(startpath, '').count(os.sep)
        indent = ' ' * 4 * (level)
        print(f'{indent}{os.path.basename(root)}/')
        subindent = ' ' * 4 * (level + 1)
        for f in files:
            if not any(f.endswith(ext) for ext in IGNORE_EXT):
                print(f'{subindent}{f}')

def print_file_contents(startpath):
    print("\n=== 2. CONTENIDO DE ARCHIVOS CRÍTICOS ===")
    for root, dirs, files in os.walk(startpath):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for f in files:
            # Check if it matches critical files OR it is a python file inside src/
            # We want to be careful not to dump everything if src is huge, but for this project it seems reasonable
            is_critical = f in CRITICAL_FILES
            is_src_code = f.endswith(".py") and "/src/" in root.replace("\\", "/") # cross platform check simple
            
            # Additional constraint: Only main components mentioned in option A to avoid noise
            # or just follow script logic provided in prompt.
            # The prompt script logic: f in CRITICAL_FILES or (f.endswith(".py") and "src" in root)
            
            if is_critical or (f.endswith(".py") and "src" in root):
                file_path = os.path.join(root, f)
                try:
                    with open(file_path, 'r', encoding='utf-8') as content:
                        print(f"\n--- FILE: {file_path} ---")
                        print(content.read())
                except Exception as e:
                    print(f"[Error leyendo {file_path}: {e}]")

if __name__ == "__main__":
    current_dir = os.getcwd()
    print(f"Generando radiografía de: {current_dir}")
    print_tree(current_dir)
    print_file_contents(current_dir)
