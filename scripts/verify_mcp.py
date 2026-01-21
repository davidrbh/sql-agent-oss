import requests
import sseclient
import json
import threading
import time

BASE_URL = "http://localhost:3002"

session_endpoint = None

def listen_to_sse(session_event):
    """Escucha eventos SSE para obtener el endpoint de sesión."""
    global session_endpoint
    print(f"📡 Conectando a {BASE_URL}/sse ...")
    
    try:
        response = requests.get(f"{BASE_URL}/sse", stream=True)
        client = sseclient.SSEClient(response)
        
        for event in client.events():
            if event.event == "endpoint":
                print(f"✅ Sesión iniciada. Endpoint recibido: {event.data}")
                session_endpoint = event.data
                session_event.set() # Notificar al hilo principal
            elif event.event == "message":
                print(f"📨 MENSAJE RECIBIDO (SSE): {event.data}")
                # Intentar parsear si es el resultado
                try:
                    data = json.loads(event.data)
                    if data.get("result"):
                         print("🎉 ¡Resultados recibidos!")
                except:
                    pass
            
    except Exception as e:
        print(f"⚠️ SSE Error: {e}")

def test_mcp_protocol():
    global session_endpoint
    session_event = threading.Event()
    
    # Iniciar SSE en segundo plano
    t = threading.Thread(target=listen_to_sse, args=(session_event,))
    t.daemon = True
    t.start()
    
    # Esperar a que se establezca la sesión
    if not session_event.wait(timeout=10):
        print("❌ Timeout esperando sesión SSE")
        return

    post_url = f"{BASE_URL}{session_endpoint}"
    print(f"🚀 Enviando petición MCP a: {post_url}")
    
    # 2. Enviar Request 'tools/list' (Estándar MCP)
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {}
    }
    
    headers = {"Content-Type": "application/json"}
    
    try:
        # En el protocolo MCP sobre SSE, el POST devuelve 202 (Accepted)
        # y la respuesta viene por el canal SSE.
        response = requests.post(post_url, json=payload, headers=headers)
        print(f"DEBUG: Status Code del POST: {response.status_code}")
        
        if response.status_code == 202:
            print("✅ Petición aceptada (202). Esperando respuesta por SSE...")
            # Esperamos un poco para ver el log del hilo SSE
            time.sleep(2)
        else:
            print(f"⚠️ Status inesperado: {response.status_code}")
            print(response.text)

    except Exception as e:
        print(f"❌ Error en la petición: {e}")

if __name__ == "__main__":
    test_mcp_protocol()
