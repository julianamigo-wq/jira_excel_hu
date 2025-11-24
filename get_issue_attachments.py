import os
import requests
import sys
from pathlib import Path 
from concurrent.futures import ThreadPoolExecutor # ¡Nuevo! Para concurrencia

# =========================================================================
try:
    from services.process_doc import ProcessDOC
    from services.email import enviar_email
    from services.iachat import send_chat
    from services.formatxlsx import createxlsx
    from services.upload_attachment_to_jira import upload_attachment_to_jira
except ImportError as e:
    # Mantener el manejo de errores simple y claro
    print(f"ERROR CRÍTICO de importación: {e}. Verifique la estructura de carpetas de 'services'.")
    sys.exit(1) # Forzar la salida si falla
# =========================================================================

# --- CONFIGURACIÓN ---
JIRA_URL = os.getenv('JIRA_BASE_URL')
JIRA_USER = os.getenv('JIRA_API_USER')
JIRA_TOKEN = os.getenv('JIRA_API_TOKEN')

# La clave del ticket (ej: 'PROYECTO-123') viene como argumento de línea de comandos
try:
    JIRA_ISSUE_KEY = sys.argv[1]
except IndexError:
    print("Error: La clave del ticket de Jira no fue proporcionada como argumento.")
    sys.exit(1)

# --- FUNCIONES DE SOPORTE ---

def upload_xlsx_files(target_dir, jira_issue_key, jira_url, jira_user, jira_token):
    """
    Busca archivos .xlsx recién creados en target_dir y los sube al ticket de Jira.
    (La lógica interna se mantiene igual a la versión anterior).
    """
    print("\n--- INICIANDO PROCESO DE SUBIDA DE ARCHIVOS XLSX A JIRA ---")
    
    xlsx_files = [f for f in target_dir.iterdir() if f.suffix.lower() == '.xlsx']
    
    if not xlsx_files:
        print("No se encontraron archivos .xlsx para subir. Finalizando subida.")
        return

    print(f"Se encontraron {len(xlsx_files)} archivos .xlsx para adjuntar a {jira_issue_key}.")
    upload_count = 0
    
    for xlsx_file_path in xlsx_files:
        print(f"  > Subiendo archivo: {xlsx_file_path.name}...")
        
        try:
            success = upload_attachment_to_jira(
                issue_key=jira_issue_key,
                file_path=str(xlsx_file_path),
                jira_url=jira_url,
                jira_user=jira_user,
                jira_token=jira_token
            )
            
            if success:
                print(f"  > SUBIDA EXITOSA: {xlsx_file_path.name}")
                upload_count += 1
            else:
                print(f"  > ERROR DE SUBIDA: La función retornó False para {xlsx_file_path.name}")
                
        except NameError:
            print("  > ERROR: La función 'upload_attachment_to_jira' no está definida o importada.")
            break
        except Exception as e:
            print(f"  > ERROR inesperado al subir {xlsx_file_path.name}: {e}")

    print(f"--- PROCESO DE SUBIDA FINALIZADO. Archivos subidos: {upload_count}/{len(xlsx_files)} ---")

# --- NUEVA FUNCIÓN PARA PROCESAMIENTO CONCURRENTE ---

