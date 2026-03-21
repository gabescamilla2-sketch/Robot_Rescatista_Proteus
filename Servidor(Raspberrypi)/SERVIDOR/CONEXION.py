import time, socket, struct, threading
import numpy as np, cv2
import board, busio
from gpiozero import DistanceSensor
import adafruit_mlx90640
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
from picamera2 import Picamera2
from ultralytics import YOLO

# ---------------------------
# Sensores
# ---------------------------
# MLX90640
i2c = busio.I2C(board.SCL, board.SDA)
mlx = adafruit_mlx90640.MLX90640(i2c)
mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_16_HZ
thermal_frame = [0] * 768
thermal_norm = np.zeros((24, 32), dtype=np.uint8)

# sensor mq2
ads = ADS.ADS1115(i2c)
chan = AnalogIn(ads, ADS.P0)
gas_voltage = 0.0

# Ultrasónico
ultra = DistanceSensor(echo=27, trigger=17)
distance = 0.0

#sensor de flama esta conectado en dout asi que solo envia 1 y 0
flame_sensor = DigitalInputDevice(18)
flame_detected = 0 #0 porque no detecto, 1 es igual a que hubo deteccion, detecta a 80cm con encendedor

# ---------------------------
# Cámara infrarroja
# ---------------------------
picam2 = Picamera2()
picam2.preview_configuration.main.size = (640, 480)
picam2.preview_configuration.main.format = "RGB888"
picam2.preview_configuration.align()
picam2.configure("preview")
picam2.start()

yolo = YOLO("/home/gab/pi5_entorno/yolov8n_ncnn_model", task="detect")

# ---------------------------
# Radar
# ---------------------------
try:
    from rd03d import RD03D
    
    class RadarServer:
        def __init__(self):
            self.radar = RD03D()
            self.radar.set_multi_mode(True)
            self.last_targets = []
            print("✅ Radar RD03D REAL inicializado correctamente")
            
        def get_radar_data(self):
            """VERSIÓN CORREGIDA - Envía todos los targets con distancia > 0"""
            try:
                self.radar.update()
                targets = []
                targets_found = 0
                
                for i in range(1, 4):  # Targets 1, 2, 3
                    try:
                        target = self.radar.get_target(i)
                        if target and target.distance > 0:
                            targets_found += 1
                            # ❗ CORRECCIÓN CLAVE: Convertir 1,2,3 a 0,1,2
                            target_data = {
                                'num': i - 1,  # 1,2,3 → 0,1,2
                                'distance': target.distance,
                                'angle': target.angle,
                                'speed': target.speed
                            }
                            targets.append(target_data)
                    except Exception as e:
                        # Si falla un target, continuar con los demás
                        continue
                
                # Debug solo si hay targets
                if targets_found > 0:
                    print(f"📡 Radar: {targets_found} target(s) detectados - ", end="")
                    for target in targets:
                        print(f"T{target['num']+1}({target['distance']:.0f}mm, {target['angle']:.1f}°) ", end="")
                    print()
                
                self.last_targets = targets
                return targets
                
            except Exception as e:
                print(f"⚠️ Error general radar: {e}")
                # En caso de error, devolver últimos targets conocidos
                return self.last_targets
    
    radar_server = RadarServer()
        
except ImportError:
    print("❌ ERROR: No se pudo importar RD03D")
    class RadarServer:
        def __init__(self):
            self.last_targets = []
        def get_radar_data(self):
            return self.last_targets
    radar_server = RadarServer()

