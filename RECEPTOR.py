import socket, struct, threading, time
import numpy as np, cv2
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import winsound
import platform
import math
import csv
import os
from datetime import datetime
from collections import deque

# =========================== CONFIGURACIÓN ===========================
HOST = "192.168.1.96"  # IP RASPBERRY
PORTS = {
    'sens': 6000,      # MQ2 + Ultrasónico
    'thermal': 6001,   # Cámara Térmica  
    'cam': 6002,       # Cámara RGB + Detección Personas
    'radar': 6003      # Radar mmWave
}

EV3_HOST = "169.254.194.235"#solo si quieres manejar el robot con ev3
EV3_PORT = 12345

# =========================== VARIABLES GLOBALES ===========================
last_cam_frame = last_thermal_frame = last_radar_frame = None
last_gas = last_distance = 0.0
last_radar_targets = []
persona_detectada = 0  # 0=no detectado, 1=detectado
persona_detectada_anterior = 0  # Para detectar cambios
alarma_activa = False
ultimo_tiempo_alarma = 0
intervalo_alarma = 2.0
flame_detected = 0 #variable de flama para esperar la señal
alarma_flama_activa = False #esta igual es del de flama xd
ultimo_tiempo_alarma_flama = 0  # este es del sensor de flama
ev3_socket = None
teclas_presionadas = set()
ultimo_tiempo_tecla = 0
intervalo_tecla = 0.1
ultimo_comando_enviado = None


def iniciar_servidor_ia():
    """Servidor para recibir comandos de la IA"""
    def manejar_conexion_ia():
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('localhost', 6007))
        server.listen(1)
        print("🔄 Servidor IA escuchando en puerto 6007...")
        
        while True:
            try:
                conn, addr = server.accept()
                print(f"✅ IA conectada desde {addr}")
                conn.settimeout(2.0)
                
                while True:
                    try:
                        data = conn.recv(1024)
                        if not data:
                            break
                        comando = data.decode().strip()
                        if comando in ['w', 'a', 's', 'd', 'x']:
                            print(f" Comando de IA recibido: {comando}")
                            enviar_comando_ev3(comando)
                    except socket.timeout:
                        continue
                    except Exception as e:
                        print(f"❌ Error en conexión IA: {e}")
                        break
                        
                conn.close()
                print("🔌 Conexión IA cerrada")
                
            except Exception as e:
                print(f"❌ Error aceptando conexión IA: {e}")
    
    # Ejecutar en hilo separado
    thread = threading.Thread(target=manejar_conexion_ia, daemon=True)
    thread.start()

# =========================== SISTEMA DE CAPTURA DE FOTOS ===========================
class PhotoCapture:
    def __init__(self):
        self.directorio_fotos = self.crear_directorio_fotos()
        self.fotos_guardadas = 0
        self.max_fotos = 100  # Límite máximo de fotos
        self.ultimo_tiempo_foto = 0
        self.intervalo_fotos = 8.0  # 8 segundos entre fotos
        
    def crear_directorio_fotos(self):
        """Crea el directorio para guardar las fotos si no existe"""
        directorio_actual = os.path.dirname(os.path.abspath(__file__))
        directorio_fotos = os.path.join(directorio_actual, "fotos_personas")
        if not os.path.exists(directorio_fotos):
            os.makedirs(directorio_fotos)
            print(f"📁 Directorio de fotos creado: {directorio_fotos}")
        return directorio_fotos
    
    def puede_guardar_foto(self):
        """Verifica si ha pasado el intervalo mínimo desde la última foto"""
        tiempo_actual = time.time()
        return tiempo_actual - self.ultimo_tiempo_foto >= self.intervalo_fotos
    
    def guardar_foto_persona(self, frame):
        """Guarda una foto cuando se detecta una persona (con intervalo)"""
        if self.fotos_guardadas >= self.max_fotos:
            print("⚠️ Límite máximo de fotos alcanzado")
            return False
            
        if not self.puede_guardar_foto():
            return False
            
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S-%f')[:-3]
            nombre_archivo = f"persona_detectada_{timestamp}.jpg"
            ruta_completa = os.path.join(self.directorio_fotos, nombre_archivo)
            
            # Convertir de RGB a BGR para OpenCV
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            
            # Guardar la imagen
            cv2.imwrite(ruta_completa, frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])
            self.fotos_guardadas += 1
            self.ultimo_tiempo_foto = time.time()
            
            print(f"📸 Foto guardada: {nombre_archivo} (Total: {self.fotos_guardadas})")
            
            # Registrar en el CSV
            data_logger.registrar_datos(last_gas, last_distance, persona_detectada, 
                                      tecla="FOTO_GUARDADA", comando_ev3=f"FOTO_{nombre_archivo}")
            
            # Actualizar la pestaña de fotos si existe
            if hasattr(app, 'actualizar_lista_fotos'):
                app.actualizar_lista_fotos()
                
            return True
            
        except Exception as e:
            print(f"❌ Error al guardar foto: {e}")
            return False
    
    def obtener_lista_fotos(self):
        """Obtiene la lista de fotos con sus metadatos"""
        fotos = []
        try:
            for archivo in os.listdir(self.directorio_fotos):
                if archivo.lower().endswith(('.jpg', '.jpeg', '.png')):
                    ruta_completa = os.path.join(self.directorio_fotos, archivo)
                    stats = os.stat(ruta_completa)
                    
                    # Extraer información del nombre del archivo
                    if archivo.startswith('persona_detectada_'):
                        fecha_str = archivo.replace('persona_detectada_', '').replace('.jpg', '')
                        try:
                            # Formato: YYYY-MM-DD_HH-MM-SS-sss
                            fecha_dt = datetime.strptime(fecha_str, '%Y-%m-%d_%H-%M-%S-%f')
                            fecha_formateada = fecha_dt.strftime('%Y-%m-%d %H:%M:%S')
                        except:
                            fecha_formateada = datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        fecha_formateada = datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                    
                    tamaño_kb = stats.st_size / 1024
                    
                    fotos.append({
                        'nombre': archivo,
                        'ruta': ruta_completa,
                        'fecha': fecha_formateada,
                        'tamaño_kb': f"{tamaño_kb:.1f} KB",
                        'timestamp': stats.st_mtime
                    })
            
            # Ordenar por fecha (más reciente primero)
            fotos.sort(key=lambda x: x['timestamp'], reverse=True)
            return fotos
            
        except Exception as e:
            print(f"❌ Error al leer directorio de fotos: {e}")
            return []
    
    def eliminar_foto(self, ruta_foto):
        """Elimina una foto específica"""
        try:
            os.remove(ruta_foto)
            print(f"🗑️ Foto eliminada: {os.path.basename(ruta_foto)}")
            return True
        except Exception as e:
            print(f"❌ Error al eliminar foto: {e}")
            return False
    
    def eliminar_todas_fotos(self):
        """Elimina todas las fotos"""
        try:
            fotos = self.obtener_lista_fotos()
            contador_eliminadas = 0
            
            for foto in fotos:
                try:
                    os.remove(foto['ruta'])
                    contador_eliminadas += 1
                    print(f"🗑️ Eliminada: {foto['nombre']}")
                except Exception as e:
                    print(f"❌ Error al eliminar {foto['nombre']}: {e}")
                    continue
            
            self.fotos_guardadas = 0
            print(f"🗑️ Proceso completado: {contador_eliminadas}/{len(fotos)} fotos eliminadas")
            
            # Verificar si realmente se eliminaron todos los archivos
            fotos_restantes = self.obtener_lista_fotos()
            if len(fotos_restantes) == 0:
                return True
            else:
                print(f"⚠️ Quedaron {len(fotos_restantes)} archivos sin eliminar")
                return False
                
        except Exception as e:
            print(f"❌ Error general al eliminar todas las fotos: {e}")
            return False

# Instanciar el sistema de captura de fotos
photo_capture = PhotoCapture()

# =========================== CONSTANTES UI ===========================
COLORES = {
    "fondo": "#000000", 
    "fondo_secundario": "#27274c", 
    "texto": "#FFFFFF",
    "texto_secundario": "#CCCCCC", 
    "exito": "#4caf50", 
    "peligro": "#f44336",
    "info": "#2196f3", 
    "advertencia": "#ffc107", 
    "acento": "#bb86fc",
    "verde_oscuro": "#006400", 
    "verde_brillante": "#00ff64", 
    "cyan": "#00ffff",
    "azul_oscuro": "#0064ff",
    "pestaña_inactiva": "#1a1a2e",
    "pestaña_activa": "#16213e",
    "pestaña_hover": "#2a2a4a",
    "borde_pestaña": "#394867"
}

FUENTES = {
    'titulo': ('Segoe UI', 14, 'bold'), 
    'subtitulo': ('Segoe UI', 12, 'bold'),
    'normal': ('Segoe UI', 10), 
    'pequeno': ('Segoe UI', 9), 
    'metricas': ('Segoe UI', 11, 'bold')
}