def process_attachment_flow(att, target_dir, jira_issue_key, jira_url, jira_user, jira_token):
    """
    Función que maneja la descarga y el flujo de procesamiento completo para un solo adjunto.
    """
    filename = att['filename']
    content_url = att['content']
    file_path = target_dir / filename
    
    print(f"  - Adjunto: {filename} - INICIANDO PROCESO CONCURRENTE...")

    # --- 1. DESCARGA DEL ARCHIVO (I/O) ---
    download_success = False
    if not file_path.exists(): # Evita descargar si ya existe (útil en re-ejecuciones)
        try:
            att_response = requests.get(content_url, auth=(jira_user, jira_token), stream=True)
            att_response.raise_for_status()
            
            with open(file_path, 'wb') as f:
                for chunk in att_response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"  - Descarga Exitosa: {file_path.name}")
            download_success = True
        except requests.exceptions.HTTPError as e:
            print(f"  - ERROR al descargar {filename}. HTTP: {e.response.status_code}")
        except Exception as e:
            print(f"  - ERROR inesperado durante descarga de {filename}: {e}")
    else:
        print(f"  - Advertencia: {filename} ya existe. Saltando descarga.")
        download_success = True

    if not download_success:
        return 0 # Indica que no se pudo descargar

    # --- 2. LÓGICA DE PROCESAMIENTO 'HU' ---
    downloaded_path = Path(file_path) # Aseguramos que sea un objeto Path
    if 'hu' in downloaded_path.name.lower():
        print(f"  - {filename} contiene 'hu'. Iniciando procesamiento.")
        
        try:
            # a) Extraer texto (ProcessDOC)
            file_text = ProcessDOC(str(downloaded_path)).process()
            
            if file_text:
                # b) Enviar a la función de Chat (IA)
                ai_text = send_chat(file_text)
                
                if ai_text:
                    # c) Generar archivo XLSX
                    createxlsx(ai_text, target_dir)
                    print(f"  - Flujo HU Terminado: {filename}")
                else:
                    print(f"  - Flujo HU: Falló la respuesta de IA para {filename}.")
            else:
                print(f"  - Flujo HU: Falló la extracción de texto para {filename}.")
        except Exception as e:
            print(f"  - ERROR en el Flujo HU para {filename}: {e}")

    return 1 # Indica que el flujo concurrente ha terminado (éxito o fallo controlado)

# --- FUNCIÓN PRINCIPAL ---

def get_issue_attachments():
    print(f"Buscando adjuntos para el ticket: {JIRA_ISSUE_KEY}...")

    # --- Paso 1: Obtener Metadata del Ticket (Síncrono) ---
    api_url = f"{JIRA_URL}/rest/api/3/issue/{JIRA_ISSUE_KEY}"
    params = {'fields': 'attachment'}
    auth = (JIRA_USER, JIRA_TOKEN)

    try:
        response = requests.get(api_url, auth=auth, params=params)
        response.raise_for_status()
        issue_data = response.json()
        attachments = issue_data['fields']['attachment']
        
        if not attachments:
            print(f"El ticket {JIRA_ISSUE_KEY} no tiene adjuntos. Finalizando.")
            sys.exit(0)

        print(f"Se encontraron {len(attachments)} adjuntos.")

        # --- Paso 2: Configurar Directorios (Síncrono) ---
        user_home = os.path.expanduser('~')
        base_dir = Path(os.path.join(user_home, 'Documents'))
        target_dir = base_dir / JIRA_ISSUE_KEY
        target_dir.mkdir(parents=True, exist_ok=True)
        print(f"Carpeta de destino creada/verificada: {target_dir.resolve()}")

        # --- Paso 3: Ejecutar Flujos de Descarga y Procesamiento (CONCURRENTE) ---
        print("\n--- INICIANDO PROCESOS DE DESCARGA/EXTRACCIÓN CONCURRENTES ---")
        
        # Usamos ThreadPoolExecutor para ejecutar I/O Bound tasks en paralelo
        # El número de 'max_workers' puede ajustarse, 10 es un valor común para I/O.
        with ThreadPoolExecutor(max_workers=10) as executor:
            # Mapeamos la función 'process_attachment_flow' a cada adjunto
            futures = [executor.submit(
                process_attachment_flow, 
                att, 
                target_dir, 
                JIRA_ISSUE_KEY, 
                JIRA_URL, 
                JIRA_USER, 
                JIRA_TOKEN
            ) for att in attachments]
            
            # Esperamos a que todos los futuros terminen
            [f.result() for f in futures]

        print("--- PROCESOS CONCURRENTES FINALIZADOS ---")
        
        # --- Paso 4: Subir Archivos XLSX creados (Síncrono) ---
        upload_xlsx_files(target_dir, JIRA_ISSUE_KEY, JIRA_URL, JIRA_USER, JIRA_TOKEN)

        # --- Paso 5: Proceso de Cierre (Síncrono) ---
        
        # 1. Obtener la lista final de nombres de archivos en la carpeta de descarga
        final_files = [f.name for f in target_dir.iterdir() if f.is_file()]
        
        # 2. Llama a la función enviar_email con la lista de nombres de archivos
        enviar_email(final_files)

    except requests.exceptions.HTTPError as e:
        print(f"Error HTTP al llamar a la API de Jira: {e}")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"Error de conexión al llamar a la API de Jira: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Ocurrió un error inesperado: {e}")
        sys.exit(1)

if __name__ == "__main__":
    get_issue_attachments()