# ---------------------------
# Hilos de sensores xd
# ---------------------------
def sensor_loop():
    global thermal_norm, gas_voltage, distance, flame_detected
    error_count = 0
    while True:
        try:
            mlx.getFrame(thermal_frame)
            thermal_array = np.array(thermal_frame).reshape(24, 32)
            thermal_norm = cv2.normalize(thermal_array, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
            gas_voltage = chan.voltage
            distance = ultra.distance
            # Leer sensor de flama (0=detecta flama, 1=no detecta - depende del sensor)
            flame_detected = 0 if flame_sensor.value else 1  # Ajusta según tu sensor
            error_count = 0  # Reset counter on success
            time.sleep(0.05)
        except Exception as e:
            error_count += 1
            if error_count % 20 == 0:  # No spammear logs
                print(f"⚠️ Error sensores: {e}")
            time.sleep(0.2)
def sensor_server():
    HOST, PORT = "0.0.0.0", 6000
    while True:
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((HOST, PORT))
            srv.listen(1)
            print(f"🟢 Servidor sensores en puerto {PORT}...")
            conn, addr = srv.accept()
            print(f"📊 Cliente conectado a sensores: {addr}")
            while True:
                # Ahora envía: gas_voltage, distance, flame_detected
                data = struct.pack("ffB", gas_voltage, distance, flame_detected)
                conn.sendall(data)
                
                # Opcional: Log para debugging
                if flame_detected:
                    print(f"🔥 FLAMA DETECTADA! - Gas: {gas_voltage:.2f}V, Distancia: {distance:.2f}m")
                    
                time.sleep(0.05)
        except Exception as e:
            print(f"❌ Error servidor sensores: {e}")
            time.sleep(2)

def thermal_server():
    HOST, PORT = "0.0.0.0", 6001
    while True:
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((HOST, PORT))
            srv.listen(1)
            print(f"🟢 Servidor térmica en puerto {PORT}...")
            conn, addr = srv.accept()
            print(f"🌡️ Cliente conectado a térmica: {addr}")
            while True:
                thermal_colored = cv2.applyColorMap(thermal_norm, cv2.COLORMAP_JET)
                thermal_resized = cv2.resize(thermal_colored, (320, 240))
                _, jpeg = cv2.imencode(".jpg", thermal_resized, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                thermal_bytes = jpeg.tobytes()
                header = struct.pack("I", len(thermal_bytes))
                conn.sendall(header + thermal_bytes)
                time.sleep(0.1)
        except Exception as e:
            print(f"❌ Error servidor térmico: {e}")
            time.sleep(2)

def camera_server():
    HOST, PORT = "0.0.0.0", 6002
    while True:
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((HOST, PORT))
            srv.listen(1)
            print(f"🟢 Servidor cámara en puerto {PORT}...")
            conn, addr = srv.accept()
            print(f"📷 Cliente conectado a cámara: {addr}")
            while True:
                frame_rgb = picam2.capture_array()
                results = yolo(frame_rgb, classes=[0])  # Solo personas (clase 0 = person)
                
                # CONTAR PERSONAS DETECTADAS
                num_personas = len(results[0].boxes) if results[0].boxes else 0
                persona_detectada = 1 if num_personas > 0 else 0  # 1=si, 0=no
                
                # Anotar frame con detecciones
                annotated = results[0].plot()
                
                # Codificar imagen
                _, jpeg = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
                cam_bytes = jpeg.tobytes()
                
                # ENVIAR TAMAÑO DE IMAGEN + DETECCIÓN DE PERSONA
                header = struct.pack("IB", len(cam_bytes), persona_detectada)
                conn.sendall(header + cam_bytes)
                
                # Log de detecciones (solo si hay personas)
                if persona_detectada:
                    print(f"👤 PERSONA DETECTADA - Total: {num_personas}")
                    
                time.sleep(0.033)
        except Exception as e:
            print(f"❌ Error servidor cámara: {e}")
            time.sleep(2)

def radar_data_server():
    HOST, PORT = "0.0.0.0", 6003
    while True:
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((HOST, PORT))
            srv.listen(1)
            print(f"🟢 Servidor radar en puerto {PORT}...")
            conn, addr = srv.accept()
            print(f"📡 Cliente conectado a radar: {addr}")
            while True:
                targets = radar_server.get_radar_data()
                num_targets = len(targets)
                
                # Construir paquete de datos
                data = struct.pack("B", num_targets)
                for target in targets:
                    # ❗ CORRECCIÓN: Usar la numeración corregida (0,1,2)
                    target_data = struct.pack("Bfff", 
                                            target['num'],  # ← Ahora es 0,1,2
                                            target['distance'],
                                            target['angle'], 
                                            target['speed'])
                    data += target_data
                
                conn.sendall(data)
                time.sleep(0.1)
        except Exception as e:
            print(f"❌ Error servidor radar: {e}")
            time.sleep(2)

# ---------------------------
# Lanzar hilos
# ---------------------------
threading.Thread(target=sensor_loop, daemon=True).start()
threading.Thread(target=sensor_server, daemon=True).start()
threading.Thread(target=thermal_server, daemon=True).start()
threading.Thread(target=camera_server, daemon=True).start()
threading.Thread(target=radar_data_server, daemon=True).start()

print("=" * 60)
print("🚀 SERVIDORES INICIADOS - VERSIÓN CORREGIDA 🚀")
print("=" * 60)
print("📊 Puerto 6000: Sensores MQ2 + Ultrasónico")
print("🌡️ Puerto 6001: Cámara Térmica MLX90640") 
print("📷 Puerto 6002: Cámara RGB + YOLO Person Detection")
print("📡 Puerto 6003: Radar RD03D (MÚLTIPLES OBJETIVOS ✅)")
print("=" * 60)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n🛑 Cerrando servidores...")
    try:
        picam2.stop()
    except:
        pass
    print("✅ Servidores detenidos correctamente")