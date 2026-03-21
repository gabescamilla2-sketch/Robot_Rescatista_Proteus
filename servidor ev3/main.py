#!/usr/bin/env pybricks-micropython

from pybricks import ev3brick as brick
from pybricks.ev3devices import Motor, UltrasonicSensor
from pybricks.parameters import Port, Stop, Direction, Color
import socket
import time

# Configuración motores y sensor (EV3 maestro)
left_motor_back = Motor(Port.A)
right_motor_back = Motor(Port.B)
left_motor_front = Motor(Port.C, Direction.COUNTERCLOCKWISE)
right_motor_front = Motor(Port.D, Direction.COUNTERCLOCKWISE)

# Conexión servidor (con la PC)
s = socket.socket()
print("Socket creado")
s.bind(('', 12345))
print("Escuchando en puerto 12345")
s.listen(5)

# Conexión cliente (hacia EV3 esclavo)
compuerta_ip = "169.254.88.120"  # IP del EV3 compuerta
compuerta_port = 23456  # ⚠️ CAMBIADO a un puerto distinto para evitar conflicto
compuerta_socket = None

def conectar_a_compuerta():
    global compuerta_socket
    try:
        compuerta_socket = socket.socket()
        compuerta_socket.connect((compuerta_ip, compuerta_port))
        print("✅ Conectado al EV3 compuerta")
    except Exception as e:
        print("❌ Error conectando a compuerta:", e)
        compuerta_socket = None

def enviar_a_compuerta(cmd):
    if compuerta_socket:
        try:
            compuerta_socket.send(bytes([ord(cmd)]))
            print("→ Enviado '{}' a compuerta".format(cmd))
        except Exception as e:
            print("❌ Error enviando a compuerta:", e)

# Funciones de movimiento
def move_all(speed_left, speed_right):
    left_motor_back.run(speed_left)
    left_motor_front.run(speed_left)
    right_motor_back.run(speed_right)
    right_motor_front.run(speed_right)

def stop_all():
    left_motor_back.stop()
    left_motor_front.stop()
    right_motor_back.stop()
    right_motor_front.stop()

# === Bucle principal ===
while True:
    print("Esperando conexión desde PC...")
    connect, addr = s.accept()
    print("Conectado con", addr)

    conectar_a_compuerta()

    try:
        while True:
            rawByte = connect.recv(1)
            if not rawByte:
                print("Cliente desconectado.")
                break

            cmd = rawByte.decode('utf-8')
            print("Recibido:", cmd)

            # Comandos locales (maestro)
            if cmd == "q":
                print("Finalizando conexión...")
                stop_all()
                break

            elif cmd == "a":
                brick.display.text("Avanzar")
                brick.light(Color.GREEN)
                move_all(700, 700)

            elif cmd == "s":
                brick.display.text("Retroceder")
                brick.light(Color.ORANGE)
                move_all(-700, 700)

            elif cmd == "d":
                brick.display.text("Girar derecha")
                brick.light(Color.YELLOW)
                move_all(-700, -700)

            elif cmd == "w":
                brick.display.text("Girar izquierda")
                brick.light(Color.YELLOW)
                move_all(700, -700)

            elif cmd == "x":
                brick.display.text("Parar")
                brick.light(Color.RED)
                stop_all()

            # Comandos para compuerta (EV3 esclavo)
            elif cmd in ["o", "l"]:
                enviar_a_compuerta(cmd)

            else:
                print("Comando no reconocido:", cmd)

    except Exception as e:
        print("❌ Error en conexión:", e)

    finally:
        connect.close()
        if compuerta_socket:
            compuerta_socket.close()
            compuerta_socket = None
        print("Conexión cerrada.")