# =========================== SISTEMA DE REGISTRO CSV ===========================
class DataLogger:
    def __init__(self):
        directorio_actual = os.path.dirname(os.path.abspath(__file__))
        self.archivo_csv = os.path.join(directorio_actual, "datos_sensores.csv")
        self.crear_archivo_si_no_existe()
        
    def crear_archivo_si_no_existe(self):
        if not os.path.exists(self.archivo_csv):
            with open(self.archivo_csv, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'gas_voltage', 'distancia_cm', 'persona_detectada', 'flame_detected',
                    'tecla_presionada', 'num_targets_radar', 'target_cercano_dist', 
                    'target_cercano_angulo', 'target_cercano_velocidad', 'alarma_activa', 'alarma_flama_activa', 'comando_ev3'
                ])
            print(f"📊 Archivo de registro creado: {self.archivo_csv}")
        else:
            print(f"📊 Archivo de registro existente: {self.archivo_csv}")
    
    def registrar_datos(self, gas, distancia, persona_detectada=0, tecla=None, comando_ev3=None):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
        num_targets = len(last_radar_targets)
        if last_radar_targets:
            distancias = [t['distance'] for t in last_radar_targets]
            dist_min = min(distancias)
            objetivo_cercano_idx = distancias.index(dist_min)
            target_cercano = last_radar_targets[objetivo_cercano_idx]
            target_dist, target_angulo, target_vel = target_cercano['distance'], target_cercano['angle'], target_cercano['speed']
        else:
            target_dist = target_angulo = target_vel = 0
        
        with open(self.archivo_csv, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                timestamp, gas, distancia * 100, persona_detectada, flame_detected,
                tecla if tecla else '', num_targets, target_dist, target_angulo, target_vel,
                alarma_activa, comando_ev3 if comando_ev3 else ''
            ])

data_logger = DataLogger()

# =========================== SISTEMA DE ALARMA ===========================
def activar_alarma_flama():
    global alarma_flama_activa, ultimo_tiempo_alarma_flama
    tiempo_actual = time.time()
    
    if tiempo_actual - ultimo_tiempo_alarma_flama > intervalo_alarma:
        data_logger.registrar_datos(last_gas, last_distance, persona_detectada, tecla="ALARMA_FLAMA")
        
        if platform.system() == "Windows":
            try: 
                # Sonido diferente para flama (más agudo)
                winsound.Beep(1500, 800)
            except: pass
        
        print("🔥 ALARMA: FLAMA DETECTADA!")
        ultimo_tiempo_alarma_flama = tiempo_actual

def verificar_alarma_flama():
    global alarma_flama_activa
    if flame_detected == 1:  # 1 = flama detectada
        if not alarma_flama_activa: 
            alarma_flama_activa = True
        activar_alarma_flama()
        return True
    else:
        alarma_flama_activa = False
        return False

def activar_alarma():
    global alarma_activa, ultimo_tiempo_alarma
    tiempo_actual = time.time()
    
    if tiempo_actual - ultimo_tiempo_alarma > intervalo_alarma:
        data_logger.registrar_datos(last_gas, last_distance, persona_detectada, tecla="ALARMA")
        
        if platform.system() == "Windows":
            try: winsound.Beep(1000, 1000)
            except: pass
        
        print("🚨 ALARMA: GAS BUTANO DETECTADO!")
        ultimo_tiempo_alarma = tiempo_actual

def verificar_alarma_gas():
    global alarma_activa
    if last_gas > 3:
        if not alarma_activa: alarma_activa = True
        activar_alarma()
        return True
    else:
        alarma_activa = False
        return False

# =========================== CONEXIÓN EV3 ===========================
def conectar_ev3():
    global ev3_socket
    try:
        if ev3_socket: ev3_socket.close()
        ev3_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ev3_socket.connect((EV3_HOST, EV3_PORT))
        ev3_socket.settimeout(2.0)
        print("✅ Conectado al EV3")
        return True
    except Exception as e:
        print(f"❌ Error conectando al EV3: {e}")
        ev3_socket = None
        return False

def enviar_comando_ev3(comando):
    global ultimo_comando_enviado
    if comando == ultimo_comando_enviado: return True
    
    if ev3_socket:
        try:
            ev3_socket.send(comando.encode('utf-8'))
            print(f"→ Enviado comando al EV3: '{comando}'")
            data_logger.registrar_datos(last_gas, last_distance, persona_detectada, tecla=comando, comando_ev3=comando)
            ultimo_comando_enviado = comando
            return True
        except Exception as e:
            print(f"❌ Error enviando comando al EV3: {e}")
            ultimo_comando_enviado = None
            conectar_ev3()
            return False
    else:
        print("❌ No hay conexión al EV3")
        return False

def procesar_control_manual():
    global ultimo_tiempo_tecla
    tiempo_actual = time.time()
    
    if teclas_presionadas and tiempo_actual - ultimo_tiempo_tecla > intervalo_tecla:
        if 'w' in teclas_presionadas: enviar_comando_ev3('w')
        elif 's' in teclas_presionadas: enviar_comando_ev3('s')
        elif 'a' in teclas_presionadas: enviar_comando_ev3('a')
        elif 'd' in teclas_presionadas: enviar_comando_ev3('d')
        ultimo_tiempo_tecla = tiempo_actual
    elif not teclas_presionadas and ultimo_comando_enviado != 'x':
        enviar_comando_ev3('x')

# =========================== RECEPCIÓN DE DATOS ===========================
def recibir_datos_generico(port, tipo, procesar_callback):
    while True:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)  # Timeout para conexión
            sock.connect((HOST, port))
            print(f"✅ Conectado a {tipo} en puerto {port}")
            
            while True:
                if not procesar_callback(sock): 
                    break
                    
        except socket.timeout:
            print(f"⏰ Timeout conectando a {tipo}")
        except ConnectionRefusedError:
            print(f"❌ Conexión rechazada por {tipo}")
        except Exception as e:
            print(f"❌ Error {tipo}: {e}")
        finally:
            if sock:
                try:
                    sock.close()
                except:
                    pass
            time.sleep(2)

def procesar_sensores(sock):
    # Cambia "ff" por "ffB" para recibir: gas(float), distance(float), flame_detected(unsigned char)
    data = sock.recv(struct.calcsize("ffB"))
    if not data: return False
        
    global last_gas, last_distance, flame_detected
    last_gas, last_distance, flame_detected = struct.unpack("ffB", data)
    data_logger.registrar_datos(last_gas, last_distance, persona_detectada)
    return True

def procesar_thermal(sock):
    header = sock.recv(struct.calcsize("I"))
    if not header: return False
        
    (size,) = struct.unpack("I", header)
    thermal_bytes = b""
    while len(thermal_bytes) < size:
        thermal_bytes += sock.recv(size - len(thermal_bytes))

    global last_thermal_frame
    thermal_frame = cv2.imdecode(np.frombuffer(thermal_bytes, np.uint8), cv2.IMREAD_COLOR)
    
    # VOLTEAR LA CÁMARA TÉRMICA - AGREGAR ESTAS LÍNEAS
    if thermal_frame is not None:
        # Voltear verticalmente
        thermal_frame = cv2.flip(thermal_frame, 0)
        # Voltear horizontalmente (opcional, si también está al revés horizontalmente)
        thermal_frame = cv2.flip(thermal_frame, 1)
    
    last_thermal_frame = cv2.cvtColor(thermal_frame, cv2.COLOR_BGR2RGB)
    return True

def procesar_camera(sock):
    try:
        # Recibir header con timeout
        sock.settimeout(2.0)
        header = sock.recv(struct.calcsize("IB"))
        if not header or len(header) != struct.calcsize("IB"):
            print("⚠️ Header de cámara incompleto")
            return False
            
        global last_cam_frame, persona_detectada, persona_detectada_anterior
        size, persona_detectada = struct.unpack("IB", header)

        # Validar tamaño del frame
        if size > 10 * 1024 * 1024:  # 10MB máximo
            print(f"⚠️ Frame demasiado grande: {size} bytes")
            return False

        # Recibir datos con timeout
        cam_bytes = b""
        start_time = time.time()
        while len(cam_bytes) < size:
            try:
                chunk = sock.recv(min(8192, size - len(cam_bytes)))
                if not chunk:
                    break
                cam_bytes += chunk
                
                # Timeout de recepción
                if time.time() - start_time > 5.0:
                    print("⏰ Timeout recibiendo frame")
                    return False
                    
            except socket.timeout:
                print("⏰ Timeout en recepción de frame")
                return False
                
        if len(cam_bytes) != size:
            print(f"⚠️ Datos de cámara incompletos: {len(cam_bytes)}/{size} bytes")
            return False

        # Decodificar imagen
        cam_frame = cv2.imdecode(np.frombuffer(cam_bytes, np.uint8), cv2.IMREAD_COLOR)
        if cam_frame is None:
            print("❌ Error decodificando imagen")
            return False
            
        last_cam_frame = cv2.cvtColor(cam_frame, cv2.COLOR_BGR2RGB)
        
        # Lógica de detección de personas y fotos
        if persona_detectada and not persona_detectada_anterior:
            print(f"👤 PERSONA DETECTADA - Flag: {persona_detectada}")
            if last_cam_frame is not None:
                photo_capture.guardar_foto_persona(last_cam_frame)
        
        elif persona_detectada and persona_detectada_anterior:
            if last_cam_frame is not None and photo_capture.puede_guardar_foto():
                print("📸 Guardando foto periódica...")
                photo_capture.guardar_foto_persona(last_cam_frame)
        
        persona_detectada_anterior = persona_detectada
        return True
        
    except Exception as e:
        print(f"❌ Error procesando cámara: {e}")
        return False
        
