import socket
import struct
import threading
import numpy as np
import time
import warnings
warnings.filterwarnings('ignore')

class EV3SimpleNavigation:
    def __init__(self, lidar_points=360):
        self.lidar_points = lidar_points
        
        # Conexiones
        self.lidar_socket = None
        self.receptor_socket = None
        self.is_running = False
        
        # Control de comandos - MUY SIMPLE
        self.current_lidar_data = []
        self.last_command = None
        
        # Parámetros de navegación - AJUSTADOS PARA EFICACIA
        self.distancia_segura = 0.6  # 50cm - distancia cómoda
        self.distancia_peligro = 0.4  # 30cm - demasiado cerca
        self.distancia_minima = 0.4   # 20cm - retroceder inmediatamente
        
        # Tiempos de ejecución
        self.tiempo_avance = 1.0      # Avanzar 1 segundo
        self.tiempo_giro = 0.8        # Girar 0.8 segundos
        self.tiempo_retroceso = 0.5   # Retroceder 0.5 segundos
        
        print("🧠 NAVEGACIÓN SUPER SIMPLE - VERSIÓN EFICAZ")

    def connect_to_receptor(self, host='localhost', port=6007):
        """Conectar al receptor de comandos"""
        try:
            self.receptor_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.receptor_socket.settimeout(2.0)
            self.receptor_socket.connect((host, port))
            print(f"✅ Conectado al receptor en {host}:{port}")
            return True
        except Exception as e:
            print(f"❌ Error conectando al receptor: {e}")
            return False

    def send_to_receptor(self, command):
        """Enviar comando al EV3"""
        if self.receptor_socket:
            try:
                self.receptor_socket.sendall(command.encode() + b'\n')
                print(f"🚀 ENVIADO: {command}")
                self.last_command = command
                return True
            except Exception as e:
                print(f"❌ Error enviando comando: {e}")
                return False
        return False

    def send_stop_then_command(self, command):
        """Enviar primero 'x' para detenerse y luego el comando"""
        if self.receptor_socket:
            try:
                # Primero enviar comando de parada 'x'
                self.receptor_socket.sendall('x'.encode() + b'\n')
                print(f"🛑 ENVIADO: x (parada)")
                time.sleep(0.1)  # Pequeña pausa entre comandos
                
                # Luego enviar el comando deseado
                self.receptor_socket.sendall(command.encode() + b'\n')
                print(f"🚀 ENVIADO: {command}")
                self.last_command = command
                return True
            except Exception as e:
                print(f"❌ Error enviando comandos: {e}")
                return False
        return False

    def connect_to_lidar(self, host, port=6005):
        """Conectar al servidor LIDAR"""
        try:
            self.lidar_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.lidar_socket.settimeout(2.0)
            self.lidar_socket.connect((host, port))
            print(f"✅ Conectado al LIDAR en {host}:{port}")
            return True
        except Exception as e:
            print(f"❌ Error conectando al LIDAR: {e}")
            return False

    def receive_lidar_data(self):
        """Recibir datos del LIDAR continuamente"""
        while self.is_running and self.lidar_socket:
            try:
                # Recibir tamaño del paquete
                size_data = self.lidar_socket.recv(4)
                if not size_data:
                    break
                
                packet_size = struct.unpack("I", size_data)[0]
                packet_data = b""
                
                # Recibir paquete completo
                while len(packet_data) < packet_size:
                    chunk = self.lidar_socket.recv(min(4096, packet_size - len(packet_data)))
                    if not chunk:
                        break
                    packet_data += chunk
                
                if len(packet_data) == packet_size:
                    self.process_lidar_packet(packet_data)
                
            except socket.timeout:
                continue
            except Exception as e:
                print(f"❌ Error recibiendo LIDAR: {e}")
                break

    def process_lidar_packet(self, packet_data):
        """Procesar datos del LIDAR"""
        try:
            if len(packet_data) < 14:
                return
            
            # Extraer número de puntos
            num_points = struct.unpack("H", packet_data[12:14])[0]
            points_data = packet_data[14:]
            current_points = []
            
            # Procesar cada punto
            for i in range(num_points):
                start_idx = i * 8
                if start_idx + 8 > len(points_data):
                    break
                
                angle_deg, distance = struct.unpack("ff", points_data[start_idx:start_idx+8])
                current_points.append((0, 0, angle_deg, distance))
            
            self.current_lidar_data = current_points
            
        except Exception as e:
            print(f"❌ Error procesando LIDAR: {e}")

    def debug_lidar_data(self):
        """Función de diagnóstico para ver los datos reales del LIDAR"""
        if not self.current_lidar_data:
            print("📡 No hay datos LIDAR disponibles")
            return
        
        print(f"\n🔍 DIAGNÓSTICO LIDAR - {len(self.current_lidar_data)} puntos:")
        
        # Crear un array de ángulos y distancias
        angles = np.array([point[2] for point in self.current_lidar_data])
        distances = np.array([point[3] for point in self.current_lidar_data])
        
        # Encontrar los puntos más cercanos en cada sector
        def find_closest_in_sector(start_angle, end_angle, sector_name):
            if start_angle > end_angle:
                # Sector que cruza 0°
                mask = (angles >= start_angle) | (angles <= end_angle)
            else:
                mask = (angles >= start_angle) & (angles <= end_angle)
            
            sector_distances = distances[mask]
            sector_angles = angles[mask]
            
            if len(sector_distances) > 0:
                min_idx = np.argmin(sector_distances)
                min_dist = sector_distances[min_idx]
                min_angle = sector_angles[min_idx]
                print(f"   {sector_name}: {min_dist:.2f}m en {min_angle:.1f}°")
            else:
                print(f"   {sector_name}: No data")
        
        # Analizar sectores clave
        find_closest_in_sector(355, 5, "FRENTE (355-5°)")
        find_closest_in_sector(175, 185, "ATRÁS (175-185°)")
        find_closest_in_sector(85, 95, "IZQUIERDA (85-95°)")
        find_closest_in_sector(265, 275, "DERECHA (265-275°)")
        
        # Mostrar las 10 distancias más cercanas
        if len(distances) > 0:
            closest_indices = np.argsort(distances)[:10]
            print(f"\n🎯 10 puntos más cercanos:")
            for idx in closest_indices:
                if distances[idx] < 10.0:  # Solo mostrar distancias reales
                    print(f"   Ángulo: {angles[idx]:6.1f}° - Distancia: {distances[idx]:5.2f}m")

    def analizar_entorno(self):
        """Analizar el entorno en 4 sectores principales"""
        if not self.current_lidar_data:
            return 10.0, 10.0, 10.0, 10.0
        
        # Convertir a arrays de ángulos y distancias
        angles = np.array([point[2] for point in self.current_lidar_data])
        distances = np.array([point[3] for point in self.current_lidar_data])
        
        # Si no hay suficientes datos, rellenar
        if len(distances) < 360:
            angles = np.pad(angles, (0, 360 - len(angles)), 'constant', constant_values=0)
            distances = np.pad(distances, (0, 360 - len(distances)), 'constant', constant_values=10.0)
        
        # Definir sectores CORREGIDOS - basados en ángulos reales
        def get_sector_min(sector_angles, sector_name=""):
            valid_distances = []
            for angle in sector_angles:
                # Encontrar el punto más cercano a este ángulo
                angle_diff = np.abs(angles - angle)
                closest_idx = np.argmin(angle_diff)
                if angle_diff[closest_idx] < 5:  # Tolerancia de 5 grados
                    if distances[closest_idx] > 0 and distances[closest_idx] < 10.0:
                        valid_distances.append(distances[closest_idx])
            
            if valid_distances:
                return min(valid_distances)
            else:
                return 10.0
        
        # Sectores corregidos
        atras_angles = [0, 1, 359, 358]  # Ángulos alrededor de 0°
        frente_angles = [180, 181, 179]     # Ángulos alrededor de 180°
        izquierda_angles = [90, 91, 89]    # Ángulos alrededor de 90°
        derecha_angles = [270, 271, 269]   # Ángulos alrededor de 270°
        
        min_frente = get_sector_min(frente_angles, "FRENTE")
        min_atras = get_sector_min(atras_angles, "ATRAS")
        min_izquierda = get_sector_min(izquierda_angles, "IZQUIERDA")
        min_derecha = get_sector_min(derecha_angles, "DERECHA")
        
        return min_frente, min_izquierda, min_derecha, min_atras

    def tomar_decision_simple(self, frente, izq, der, atras):
        """
        LÓGICA SUPER SIMPLE:
        1. Si hay peligro inmediato → RETROCEDER
        2. Si hay obstáculo cerca → GIRAR
        3. Si está despejado → AVANZAR
        """
        
        # 1. PELIGRO INMINENTE - Retroceder inmediatamente
        if frente < self.distancia_minima:
            print(f"🚨 PELIGRO! Frente: {frente:.2f}m → RETROCEDER")
            return 's', self.tiempo_retroceso
        
        # 2. DEMASIADO CERCA - Girar para evitar
        elif frente < self.distancia_peligro:
            # Verificar qué lado tiene más espacio
            if izq > der and izq > self.distancia_segura:
                print(f"↩️  Obstáculo cerca. Frente: {frente:.2f}m → GIRAR IZQUIERDA")
                return 'a', self.tiempo_giro
            else:
                print(f"↪️  Obstáculo cerca. Frente: {frente:.2f}m → GIRAR DERECHA")
                return 'd', self.tiempo_giro
        
        # 3. OBSTÁCULO EN ZONA SEGURA - Decidir dirección
        elif frente < self.distancia_segura:
            if izq > der:
                print(f"🔄 Camino estrecho. Frente: {frente:.2f}m → GIRAR IZQUIERDA")
                return 'a', self.tiempo_giro
            else:
                print(f"🔄 Camino estrecho. Frente: {frente:.2f}m → GIRAR DERECHA")
                return 'd', self.tiempo_giro
        
        # 4. CAMINO DESPEJADO - Avanzar
        else:
            print(f"✅ Camino despejado. Frente: {frente:.2f}m → AVANZAR")
            return 'w', self.tiempo_avance

    def ejecutar_comando(self, comando, duracion):
        """Ejecutar un comando por un tiempo determinado"""
        if not self.is_running:
            return
            
        # MODIFICACIÓN: Enviar primero 'x' y luego el comando
        self.send_stop_then_command(comando)
        time.sleep(duracion)
        
        # Pequeña pausa entre comandos
        time.sleep(0.1)

    def run_navigation(self, send_commands=False):
        """Bucle principal de navegación"""
        print("🚀 INICIANDO NAVEGACIÓN SUPER SIMPLE")
        print("🎯 Lógica: PELIGRO→Retroceder, CERCA→Girar, LEJOS→Avanzar")
        print("🛑 ESTRATEGIA: Siempre enviar 'x' antes de cualquier movimiento")
        
        ciclo = 0
        
        while self.is_running:
            if not self.current_lidar_data:
                print("📡 Esperando datos LIDAR...")
                if send_commands:
                    # MODIFICACIÓN: Enviar primero 'x' y luego 'w'
                    self.send_stop_then_command('w')  # Avanzar por defecto
                time.sleep(0.5)
                continue
            
            try:
                # Analizar entorno
                frente, izq, der, atras = self.analizar_entorno()
                
                # Mostrar info del entorno
                ciclo += 1
                if ciclo % 10 == 0:  # Mostrar diagnóstico cada 10 ciclos
                    print(f"\n📊 CICLO {ciclo} - Distancias:")
                    print(f"   Frente: {frente:.2f}m | Izq: {izq:.2f}m | Der: {der:.2f}m | Atrás: {atras:.2f}m")
                    self.debug_lidar_data()
                elif ciclo % 3 == 0:  # Info básica cada 3 ciclos
                    print(f"📊 Frente: {frente:.2f}m | Izq: {izq:.2f}m | Der: {der:.2f}m")
                
                # Tomar decisión
                comando, duracion = self.tomar_decision_simple(frente, izq, der, atras)
                
                # Ejecutar comando
                if send_commands:
                    self.ejecutar_comando(comando, duracion)
                else:
                    print(f"💡 SIMULACIÓN: x + {comando} por {duracion:.1f}s")
                    time.sleep(0.5)  # Pausa en simulación
                    
            except Exception as e:
                print(f"❌ Error en ciclo de navegación: {e}")
                time.sleep(0.5)

    def start(self, lidar_host, receptor_host='localhost', send_commands=False):
        """Iniciar sistema completo"""
        print("🤖 SISTEMA DE NAVEGACIÓN SUPER SIMPLE")
        print("=" * 50)
        
        # Conectar al LIDAR
        if not self.connect_to_lidar(lidar_host):
            print("❌ No se pudo conectar al LIDAR")
            return
        
        # Conectar al receptor (opcional)
        if send_commands:
            if not self.connect_to_receptor(receptor_host):
                print("⚠️  Modo solo simulación - No se pudo conectar al receptor")
                send_commands = False
        else:
            print("🔍 Modo simulación - Solo mostrando decisiones")
        
        self.is_running = True
        
        # Hilo para recibir datos LIDAR
        lidar_thread = threading.Thread(target=self.receive_lidar_data, daemon=True)
        lidar_thread.start()
        
        print("⏳ Esperando datos LIDAR...")
        time.sleep(2)
        
        try:
            self.run_navigation(send_commands)
        except KeyboardInterrupt:
            print("\n🛑 Navegación interrumpida por usuario")
        finally:
            self.stop()

    def stop(self):
        """Detener sistema"""
        print("\n🛑 Deteniendo sistema...")
        self.is_running = False
        
        # Enviar comando de parada
        if self.receptor_socket:
            try:
                self.receptor_socket.sendall('x'.encode() + b'\n')
                print("🛑 Comando de parada enviado")
            except:
                pass
            self.receptor_socket.close()
        
        if self.lidar_socket:
            self.lidar_socket.close()
            
        print("✅ Sistema detenido correctamente")

def main():
    print("=" * 60)
    print("🧠 NAVEGACIÓN SUPER SIMPLE - VERSIÓN EFICAZ")
    print("🔍 CON DIAGNÓSTICO LIDAR MEJORADO")
    print("🛑 ESTRATEGIA: x + comando en cada movimiento")
    print("=" * 60)
    
    # Configuración - CAMBIA ESTAS IPs SEGÚN TU CONFIGURACIÓN
    LIDAR_HOST = "192.168.4.1"    # IP de la Raspberry Pi con LIDAR
    RECEPTOR_HOST = "localhost"    # IP del EV3 o localhost para pruebas
    
    # Crear navegador
    navigator = EV3SimpleNavigation()
    
    try:
        # Iniciar navegación (cambia a True para enviar comandos reales)
        navigator.start(LIDAR_HOST, RECEPTOR_HOST, send_commands=True)
    except Exception as e:
        print(f"❌ Error crítico: {e}")
    finally:
        navigator.stop()

if __name__ == "__main__":
    main()