def procesar_radar(sock):
    num_targets_data = sock.recv(1)
    if not num_targets_data: return False
        
    num_targets = struct.unpack("B", num_targets_data)[0]
    targets = []
    target_struct = struct.Struct("Bfff")
    target_size = target_struct.size
    
    for _ in range(num_targets):
        target_data = b""
        while len(target_data) < target_size:
            chunk = sock.recv(target_size - len(target_data))
            if not chunk:
                break
            target_data += chunk
        
        if len(target_data) == target_size:
            unpacked = target_struct.unpack(target_data)
            targets.append({
                'num': unpacked[0], 'distance': unpacked[1],
                'angle': unpacked[2], 'speed': unpacked[3]
            })
        else:
            print(f"⚠️ Datos de radar incompletos: {len(target_data)}/{target_size} bytes")
    
    global last_radar_targets
    last_radar_targets = targets
    
    # DEBUG: Mostrar objetivos recibidos
    if targets:
        print(f"📡 Radar: {len(targets)} objetivo(s) recibido(s)")
        for target in targets:
            print(f"   Target {target['num']}: {target['distance']:.2f}m, {target['angle']:.1f}°, {target['speed']:.2f}m/s")
    
    return True

# =========================== RADAR DISPLAY ===========================
class RadarDisplay(tk.Canvas):
    def __init__(self, parent, width=600, height=500, **kwargs):
        super().__init__(parent, width=width, height=height, **kwargs)
        self.width, self.height = width, height
        self.max_range, self.fov_angle = 7000, 120
        self.center_x, self.center_y = self.width // 2, self.height - 80
        self.radar_radius = min(self.width // 2 - 50, self.height - 120)
        self.sweep_angle, self.sweep_speed, self.sweep_visible = 0, 2, True
        self.respiration_data = {}
        self.respiration_history_length = 50
        
    def update_display(self, targets):
        self.delete("all")
        self.draw_radar_background()
        if self.sweep_visible: self.draw_sweep()
        
        for target in targets:
            if target['distance'] <= self.max_range and abs(target['angle']) <= self.fov_angle/2:
                self.draw_target(target)
        
        self.sweep_angle += self.sweep_speed
        if self.sweep_angle > self.fov_angle/2: self.sweep_angle = -self.fov_angle/2

    def draw_radar_background(self):
        self.create_rectangle(0, 0, self.width, self.height, fill=COLORES["fondo"], outline="")
        fov_half, max_range_meters = self.fov_angle / 2, self.max_range / 1000
        
        range_intervals = (list(range(1, int(max_range_meters) + 1)) if max_range_meters <= 5 else
                          list(range(2, int(max_range_meters) + 1, 2)) if max_range_meters <= 10 else
                          list(range(5, int(max_range_meters) + 1, 5)))
        
        for range_m in range_intervals:
            radius = int((range_m * 1000 / self.max_range) * self.radar_radius)
            if 0 < radius <= self.radar_radius:
                self.draw_range_arc(radius, -fov_half, fov_half, COLORES["verde_oscuro"])
                label_angle = 0
                screen_angle = math.radians(self.angle_to_screen_angle(label_angle))
                label_x = self.center_x + (radius + 15) * math.cos(screen_angle)
                label_y = self.center_y - (radius + 15) * math.sin(screen_angle)
                self.create_text(label_x, label_y, text=f"{range_m}m", 
                               fill=COLORES["verde_oscuro"], font=FUENTES['pequeno'])
        
        for angle in [-fov_half, fov_half]:
            screen_angle = math.radians(self.angle_to_screen_angle(angle))
            end_x = self.center_x + self.radar_radius * math.cos(screen_angle)
            end_y = self.center_y - self.radar_radius * math.sin(screen_angle)
            self.create_line(self.center_x, self.center_y, end_x, end_y, 
                           fill=COLORES["exito"], width=2)
        
        for angle in range(-60, 61, 30):
            if abs(angle) <= fov_half and angle != 0:
                screen_angle = math.radians(self.angle_to_screen_angle(angle))
                end_x = self.center_x + self.radar_radius * math.cos(screen_angle)
                end_y = self.center_y - self.radar_radius * math.sin(screen_angle)
                self.create_line(self.center_x, self.center_y, end_x, end_y, 
                               fill=COLORES["verde_oscuro"], width=1)
                label_x = self.center_x + (self.radar_radius + 25) * math.cos(screen_angle)
                label_y = self.center_y - (self.radar_radius + 25) * math.sin(screen_angle)
                self.create_text(label_x, label_y, text=f"{angle}°", 
                               fill=COLORES["verde_oscuro"], font=FUENTES['pequeno'])
        
        screen_angle = math.radians(self.angle_to_screen_angle(0))
        end_x = self.center_x + self.radar_radius * math.cos(screen_angle)
        end_y = self.center_y - self.radar_radius * math.sin(screen_angle)
        self.create_line(self.center_x, self.center_y, end_x, end_y, 
                       fill=COLORES["exito"], width=1)
        self.create_oval(self.center_x-4, self.center_y-4, self.center_x+4, self.center_y+4, 
                        fill=COLORES["exito"], outline="")
        self.draw_radar_area_outline()

    def draw_range_arc(self, radius, start_angle, end_angle, color, width=1):
        points = []
        start_screen_angle = math.radians(self.angle_to_screen_angle(start_angle))
        end_screen_angle = math.radians(self.angle_to_screen_angle(end_angle))
        angle_step = (end_screen_angle - start_screen_angle) / 30
        
        for i in range(31):
            angle = start_screen_angle + i * angle_step
            x = self.center_x + radius * math.cos(angle)
            y = self.center_y - radius * math.sin(angle)
            points.append((x, y))
        
        if len(points) > 1:
            for i in range(len(points)-1):
                self.create_line(points[i][0], points[i][1], points[i+1][0], points[i+1][1],
                               fill=color, width=width)

    def draw_radar_area_outline(self):
        fov_half = self.fov_angle / 2
        left_angle = math.radians(self.angle_to_screen_angle(-fov_half))
        right_angle = math.radians(self.angle_to_screen_angle(fov_half))
        
        points = [(self.center_x, self.center_y)]
        for i in range(31):
            angle = left_angle + i * (right_angle - left_angle) / 30
            x = self.center_x + self.radar_radius * math.cos(angle)
            y = self.center_y - self.radar_radius * math.sin(angle)
            points.append((x, y))
        points.append((self.center_x, self.center_y))
        
        for i in range(len(points)-1):
            self.create_line(points[i][0], points[i][1], points[i+1][0], points[i+1][1],
                           fill=COLORES["verde_oscuro"], width=1)

    def draw_sweep(self):
        fov_half = self.fov_angle / 2
        if abs(self.sweep_angle) <= fov_half:
            screen_angle = math.radians(self.angle_to_screen_angle(self.sweep_angle))
            end_x = self.center_x + self.radar_radius * math.cos(screen_angle)
            end_y = self.center_y - self.radar_radius * math.sin(screen_angle)
            
            for i in range(4):
                alpha_angle = self.sweep_angle - i * 2
                if abs(alpha_angle) <= fov_half:
                    alpha_screen_angle = math.radians(self.angle_to_screen_angle(alpha_angle))
                    alpha_end_x = self.center_x + self.radar_radius * math.cos(alpha_screen_angle)
                    alpha_end_y = self.center_y - self.radar_radius * math.sin(alpha_screen_angle)
                    intensity = 200 - (i * 50)
                    if intensity > 0:
                        color = f"#00{int(intensity):02x}00"
                        self.create_line(self.center_x, self.center_y, alpha_end_x, alpha_end_y, 
                                       fill=color, width=max(1, 3-i))

    def angle_to_screen_angle(self, angle_deg): return -angle_deg + 90

    def polar_to_cartesian(self, distance_mm, angle_deg):
        pixel_radius = int((distance_mm / self.max_range) * self.radar_radius)
        screen_angle = math.radians(self.angle_to_screen_angle(angle_deg))
        x = self.center_x + pixel_radius * math.cos(screen_angle)
        y = self.center_y - pixel_radius * math.sin(screen_angle)
        return int(x), int(y)

    def update_respiration_data(self, target_num, speed):
        if target_num not in self.respiration_data:
            self.respiration_data[target_num] = {
                'speed_history': deque(maxlen=self.respiration_history_length),
                'breathing_detected': False, 'last_update': time.time()
            }
        
        data = self.respiration_data[target_num]
        data['speed_history'].append(speed)
        
        current_time = time.time()
        if current_time - data['last_update'] >= 2.0 and len(data['speed_history']) > 10:
            self.analyze_breathing(target_num)
            data['last_update'] = current_time

    def analyze_breathing(self, target_num):
        if target_num not in self.respiration_data: return
        data = self.respiration_data[target_num]
        speed_history = list(data['speed_history'])
        if len(speed_history) < 10: return
        
        speed_variations = np.abs(np.diff(speed_history))
        data['breathing_detected'] = np.mean(speed_variations) > 0.5

    def draw_target(self, target):
        x, y = self.polar_to_cartesian(target['distance'], target['angle'])
        target_num = target['num']
        self.update_respiration_data(target_num, target['speed'])
        
        if target_num in self.respiration_data and self.respiration_data[target_num]['breathing_detected']:
            color, pulse_color, breathing_symbol = COLORES["cyan"], COLORES["azul_oscuro"], "💨"
        else:
            color, pulse_color, breathing_symbol = COLORES["advertencia"], COLORES["peligro"], "○"
        
        if target_num in self.respiration_data:
            data = self.respiration_data[target_num]
            if data['breathing_detected']:
                pulse_size = 3 + 2 * math.sin(time.time() * 4)
                self.create_oval(x-8-pulse_size, y-8-pulse_size, x+8+pulse_size, y+8+pulse_size,
                               outline=pulse_color, width=2)
        
        self.create_oval(x-8, y-8, x+8, y+8, fill=color, outline=COLORES["texto"], width=2)
        
        if abs(target['speed']) > 0.1:
            arrow_length = min(30, abs(target['speed']) * 3)
            angle_rad = math.radians(self.angle_to_screen_angle(target['angle']))
            if target['speed'] > 0:
                arrow_end_x = x + arrow_length * math.cos(angle_rad)
                arrow_end_y = y - arrow_length * math.sin(angle_rad)
                arrow_color = COLORES["peligro"]
            else:
                arrow_end_x = x - arrow_length * math.cos(angle_rad)
                arrow_end_y = y + arrow_length * math.sin(angle_rad)
                arrow_color = COLORES["exito"]
            
            self.create_line(x, y, arrow_end_x, arrow_end_y, 
                           fill=arrow_color, width=3, arrow=tk.LAST)
        
        label_text = f"T{target_num+1} {breathing_symbol}"
        self.create_text(x + 15, y - 15, text=label_text, 
                       fill=color, font=FUENTES['pequeno'], anchor="w")

# =========================== INTERFAZ PRINCIPAL ===========================
class App:
    def __init__(self, root):
        self.root = root
        self.current_camera_mode = "rgb"
        self.foto_seleccionada = None
        self.setup_ui()
        self.setup_bindings()
        
    def setup_ui(self):
        self.root.title("Sistema de Monitoreo - Robot Rescatista FRIDAI")
        self.root.geometry("1400x800")
        self.root.configure(bg=COLORES["fondo"])
        
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # CONFIGURACIÓN MEJORADA DE LAS PESTAÑAS
        style = ttk.Style()
        style.theme_use('default')
        
        # Configurar el estilo del notebook
        style.configure('TNotebook', 
                       background=COLORES["fondo"],
                       borderwidth=0,
                       tabmargins=[2, 5, 2, 0])
        
        # Configurar las pestañas normales
        style.configure('TNotebook.Tab',
                       background=COLORES["pestaña_inactiva"],
                       foreground=COLORES["texto"],
                       padding=[20, 8],
                       font=FUENTES['normal'],
                       focuscolor=COLORES["fondo"],
                       borderwidth=2,
                       relief="raised")
        
        # Configurar pestañas seleccionadas
        style.map('TNotebook.Tab',
                 background=[('selected', COLORES["pestaña_activa"]),
                           ('active', COLORES["pestaña_hover"])],
                 foreground=[('selected', COLORES["acento"]),
                           ('active', COLORES["texto"])],
                 relief=[('selected', 'raised'),
                        ('active', 'raised')])
        
        # Crear pestañas
        self.tab_principal = tk.Frame(self.notebook, bg=COLORES["fondo"])
        self.notebook.add(self.tab_principal, text="🏠 VISTA PRINCIPAL")
        self.setup_tab_principal()
        
        self.tab_radar = tk.Frame(self.notebook, bg=COLORES["fondo"])
        self.notebook.add(self.tab_radar, text="📡 VISTA RADAR")
        self.setup_tab_radar()
        
        # NUEVA PESTAÑA PARA FOTOS
        self.tab_fotos = tk.Frame(self.notebook, bg=COLORES["fondo"])
        self.notebook.add(self.tab_fotos, text="📸 GESTIÓN DE FOTOS")
        self.setup_tab_fotos()
        
        self.tab_principal.grid_columnconfigure(0, weight=3)
        self.tab_principal.grid_columnconfigure(1, weight=1)
        self.tab_principal.grid_rowconfigure(1, weight=1)

    def setup_tab_principal(self):
        # Header
        header = tk.Frame(self.tab_principal, bg=COLORES["fondo_secundario"], height=50)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        header.grid_propagate(False)
        
        tk.Label(header, text="🤖 ROBOT RESCATISTA PROTEUS - VISTA PRINCIPAL",
            bg=COLORES["fondo_secundario"], fg=COLORES["texto"], font=FUENTES['titulo']
        ).pack(side="left", padx=20)


        header_status_frame = tk.Frame(header, bg=COLORES["fondo_secundario"])
        header_status_frame.pack(side="right", padx=20)

        self.ev3_status_header = tk.Label(header, text="● EV3 Desconectado",
            bg=COLORES["fondo_secundario"], fg=COLORES["peligro"], font=FUENTES['normal'])
        self.ev3_status_header.pack(side="right", padx=20)

        self.ia_status_header = tk.Label(header_status_frame, text="● IA: Servidor activo", 
            bg=COLORES["fondo_secundario"], fg=COLORES["exito"], font=FUENTES['normal'])
        self.ia_status_header.pack(anchor='e')



        # Cuerpo Principal
        left = tk.Frame(self.tab_principal, bg=COLORES["fondo"])
        left.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        left.grid_rowconfigure(0, weight=1)
        left.grid_columnconfigure(0, weight=1)

        self.frame_cam_principal = tk.LabelFrame(left, text="📷 CÁMARA PRINCIPAL", 
            fg=COLORES["info"], bg=COLORES["fondo_secundario"],
            font=FUENTES['subtitulo'], labelanchor='n')
        self.frame_cam_principal.grid(row=0, column=0, sticky="nsew")
        self.frame_cam_principal.grid_rowconfigure(1, weight=1)
        self.frame_cam_principal.grid_columnconfigure(0, weight=1)
        
        self.crear_pestanas_camara()

        # Panel derecho
        right = tk.Frame(self.tab_principal, bg=COLORES["fondo"])
        right.grid(row=1, column=1, sticky="nsew", padx=10, pady=10)
        right.grid_columnconfigure(0, weight=1)

        self.frame_sensores = tk.LabelFrame(right, text="🎮 CONTROL Y SENSORES", 
            fg=COLORES["exito"], bg=COLORES["fondo_secundario"],
            font=FUENTES['subtitulo'], labelanchor='n')
        self.frame_sensores.grid(row=0, column=0, sticky="nsew")
        self.frame_sensores.grid_columnconfigure(0, weight=1)

        content_frame = tk.Frame(self.frame_sensores, bg=COLORES["fondo_secundario"])
        content_frame.grid(row=0, column=0, sticky="nsew", padx=15, pady=15)
        content_frame.grid_columnconfigure(0, weight=1)

        # Sensores
        self.crear_widget_sensor(content_frame, "SENSOR DE GAS:", "gas_value", 0)
        self.gas_bar = ttk.Progressbar(content_frame, orient="horizontal", mode="determinate")
        self.gas_bar.grid(row=1, column=0, sticky="ew", pady=(0, 15))
        
        self.crear_widget_sensor(content_frame, "DISTANCIA:", "dist_value", 2)
        self.crear_widget_sensor(content_frame, "DETECCIÓN PERSONAS:", "persona_value", 3)
        self.crear_widget_sensor(content_frame, "SENSOR DE FLAMA:", "flama_value", 4)
        self.crear_widget_sensor(content_frame, "RADAR (ver pestaña 📡):", "radar_info_principal", 5)

        # Control EV3
        control_frame = tk.Frame(content_frame, bg=COLORES["fondo_secundario"])
        control_frame.grid(row=6, column=0, sticky="ew", pady=15)
        
        self.ev3_status = tk.Label(control_frame, text="● EV3 Desconectado", 
            bg=COLORES["fondo_secundario"], fg=COLORES["peligro"], font=FUENTES['normal'])
        self.ev3_status.grid(row=0, column=0, pady=(0, 10))

        wasd_frame = tk.Frame(control_frame, bg=COLORES["fondo_secundario"])
        wasd_frame.grid(row=1, column=0, pady=10)
        
        for i in range(3):
            wasd_frame.columnconfigure(i, weight=1, uniform="wasd")
            wasd_frame.rowconfigure(i, weight=1, uniform="wasd")
        
        self.btn_w = self.create_control_button(wasd_frame, "W", 0, 1)
        self.btn_a = self.create_control_button(wasd_frame, "A", 1, 0)
        self.btn_s = self.create_control_button(wasd_frame, "S", 1, 1)
        self.btn_d = self.create_control_button(wasd_frame, "D", 1, 2)
        
        connect_btn = tk.Label(control_frame, text="🔗 Conectar EV3", 
            bg=COLORES["fondo"], fg=COLORES["texto"], font=FUENTES['pequeno'], 
            relief="raised", padx=15, pady=8, cursor="hand2")
        connect_btn.grid(row=2, column=0, sticky="ew", pady=10)
        connect_btn.bind("<Button-1>", lambda e: conectar_ev3())
        connect_btn.bind("<Enter>", lambda e: connect_btn.config(bg=COLORES["fondo_secundario"]))
        connect_btn.bind("<Leave>", lambda e: connect_btn.config(bg=COLORES["fondo"]))

        tk.Label(control_frame, text="Control con teclas WASD",
            bg=COLORES["fondo_secundario"], fg=COLORES["texto_secundario"],
            font=FUENTES['pequeno']).grid(row=3, column=0, pady=5)

        # Barra de estado y alarma
        self.status_bar = tk.Label(self.tab_principal, text="Sistema iniciando...", 
            bg=COLORES["fondo_secundario"], fg=COLORES["texto"], anchor="w",
            font=FUENTES['pequeno'])
        self.status_bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=5)

        self.alarma_frame = tk.Frame(self.tab_principal, bg=COLORES["peligro"], height=40)
        self.alarma_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        self.alarma_frame.grid_remove()
        
        self.alarma_label = tk.Label(self.alarma_frame, 
            text="🚨 ALARMA: GAS BUTANO DETECTADO! 🚨", 
            font=("Segoe UI", 12, "bold"), fg=COLORES["texto"], bg=COLORES["peligro"])
        self.alarma_label.pack(expand=True)
        
        # NUEVA ALARMA PARA FLAMA
        self.alarma_flama_frame = tk.Frame(self.tab_principal, bg=COLORES["advertencia"], height=40)
        self.alarma_flama_frame.grid(row=4, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        self.alarma_flama_frame.grid_remove()
        self.alarma_flama_label = tk.Label(self.alarma_flama_frame, 
            text="🔥 ALARMA: FLAMA DETECTADA! 🔥", 
            font=("Segoe UI", 12, "bold"), fg=COLORES["texto"], bg=COLORES["advertencia"])
        self.alarma_flama_label.pack(expand=True)

    def crear_widget_sensor(self, parent, texto, variable_name, row):
        frame = tk.Frame(parent, bg=COLORES["fondo_secundario"])
        frame.grid(row=row, column=0, sticky="ew", pady=8)
        frame.grid_columnconfigure(1, weight=1)
        
        tk.Label(frame, text=texto, bg=COLORES["fondo_secundario"], fg=COLORES["texto"],
            font=FUENTES['normal']).grid(row=0, column=0, sticky="w")
        
        # Actualizar para incluir el sensor de flama
        if "FLAMA" in texto:
            valor_inicial = "No detectado"
            color_inicial = COLORES["exito"]
        elif "GAS" in texto:
            valor_inicial = "0.00 V"
            color_inicial = COLORES["exito"]
        elif "RADAR" in texto:
            valor_inicial = "0 objetivos"
            color_inicial = COLORES["info"]
        elif "DISTANCIA" in texto:
            valor_inicial = "0.0 cm"
            color_inicial = COLORES["texto"]
        else:  # PERSONAS
            valor_inicial = "No detectado"
            color_inicial = COLORES["peligro"]
        
        setattr(self, variable_name, tk.Label(frame, text=valor_inicial, 
            bg=COLORES["fondo_secundario"], fg=color_inicial, font=FUENTES['metricas']))
        getattr(self, variable_name).grid(row=0, column=1, sticky="e")

    def setup_tab_radar(self):
        radar_header = tk.Frame(self.tab_radar, bg=COLORES["fondo_secundario"], height=50)
        radar_header.pack(fill="x", padx=10, pady=5)
        
        tk.Label(radar_header, text="📡 SISTEMA DE RADAR mmWave - DETECCIÓN DE RESPIRACIÓN",
            bg=COLORES["fondo_secundario"], fg=COLORES["texto"], font=FUENTES['titulo']
        ).pack(side="left", padx=20)

        radar_body = tk.Frame(self.tab_radar, bg=COLORES["fondo"])
        radar_body.pack(fill="both", expand=True, padx=10, pady=10)
        radar_body.grid_columnconfigure(0, weight=2)
        radar_body.grid_columnconfigure(1, weight=1)
        radar_body.grid_rowconfigure(0, weight=1)

        radar_left = tk.Frame(radar_body, bg=COLORES["fondo"])
        radar_left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        radar_left.grid_rowconfigure(0, weight=1)
        radar_left.grid_columnconfigure(0, weight=1)
        
        self.radar_display_full = RadarDisplay(radar_left, width=600, height=500,
                                              bg=COLORES['fondo'], highlightthickness=0)
        self.radar_display_full.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        radar_right = tk.Frame(radar_body, bg=COLORES["fondo"])
        radar_right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        radar_right.grid_rowconfigure(1, weight=1)
        radar_right.grid_columnconfigure(0, weight=1)

        info_frame = tk.LabelFrame(radar_right, text="📊 INFORMACIÓN DEL RADAR", 
            fg=COLORES["info"], bg=COLORES["fondo_secundario"],
            font=FUENTES['subtitulo'], labelanchor='n')
        info_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        info_frame.grid_columnconfigure(0, weight=1)

        info_content = tk.Frame(info_frame, bg=COLORES["fondo_secundario"])
        info_content.grid(row=0, column=0, sticky="nsew", padx=15, pady=15)
        info_content.grid_columnconfigure(1, weight=1)

        self.radar_metrics = {}
        metrics = [
            ("Objetivos detectados:", "num_targets"), ("Objetivo más cercano:", "target_cercano"),
            ("Distancia promedio:", "dist_promedio"), ("Ángulo principal:", "angulo_principal"),
            ("Velocidad máxima:", "velocidad_max"), ("Objetivos respirando:", "objetivos_respirando"),
            ("Rango de detección:", "rango_deteccion"), ("Campo de visión:", "campo_vision")
        ]

        for i, (texto, clave) in enumerate(metrics):
            tk.Label(info_content, text=texto, bg=COLORES["fondo_secundario"], 
                    fg=COLORES["texto_secundario"], font=FUENTES['normal'], anchor="w"
            ).grid(row=i, column=0, sticky="w", pady=5)
            
            self.radar_metrics[clave] = tk.Label(info_content, text="--",
                bg=COLORES["fondo_secundario"], fg=COLORES["info"],
                font=FUENTES['normal'], anchor="w")
            self.radar_metrics[clave].grid(row=i, column=1, sticky="w", pady=5)

        legend_frame = tk.Frame(info_content, bg=COLORES["fondo_secundario"])
        legend_frame.grid(row=len(metrics), column=0, columnspan=2, sticky="ew", pady=(15, 5))
        
        tk.Label(legend_frame, text="Leyenda de Respiración:", bg=COLORES["fondo_secundario"], 
                fg=COLORES["texto"], font=FUENTES['pequeno']).grid(row=0, column=0, sticky="w")
        
        breathing_legend = tk.Frame(legend_frame, bg=COLORES["fondo_secundario"])
        breathing_legend.grid(row=1, column=0, sticky="w", pady=5)
        
        tk.Label(breathing_legend, text="💨 = Respiración detectada", fg=COLORES["cyan"], 
                bg=COLORES["fondo_secundario"], font=FUENTES['pequeno']).grid(row=0, column=0, sticky="w")
        tk.Label(breathing_legend, text="○ = Sin respiración", fg=COLORES["advertencia"],
                bg=COLORES["fondo_secundario"], font=FUENTES['pequeno']).grid(row=1, column=0, sticky="w", pady=2)

        targets_frame = tk.LabelFrame(radar_right, text="🎯 OBJETIVOS DETECTADOS", 
            fg=COLORES["advertencia"], bg=COLORES["fondo_secundario"],
            font=FUENTES['subtitulo'], labelanchor='n')
        targets_frame.grid(row=1, column=0, sticky="nsew")
        targets_frame.grid_columnconfigure(0, weight=1)
        targets_frame.grid_rowconfigure(0, weight=1)

        self.targets_canvas = tk.Canvas(targets_frame, bg=COLORES["fondo_secundario"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(targets_frame, orient="vertical", command=self.targets_canvas.yview)
        self.scrollable_frame = tk.Frame(self.targets_canvas, bg=COLORES["fondo_secundario"])

        self.scrollable_frame.bind("<Configure>",
            lambda e: self.targets_canvas.configure(scrollregion=self.targets_canvas.bbox("all")))

        self.targets_canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.targets_canvas.configure(yscrollcommand=scrollbar.set)

        self.targets_canvas.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=5)

        targets_frame.grid_rowconfigure(0, weight=1)
        targets_frame.grid_columnconfigure(0, weight=1)

    def crear_pestanas_camara(self):
        pestanas_frame = tk.Frame(self.frame_cam_principal, bg=COLORES["fondo_secundario"])
        pestanas_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        pestanas_frame.grid_columnconfigure(0, weight=1)
        pestanas_frame.grid_columnconfigure(1, weight=1)
        
        self.btn_rgb = tk.Label(pestanas_frame, text="📷 CÁMARA RGB", 
            bg=COLORES["info"], fg=COLORES["texto"], font=FUENTES['pequeno'], 
            relief="raised", padx=20, pady=8, cursor="hand2")
        self.btn_rgb.grid(row=0, column=0, sticky="ew", padx=(0, 2))
        self.btn_rgb.bind("<Button-1>", lambda e: self.cambiar_modo_camara("rgb"))
        
        self.btn_thermal = tk.Label(pestanas_frame, text="🌡️ CÁMARA TÉRMICA", 
            bg=COLORES["fondo"], fg=COLORES["texto_secundario"], font=FUENTES['pequeno'],
            relief="raised", padx=20, pady=8, cursor="hand2")
        self.btn_thermal.grid(row=0, column=1, sticky="ew", padx=(2, 0))
        self.btn_thermal.bind("<Button-1>", lambda e: self.cambiar_modo_camara("thermal"))
        
        self.cam_display_frame = tk.Frame(self.frame_cam_principal, bg=COLORES["fondo_secundario"])
        self.cam_display_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self.cam_display_frame.grid_rowconfigure(0, weight=1)
        self.cam_display_frame.grid_columnconfigure(0, weight=1)
        
        self.lbl_cam_principal = tk.Label(self.cam_display_frame, bg=COLORES["fondo_secundario"], 
                                         text="Seleccione un modo de cámara", fg=COLORES["texto_secundario"])
        self.lbl_cam_principal.grid(row=0, column=0, sticky="nsew")

    def cambiar_modo_camara(self, modo):
        self.current_camera_mode = modo
        if modo == "rgb":
            self.btn_rgb.config(bg=COLORES["info"], fg=COLORES["texto"])
            self.btn_thermal.config(bg=COLORES["fondo"], fg=COLORES["texto_secundario"])
        else:
            self.btn_rgb.config(bg=COLORES["fondo"], fg=COLORES["texto_secundario"])
            self.btn_thermal.config(bg=COLORES["advertencia"], fg=COLORES["texto"])

    def create_control_button(self, parent, text, row, column):
        button = tk.Label(parent, text=text, font=("Segoe UI", 12, "bold"),
                         width=4, height=2, relief="raised", bg=COLORES["fondo"], 
                         fg=COLORES["texto"], cursor="hand2", bd=1)
        button.grid(row=row, column=column, padx=2, pady=2, sticky="nsew")
        button.bind("<ButtonPress-1>", lambda e, t=text.lower(): self.on_control_button(t, True))
        button.bind("<ButtonRelease-1>", lambda e, t=text.lower(): self.on_control_button(t, False))
        button.bind("<Enter>", lambda e, b=button: self.on_button_hover(b, True))
        button.bind("<Leave>", lambda e, b=button: self.on_button_hover(b, False))
        return button

    def on_button_hover(self, button, hover):
        new_bg = COLORES["fondo_secundario"] if hover and button.cget('bg') != COLORES["info"] else COLORES["fondo"]
        button.config(bg=new_bg)

    def on_control_button(self, tecla, presionada):
        if presionada and tecla not in teclas_presionadas:
            teclas_presionadas.add(tecla)
            data_logger.registrar_datos(last_gas, last_distance, persona_detectada, tecla=tecla)
        elif not presionada:
            teclas_presionadas.discard(tecla)
        
        for btn, key in [(self.btn_w, 'w'), (self.btn_a, 'a'), (self.btn_s, 's'), (self.btn_d, 'd')]:
            btn.config(bg=COLORES["info"] if key in teclas_presionadas else COLORES["fondo"])

    def setup_bindings(self):
        self.root.bind('<KeyPress>', self.tecla_presionada)
        self.root.bind('<KeyRelease>', self.tecla_liberada)
        self.root.focus_set()

    def tecla_presionada(self, event):
        tecla = event.char.lower()
        if tecla in ['w', 'a', 's', 'd', 'x'] and tecla not in teclas_presionadas:
            teclas_presionadas.add(tecla)
            self.on_control_button(tecla, True)
            data_logger.registrar_datos(last_gas, last_distance, persona_detectada, tecla=tecla)
                
    def tecla_liberada(self, event):
        tecla = event.char.lower()
        if tecla in teclas_presionadas:
            teclas_presionadas.discard(tecla)
            self.on_control_button(tecla, False)

    def calcular_metricas_radar_completas(self):
        if not last_radar_targets:
            return {k: '0' if k == 'num_targets' or k == 'objetivos_respirando' else '--' 
                   for k in ['num_targets', 'target_cercano', 'dist_promedio', 'angulo_principal', 
                           'velocidad_max', 'objetivos_respirando']} | {'rango_deteccion': '0-7 m', 'campo_vision': '±60°'}
        
        distancias = [t['distance'] for t in last_radar_targets]
        velocidades = [abs(t['speed']) for t in last_radar_targets]
        angulos = [t['angle'] for t in last_radar_targets]
        
        dist_min, dist_promedio = min(distancias), sum(distancias) / len(distancias)
        velocidad_max = max(velocidades) if velocidades else 0
        
        objetivos_respirando = sum(1 for target in last_radar_targets 
                                 if target['num'] in self.radar_display_full.respiration_data 
                                 and self.radar_display_full.respiration_data[target['num']]['breathing_detected'])
        
        angulo_principal = angulos[distancias.index(min(distancias))] if angulos else "--"
        
        return {
            'num_targets': str(len(last_radar_targets)),
            'target_cercano': f"{dist_min*100:.1f} cm",
            'dist_promedio': f"{dist_promedio*100:.1f} cm",
            'angulo_principal': f"{angulo_principal:.1f}°" if angulo_principal != "--" else "--",
            'velocidad_max': f"{velocidad_max:.2f} m/s",
            'objetivos_respirando': str(objetivos_respirando),
            'rango_deteccion': "0-7 m",
            'campo_vision': "±60°"
        }

    def actualizar_lista_objetivos(self):
        for widget in self.scrollable_frame.winfo_children(): widget.destroy()
        
        if not last_radar_targets:
            tk.Label(self.scrollable_frame, text="No hay objetivos detectados",
                    bg=COLORES["fondo_secundario"], fg=COLORES["texto_secundario"],
                    font=FUENTES['normal']).pack(pady=20)
            return
        
        header_frame = tk.Frame(self.scrollable_frame, bg=COLORES["fondo_secundario"])
        header_frame.pack(fill="x", pady=(0, 10))
        
        headers = ["ID", "Distancia", "Ángulo", "Velocidad", "Respiración"]
        for i, header in enumerate(headers):
            tk.Label(header_frame, text=header, bg=COLORES["fondo_secundario"], fg=COLORES["acento"],
                    font=FUENTES['pequeno'], width=12 if i>0 else 6).grid(row=0, column=i, padx=2)
        
        for target in last_radar_targets:
            target_frame = tk.Frame(self.scrollable_frame, bg=COLORES["fondo_secundario"])
            target_frame.pack(fill="x", pady=2)
            
            target_num = target['num']
            if (target_num in self.radar_display_full.respiration_data and 
                self.radar_display_full.respiration_data[target_num]['breathing_detected']):
                color, respiracion = COLORES["cyan"], "💨 SÍ"
            else:
                color, respiracion = COLORES["advertencia"], "○ NO"
            
            datos = [
                str(target['num']+1),
                f"{target['distance']*100:.1f} cm",
                f"{target['angle']:.1f}°", 
                f"{target['speed']:.2f} m/s",
                respiracion
            ]
            
            for i, dato in enumerate(datos):
                tk.Label(target_frame, text=dato, bg=COLORES["fondo_secundario"], 
                        fg=color if i == 0 or i == 4 else COLORES["texto"],
                        font=FUENTES['pequeno'], width=12 if i>0 else 6).grid(row=0, column=i, padx=2)

    def setup_tab_fotos(self):
        """Configura la pestaña de gestión de fotos"""
        # Header
        header = tk.Frame(self.tab_fotos, bg=COLORES["fondo_secundario"], height=50)
        header.pack(fill="x", padx=10, pady=5)
        
        tk.Label(header, text="📸 GESTIÓN DE FOTOS CAPTURADAS",
            bg=COLORES["fondo_secundario"], fg=COLORES["texto"], font=FUENTES['titulo']
        ).pack(side="left", padx=20)

        # Botones de acción
        botones_frame = tk.Frame(header, bg=COLORES["fondo_secundario"])
        botones_frame.pack(side="right", padx=20)
        
        self.btn_actualizar = tk.Label(botones_frame, text="🔄 Actualizar", 
            bg=COLORES["info"], fg=COLORES["texto"], font=FUENTES['pequeno'], 
            relief="raised", padx=15, pady=8, cursor="hand2")
        self.btn_actualizar.pack(side="left", padx=5)
        self.btn_actualizar.bind("<Button-1>", lambda e: self.actualizar_lista_fotos())
        
        self.btn_eliminar_todas = tk.Label(botones_frame, text="🗑️ Eliminar Todas", 
            bg=COLORES["peligro"], fg=COLORES["texto"], font=FUENTES['pequeno'],
            relief="raised", padx=15, pady=8, cursor="hand2")
        self.btn_eliminar_todas.pack(side="left", padx=5)
        self.btn_eliminar_todas.bind("<Button-1>", lambda e: self.eliminar_todas_fotos())
        
        # Cuerpo principal
        cuerpo = tk.Frame(self.tab_fotos, bg=COLORES["fondo"])
        cuerpo.pack(fill="both", expand=True, padx=10, pady=10)
        cuerpo.grid_columnconfigure(0, weight=1)
        cuerpo.grid_columnconfigure(1, weight=2)
        cuerpo.grid_rowconfigure(0, weight=1)

        # Panel izquierdo - Lista de fotos
        lista_frame = tk.LabelFrame(cuerpo, text="📋 LISTA DE FOTOS", 
            fg=COLORES["info"], bg=COLORES["fondo_secundario"],
            font=FUENTES['subtitulo'], labelanchor='n')
        lista_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        lista_frame.grid_rowconfigure(1, weight=1)
        lista_frame.grid_columnconfigure(0, weight=1)

        # Contador de fotos
        self.contador_fotos = tk.Label(lista_frame, text="Cargando...", 
            bg=COLORES["fondo_secundario"], fg=COLORES["texto_secundario"],
            font=FUENTES['normal'])
        self.contador_fotos.grid(row=0, column=0, sticky="w", padx=15, pady=10)

        # Lista con scroll
        lista_container = tk.Frame(lista_frame, bg=COLORES["fondo_secundario"])
        lista_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        self.lista_fotos = tk.Listbox(lista_container, 
            bg=COLORES["fondo"], fg=COLORES["texto"],
            selectbackground=COLORES["info"], selectforeground=COLORES["texto"],
            font=FUENTES['pequeno'], height=20)
        
        scrollbar_lista = ttk.Scrollbar(lista_container, orient="vertical", 
                                      command=self.lista_fotos.yview)
        self.lista_fotos.configure(yscrollcommand=scrollbar_lista.set)
        
        self.lista_fotos.pack(side="left", fill="both", expand=True)
        scrollbar_lista.pack(side="right", fill="y")
        
        self.lista_fotos.bind('<<ListboxSelect>>', self.on_foto_seleccionada)

        # Panel derecho - Vista previa y detalles
        preview_frame = tk.LabelFrame(cuerpo, text="👁️ VISTA PREVIA", 
            fg=COLORES["advertencia"], bg=COLORES["fondo_secundario"],
            font=FUENTES['subtitulo'], labelanchor='n')
        preview_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        preview_frame.grid_rowconfigure(1, weight=1)
        preview_frame.grid_columnconfigure(0, weight=1)

        # Detalles de la foto
        self.detalles_frame = tk.Frame(preview_frame, bg=COLORES["fondo_secundario"])
        self.detalles_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=10)
        self.detalles_frame.grid_columnconfigure(1, weight=1)

        self.detalle_nombre = tk.Label(self.detalles_frame, text="Nombre: -", 
            bg=COLORES["fondo_secundario"], fg=COLORES["texto"], font=FUENTES['pequeno'], anchor="w")
        self.detalle_nombre.grid(row=0, column=0, columnspan=2, sticky="w", pady=2)
        
        self.detalle_fecha = tk.Label(self.detalles_frame, text="Fecha: -", 
            bg=COLORES["fondo_secundario"], fg=COLORES["texto"], font=FUENTES['pequeno'], anchor="w")
        self.detalle_fecha.grid(row=1, column=0, columnspan=2, sticky="w", pady=2)
        
        self.detalle_tamaño = tk.Label(self.detalles_frame, text="Tamaño: -", 
            bg=COLORES["fondo_secundario"], fg=COLORES["texto"], font=FUENTES['pequeno'], anchor="w")
        self.detalle_tamaño.grid(row=2, column=0, columnspan=2, sticky="w", pady=2)

        # Botón eliminar foto seleccionada
        self.btn_eliminar = tk.Label(self.detalles_frame, text="🗑️ Eliminar Foto Seleccionada", 
            bg=COLORES["peligro"], fg=COLORES["texto"], font=FUENTES['pequeno'],
            relief="raised", padx=10, pady=5, cursor="hand2")
        self.btn_eliminar.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.btn_eliminar.bind("<Button-1>", lambda e: self.eliminar_foto_seleccionada())
        self.btn_eliminar.grid_remove()  # Ocultar inicialmente

        # Vista previa de la imagen
        self.preview_container = tk.Frame(preview_frame, bg=COLORES["fondo_secundario"])
        self.preview_container.grid(row=1, column=0, sticky="nsew", padx=15, pady=10)
        self.preview_container.grid_rowconfigure(0, weight=1)
        self.preview_container.grid_columnconfigure(0, weight=1)

        self.lbl_preview = tk.Label(self.preview_container, 
            text="Seleccione una foto para ver la vista previa",
            bg=COLORES["fondo_secundario"], fg=COLORES["texto_secundario"],
            font=FUENTES['normal'])
        self.lbl_preview.grid(row=0, column=0, sticky="nsew")

        # Cargar lista inicial
        self.actualizar_lista_fotos()

    def actualizar_lista_fotos(self):
        """Actualiza la lista de fotos en la interfaz"""
        try:
            fotos = photo_capture.obtener_lista_fotos()
            
            # Actualizar contador
            self.contador_fotos.config(text=f"Total de fotos: {len(fotos)}")
            
            # Limpiar lista
            self.lista_fotos.delete(0, tk.END)
            
            # Limpiar cualquier dato anterior
            if hasattr(self.lista_fotos, 'fotos_data'):
                delattr(self.lista_fotos, 'fotos_data')
            
            # Agregar fotos a la lista
            for foto in fotos:
                nombre_corto = foto['nombre'][:30] + "..." if len(foto['nombre']) > 30 else foto['nombre']
                self.lista_fotos.insert(tk.END, f"{foto['fecha']} - {nombre_corto}")
            
            # Guardar datos completos como atributo de la lista
            self.lista_fotos.fotos_data = fotos
            
            # Forzar actualización de la interfaz
            self.lista_fotos.update_idletasks()
            
            print(f"📸 Lista actualizada: {len(fotos)} fotos")
            
        except Exception as e:
            print(f"❌ Error al actualizar lista de fotos: {e}")
            self.contador_fotos.config(text="Error al cargar fotos")

    def on_foto_seleccionada(self, event):
        """Cuando se selecciona una foto de la lista"""
        seleccion = self.lista_fotos.curselection()
        if not seleccion:
            return
            
        index = seleccion[0]
        fotos_data = getattr(self.lista_fotos, 'fotos_data', [])
        
        if index < len(fotos_data):
            self.foto_seleccionada = fotos_data[index]
            self.mostrar_detalles_foto()
            self.mostrar_vista_previa()

    def mostrar_detalles_foto(self):
        """Muestra los detalles de la foto seleccionada"""
        if not self.foto_seleccionada:
            return
            
        self.detalle_nombre.config(text=f"Nombre: {self.foto_seleccionada['nombre']}")
        self.detalle_fecha.config(text=f"Fecha: {self.foto_seleccionada['fecha']}")
        self.detalle_tamaño.config(text=f"Tamaño: {self.foto_seleccionada['tamaño_kb']}")
        
        # Mostrar botón de eliminar
        self.btn_eliminar.grid()

    def mostrar_vista_previa(self):
        """Muestra la vista previa de la foto seleccionada"""
        if not self.foto_seleccionada:
            return
            
        try:
            # Cargar imagen
            imagen = Image.open(self.foto_seleccionada['ruta'])
            
            # Redimensionar manteniendo aspect ratio
            max_size = (400, 300)
            imagen.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Convertir para tkinter
            img_tk = ImageTk.PhotoImage(imagen)
            
            # Actualizar label
            self.lbl_preview.config(image=img_tk, text="")
            self.lbl_preview.img = img_tk  # Mantener referencia
            
        except Exception as e:
            self.lbl_preview.config(image="", text=f"Error al cargar imagen: {e}")

    def limpiar_vista_previa(self):
        """Limpia la vista previa"""
        self.lbl_preview.config(image="", text="Seleccione una foto para ver la vista previa")
        self.detalle_nombre.config(text="Nombre: -")
        self.detalle_fecha.config(text="Fecha: -")
        self.detalle_tamaño.config(text="Tamaño: -")
        self.btn_eliminar.grid_remove()
        self.foto_seleccionada = None

    def eliminar_foto_seleccionada(self):
        """Elimina la foto seleccionada"""
        if not self.foto_seleccionada:
            return
            
        nombre_foto = self.foto_seleccionada['nombre']
        if messagebox.askyesno("Confirmar eliminación", 
                             f"¿Está seguro de que desea eliminar la foto:\n{nombre_foto}?"):
            if photo_capture.eliminar_foto(self.foto_seleccionada['ruta']):
                messagebox.showinfo("Éxito", "Foto eliminada correctamente")
                self.actualizar_lista_fotos()
                self.limpiar_vista_previa()
            else:
                messagebox.showerror("Error", "No se pudo eliminar la foto")

    def eliminar_todas_fotos(self):
        """Elimina todas las fotos"""
        fotos = photo_capture.obtener_lista_fotos()
        if not fotos:
            messagebox.showinfo("Información", "No hay fotos para eliminar")
            return
            
        if messagebox.askyesno("Confirmar eliminación", 
                             f"¿Está seguro de que desea eliminar TODAS las fotos?\n\nSe eliminarán {len(fotos)} archivos."):
            # Mostrar mensaje de progreso
            self.contador_fotos.config(text="Eliminando fotos...")
            self.root.update()
            
            # Intentar eliminar las fotos
            exito = photo_capture.eliminar_todas_fotos()
            
            if exito:
                messagebox.showinfo("Éxito", f"Todas las fotos han sido eliminadas ({len(fotos)} archivos)")
                # Forzar actualización completa
                self.actualizar_lista_fotos()
                # También resetear la vista previa
                self.limpiar_vista_previa()
            else:
                messagebox.showerror("Error", "No se pudieron eliminar todas las fotos")
                self.actualizar_lista_fotos()

    def mostrar_info_debug(self):
        """Muestra información de debug para las fotos"""
        fotos = photo_capture.obtener_lista_fotos()
        directorio = photo_capture.directorio_fotos
        
        info = f"""📁 Directorio: {directorio}
📊 Fotos en lista: {len(fotos)}
💾 Fotos guardadas (contador): {photo_capture.fotos_guardadas}

Archivos en directorio:"""
        
        try:
            archivos = os.listdir(directorio)
            for archivo in archivos:
                if archivo.lower().endswith(('.jpg', '.jpeg', '.png')):
                    ruta_completa = os.path.join(directorio, archivo)
                    tamaño = os.path.getsize(ruta_completa) / 1024
                    info += f"\n   - {archivo} ({tamaño:.1f} KB)"
        except Exception as e:
            info += f"\n❌ Error al leer directorio: {e}"
        

    def update_gui(self):
        try:
            # ========== VERIFICAR ALARMAS ==========
            gas_detectado = verificar_alarma_gas()
            flama_detectada = verificar_alarma_flama()
            
            # Mostrar/ocultar frames de alarma
            self.alarma_frame.grid() if gas_detectado else self.alarma_frame.grid_remove()
            self.alarma_flama_frame.grid() if flama_detectada else self.alarma_flama_frame.grid_remove()
            
            # ========== ACTUALIZAR CÁMARA (CON MANEJO DE ERRORES ROBUSTO) ==========
            if self.current_camera_mode == "rgb":
                frame_actual = last_cam_frame
                modo_texto = "RGB"
            else:
                frame_actual = last_thermal_frame
                modo_texto = "térmica"
                
            if frame_actual is not None and frame_actual.size > 0:
                try:
                    img_pil = Image.fromarray(frame_actual)
                    img_pil = img_pil.resize((800, 600), Image.Resampling.LANCZOS)
                    img_tk = ImageTk.PhotoImage(img_pil)
                    self.lbl_cam_principal.config(image=img_tk, text="")
                    self.lbl_cam_principal.img = img_tk
                except Exception as e:
                    print(f"⚠️ Error mostrando cámara: {e}")
                    self.lbl_cam_principal.config(image="", text=f"Error mostrando cámara {modo_texto}")
            else:
                self.lbl_cam_principal.config(image="", text=f"Cámara {modo_texto} no disponible")
            
            # ========== ACTUALIZAR RADAR ==========
            if hasattr(self, 'radar_display_full'):
                self.radar_display_full.update_display(last_radar_targets)
                
            # Actualizar métricas de radar
            if hasattr(self, 'radar_metrics'):
                metricas = self.calcular_metricas_radar_completas()
                for clave, valor in metricas.items():
                    if clave in self.radar_metrics:
                        self.radar_metrics[clave].config(text=valor)
                
                self.actualizar_lista_objetivos()
            
            # ========== ACTUALIZAR SENSORES (MÉTODO SEPARADO) ==========
            self.actualizar_sensores_ui()
            
            # ========== CONTROL EV3 ==========
            procesar_control_manual()
            
            # ========== ACTUALIZAR ESTADO GENERAL ==========
            self.actualizar_estado_general()
            
        except Exception as e:
            print(f"❌ Error en update_gui: {e}")
            import traceback
            traceback.print_exc()
        
        # Programar siguiente actualización (30 FPS = 33ms)
        self.root.after(33, self.update_gui)

    def actualizar_sensores_ui(self):
        """Actualiza solo los widgets de sensores en la UI"""
        try:
            # ===== SENSOR DE GAS =====
            self.gas_value.config(text=f"{last_gas:.2f} V")
            gas_percentage = min(last_gas * 20, 100)
            self.gas_bar['value'] = gas_percentage
            
            color_gas = (COLORES["peligro"] if last_gas > 0.65 else 
                        COLORES["advertencia"] if last_gas > 0.45 else COLORES["exito"])
            self.gas_value.config(fg=color_gas)
            
            # ===== SENSOR DE DISTANCIA =====
            self.dist_value.config(text=f"{last_distance * 100:.1f} cm")
            
            # ===== SENSOR DE FLAMA =====
            texto_flama = "🔥 FUEGO DETECTADO" if flame_detected == 1 else "✅ No detectada"
            color_flama = COLORES["advertencia"] if flame_detected == 1 else COLORES["exito"]
            self.flama_value.config(text=texto_flama, fg=color_flama)
            
            # ===== DETECCIÓN DE PERSONAS =====
            texto_persona = "👤 DETECTADO" if persona_detectada else "❌ No detectado"
            color_persona = COLORES["exito"] if persona_detectada else COLORES["peligro"]
            self.persona_value.config(text=texto_persona, fg=color_persona)
            
            # ===== RADAR INFO PRINCIPAL =====
            self.radar_info_principal.config(text=f"{len(last_radar_targets)} objetivos")
            
            # ===== ESTADO EV3 =====
            estado_ev3 = "● EV3 Conectado" if ev3_socket else "● EV3 Desconectado"
            color_ev3 = COLORES['exito'] if ev3_socket else COLORES['peligro']
            self.ev3_status.config(text=estado_ev3, fg=color_ev3)
            self.ev3_status_header.config(text=estado_ev3, fg=color_ev3)
            
        except Exception as e:
            print(f"⚠️ Error actualizando sensores UI: {e}")

    def actualizar_estado_general(self):
        """Actualiza la barra de estado general del sistema"""
        try:
            status_parts = []
            
            # Verificar componentes activos
            if last_cam_frame is not None: 
                status_parts.append("📷 RGB")
            if last_thermal_frame is not None: 
                status_parts.append("🌡️ Térmica")
            if last_gas > 0: 
                status_parts.append("⛽ Sensores")
            if flame_detected == 1: 
                status_parts.append("🔥 Flama")
            if len(last_radar_targets) > 0: 
                status_parts.append("📡 Radar")
            if ev3_socket: 
                status_parts.append("🤖 EV3")
            if alarma_activa: 
                status_parts.append("🚨 ALARMA GAS")
            if alarma_flama_activa: 
                status_parts.append("🔥 ALARMA FLAMA")
            if persona_detectada: 
                status_parts.append("👤 PERSONA")
            
            # Construir mensaje de estado
            nombre_archivo = os.path.basename(data_logger.archivo_csv)
            
            if status_parts:
                status_text = f"✅ Sistema operativo | {' | '.join(status_parts)} | 📊 Registrando en: {nombre_archivo}"
                color_status = COLORES['exito']
            else:
                status_text = "⏳ Conectando a los sistemas..."
                color_status = COLORES['advertencia']
            
            self.status_bar.config(text=status_text, fg=color_status)
            
        except Exception as e:
            print(f"⚠️ Error actualizando estado general: {e}")
            self.status_bar.config(text="❌ Error en estado del sistema", fg=COLORES['peligro'])



# =========================== INICIALIZACIÓN ===========================
if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    
    conectar_ev3()
    
    iniciar_servidor_ia()


    # Lanzar threads de recepción
    threading.Thread(target=lambda: recibir_datos_generico(PORTS['sens'], "sensores", procesar_sensores), daemon=True).start()
    threading.Thread(target=lambda: recibir_datos_generico(PORTS['thermal'], "cámara térmica", procesar_thermal), daemon=True).start()
    threading.Thread(target=lambda: recibir_datos_generico(PORTS['cam'], "cámara RGB", procesar_camera), daemon=True).start()
    threading.Thread(target=lambda: recibir_datos_generico(PORTS['radar'], "radar", procesar_radar), daemon=True).start()
    
    app.update_gui()
    root.mainloop()