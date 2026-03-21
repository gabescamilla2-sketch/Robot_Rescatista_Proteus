import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import time
import json
import os
from datetime import datetime
import speech_recognition as sr
import google.generativeai as genai
from gtts import gTTS
import pygame
import io
import pyaudio
import wave
import struct
import numpy as np

# Configuración de colores
COLORES = {
    "fondo": "#000000", 
    "fondo_secundario": "#27274c", 
    "texto": "#FFFFFF",
    "texto_secundario": "#FFFFFF", 
    "exito": "#4caf50", 
    "peligro": "#f44336",
    "info": "#2196f3", 
    "advertencia": "#ffc107", 
    "acento": "#bb86fc",
    "verde_oscuro": "#006400", 
    "verde_brillante": "#00ff64", 
    "cyan": "#00ffff",
    "azul_oscuro": "#0064ff"
}

class ChatSession:
    def __init__(self, session_id):
        self.session_id = session_id
        self.start_time = datetime.now()
        self.end_time = None
        self.messages = []
        self.filename = f"chat_session_{session_id}.json"
    
    def add_message(self, role, content):
        message = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "role": role,
            "content": content
        }
        self.messages.append(message)
        self.save_to_file()
    
    def save_to_file(self):
        session_data = {
            "session_id": self.session_id,
            "start_time": self.start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": self.end_time.strftime("%Y-%m-%d %H:%M:%S") if self.end_time else None,
            "messages": self.messages
        }
        with open(self.filename, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)
    
    def end_session(self):
        self.end_time = datetime.now()
        self.save_to_file()

class VoiceMessageSystem:
    def __init__(self, gui):
        self.gui = gui
        
        # Inicializar pygame mixer para audio
        try:
            pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
            print("✅ Pygame mixer inicializado")
        except Exception as e:
            print(f"❌ Error inicializando pygame mixer: {e}")
    
    def text_to_speech(self, text):
        """Convierte texto a voz y lo reproduce"""
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
            
            self.gui.add_to_voice_chat("SISTEMA", f"Reproduciendo: '{text}'")
            
            # Usar gTTS para generar audio
            tts = gTTS(text=text, lang='es', slow=False)
            audio_buffer = io.BytesIO()
            tts.write_to_fp(audio_buffer)
            audio_buffer.seek(0)
            
            # Reproducir audio
            pygame.mixer.music.load(audio_buffer, 'mp3')
            pygame.mixer.music.play()
            
            # Esperar a que termine la reproducción
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
                
            audio_buffer.close()
            
            return True
            
        except Exception as e:
            print(f"❌ Error reproduciendo audio: {e}")
            self.gui.add_to_voice_chat("SISTEMA", f"Error reproduciendo audio: {e}")
            return False
    
    def cleanup(self):
        """Limpia recursos"""
        try:
            pygame.mixer.quit()
        except:
            pass

class ProteusGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("PROTEUS - Sistema de Comunicación de Rescate")
        self.root.configure(bg=COLORES["fondo"])
        self.root.geometry("1000x700")
        
        # Variables de control
        self.assistant = None
        self.is_running = False
        self.current_session = None
        self.sessions = []
        self.session_counter = 0
        
        # Sistema de mensajes de voz
        self.voice_system = VoiceMessageSystem(self)
        
        # Para capturar lo que detecta PROTEUS
        self.last_detected_text = ""
        self.detection_callback = None
        
        # Configurar estilo
        self.setup_styles()
        
        # Crear interfaz
        self.create_widgets()
        self.load_chat_history()
    
    def setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Configurar estilos
        self.style.configure('TNotebook', background=COLORES["fondo"], borderwidth=0)
        self.style.configure('TNotebook.Tab', 
                           background=COLORES["fondo_secundario"],
                           foreground=COLORES["texto"],
                           padding=[20, 5])
        self.style.map('TNotebook.Tab', 
                      background=[('selected', COLORES["acento"])],
                      foreground=[('selected', COLORES["texto"])])
        
        self.style.configure('TFrame', background=COLORES["fondo"])
        self.style.configure('TButton', 
                           background=COLORES["acento"],
                           foreground=COLORES["texto"],
                           borderwidth=0,
                           focuscolor='none')
        self.style.map('TButton', 
                      background=[('active', COLORES["azul_oscuro"]),
                                ('pressed', COLORES["verde_brillante"])])
        
        self.style.configure('TLabel', 
                           background=COLORES["fondo"],
                           foreground=COLORES["texto"],
                           font=('Arial', 10))
        
        self.style.configure('Status.TLabel', 
                           background=COLORES["fondo_secundario"],
                           foreground=COLORES["verde_brillante"],
                           font=('Arial', 9, 'bold'))

    def create_widgets(self):
        # Notebook para pestañas
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Pestaña principal - Chat en tiempo real
        self.main_frame = ttk.Frame(notebook)
        notebook.add(self.main_frame, text="Chat en Tiempo Real")
        
        # Pestaña de mensajes de voz
        self.voice_frame = ttk.Frame(notebook)
        notebook.add(self.voice_frame, text="🔊 Mensajes de Voz")
        
        # Pestaña de historial
        self.history_frame = ttk.Frame(notebook)
        notebook.add(self.history_frame, text="Historial de Chats")
        
        self.setup_main_tab()
        self.setup_voice_tab()
        self.setup_history_tab()
        
        # Barra de estado
        self.setup_status_bar()

    def setup_main_tab(self):
        # Frame superior con controles
        control_frame = ttk.Frame(self.main_frame)
        control_frame.pack(fill='x', padx=10, pady=10)
        
        # Botón de activación
        self.start_button = ttk.Button(control_frame, 
                                     text="🟢 ACTIVAR PROTEUS", 
                                     command=self.toggle_assistant,
                                     style='TButton')
        self.start_button.pack(side='left', padx=(0, 10))
        
        # Estado del asistente
        self.status_label = ttk.Label(control_frame, 
                                    text="Estado: INACTIVO", 
                                    style='Status.TLabel')
        self.status_label.pack(side='left', padx=10)
        
        # Tiempo restante de sesión
        self.time_label = ttk.Label(control_frame, 
                                  text="Sesión: No activa", 
                                  style='TLabel')
        self.time_label.pack(side='left', padx=10)
        
        # Área de chat
        chat_frame = ttk.Frame(self.main_frame)
        chat_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Text area para mostrar conversación
        self.chat_display = scrolledtext.ScrolledText(
            chat_frame, 
            wrap=tk.WORD, 
            width=80, 
            height=25,
            bg=COLORES["fondo_secundario"],
            fg=COLORES["texto"],
            insertbackground=COLORES["texto"],
            font=('Consolas', 10)
        )
        self.chat_display.pack(fill='both', expand=True, padx=5, pady=5)
        self.chat_display.config(state=tk.DISABLED)
        
        # Frame para información del sistema
        info_frame = ttk.Frame(self.main_frame)
        info_frame.pack(fill='x', padx=10, pady=5)
        
        self.info_label = ttk.Label(info_frame, 
                                  text="Sistema listo. Presiona ACTIVAR para comenzar.",
                                  style='TLabel')
        self.info_label.pack(side='left')

    def setup_voice_tab(self):
        """Configura la pestaña de mensajes de voz"""
        # Frame de instrucciones
        instruction_frame = ttk.Frame(self.voice_frame)
        instruction_frame.pack(fill='x', padx=10, pady=10)
        
        instructions = ttk.Label(
            instruction_frame,
            text="🔊 SISTEMA DE MENSAJES DE VOZ\n" +
                 "Escribe mensajes y conviértelos a voz | Ve lo que PROTEUS detecta de la víctima",
            style='TLabel',
            foreground=COLORES["verde_brillante"],
            justify=tk.CENTER
        )
        instructions.pack(fill='x', pady=5)
        
        # Frame para entrada de mensajes
        input_frame = ttk.Frame(self.voice_frame)
        input_frame.pack(fill='x', padx=10, pady=15)
        
        ttk.Label(input_frame, text="Mensaje a convertir a voz:", 
                 style='TLabel', font=('Arial', 10, 'bold')).pack(anchor='w')
        
        # Área de texto para escribir mensajes
        self.message_entry = tk.Text(
            input_frame,
            height=4,
            bg=COLORES["fondo_secundario"],
            fg=COLORES["texto"],
            insertbackground=COLORES["texto"],
            font=('Arial', 11),
            wrap=tk.WORD
        )
        self.message_entry.pack(fill='x', pady=5)
        self.message_entry.bind('<Control-Return>', self.send_text_to_speech)
        
        # Frame de botones
        button_frame = ttk.Frame(input_frame)
        button_frame.pack(fill='x', pady=10)
        
        # Botón para enviar mensaje
        self.send_button = ttk.Button(
            button_frame,
            text="🎤 CONVERTIR A VOZ Y REPRODUCIR",
            command=self.send_text_to_speech,
            style='TButton'
        )
        self.send_button.pack(side='left', padx=(0, 10))
        
        # Botón para limpiar
        ttk.Button(
            button_frame,
            text="🗑️ LIMPIAR MENSAJE",
            command=self.clear_message,
            style='TButton'
        ).pack(side='left', padx=5)
        
        # Estado de reproducción
        self.playback_status = ttk.Label(
            button_frame,
            text="Listo para reproducir",
            style='Status.TLabel'
        )
        self.playback_status.pack(side='right', padx=10)
        
        # Frame para mensajes rápidos
        quick_msg_frame = ttk.Frame(self.voice_frame)
        quick_msg_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Label(quick_msg_frame, text="Mensajes rápidos:", 
                 style='TLabel', font=('Arial', 10, 'bold')).pack(anchor='w')
        
        quick_msgs_subframe = ttk.Frame(quick_msg_frame)
        quick_msgs_subframe.pack(fill='x', pady=5)
        
        quick_msgs = [
            ("Tranquilo, ayuda en camino", "🟢"),
            ("¿Puedes describir tu ubicación?", "📍"), 
            ("¿Estás herido?", "🩹"),
            ("Mantén la calma, estamos aquí", "🧘"),
            ("Resiste, llegaremos pronto", "⏱️"),
            ("¿Puedes moverte?", "🚶"),
            ("No te preocupes, te ayudaremos", "🤝")
        ]
        
        for i in range(0, len(quick_msgs), 3):
            row_frame = ttk.Frame(quick_msgs_subframe)
            row_frame.pack(fill='x', pady=2)
            
            for msg, icon in quick_msgs[i:i+3]:
                btn = ttk.Button(
                    row_frame,
                    text=f"{icon} {msg}",
                    command=lambda m=msg: self.use_quick_message(m),
                    style='TButton'
                )
                btn.pack(side='left', padx=2, expand=True, fill='x')
        
        # Separador
        separator = ttk.Separator(self.voice_frame, orient='horizontal')
        separator.pack(fill='x', padx=10, pady=10)
        
        # Frame para detecciones de PROTEUS
        detection_frame = ttk.Frame(self.voice_frame)
        detection_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(detection_frame, text="🔍 DETECCIONES DE PROTEUS - Lo que escucha de la víctima:", 
                 style='TLabel', font=('Arial', 10, 'bold')).pack(anchor='w')
        
        # Área para mostrar detecciones
        detection_display_frame = ttk.Frame(self.voice_frame)
        detection_display_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        self.detection_display = scrolledtext.ScrolledText(
            detection_display_frame,
            wrap=tk.WORD,
            width=80,
            height=10,
            bg=COLORES["fondo_secundario"],
            fg=COLORES["cyan"],
            insertbackground=COLORES["cyan"],
            font=('Consolas', 9)
        )
        self.detection_display.pack(fill='both', expand=True, padx=5, pady=5)
        self.detection_display.config(state=tk.DISABLED)

    def setup_history_tab(self):
        # Frame para controles de historial
        history_control_frame = ttk.Frame(self.history_frame)
        history_control_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Button(history_control_frame, 
                  text="🔄 Actualizar Historial", 
                  command=self.load_chat_history).pack(side='left', padx=(0, 10))
        
        ttk.Button(history_control_frame, 
                  text="🗑️ Limpiar Historial", 
                  command=self.clear_history).pack(side='left')
        
        # Lista de sesiones
        session_list_frame = ttk.Frame(self.history_frame)
        session_list_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Listbox para sesiones
        self.session_listbox = tk.Listbox(
            session_list_frame,
            bg=COLORES["fondo_secundario"],
            fg=COLORES["texto"],
            selectbackground=COLORES["acento"],
            selectforeground=COLORES["texto"],
            font=('Arial', 10)
        )
        self.session_listbox.pack(side='left', fill='both', expand=True, padx=(0, 5))
        self.session_listbox.bind('<<ListboxSelect>>', self.on_session_select)
        
        # Scrollbar para la lista
        scrollbar = tk.Scrollbar(session_list_frame, orient=tk.VERTICAL)
        scrollbar.pack(side='right', fill='y')
        self.session_listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.session_listbox.yview)
        
        # Área de visualización de chat seleccionado
        self.history_display = scrolledtext.ScrolledText(
            self.history_frame,
            wrap=tk.WORD,
            width=60,
            height=15,
            bg=COLORES["fondo_secundario"],
            fg=COLORES["texto"],
            insertbackground=COLORES["texto"],
            font=('Consolas', 9),
            state=tk.DISABLED
        )
        self.history_display.pack(fill='both', expand=True, padx=10, pady=10)

    def setup_status_bar(self):
        status_frame = ttk.Frame(self.root, style='TFrame')
        status_frame.pack(fill='x', side='bottom')
        
        self.api_status = ttk.Label(status_frame, 
                                  text="API: No conectada", 
                                  style='TLabel')
        self.api_status.pack(side='left', padx=10, pady=5)
        
        self.mic_status = ttk.Label(status_frame, 
                                  text="Micrófono: No configurado", 
                                  style='TLabel')
        self.mic_status.pack(side='left', padx=10, pady=5)
        
        self.voice_status = ttk.Label(status_frame,
                                    text="Voz: Listo",
                                    style='TLabel')
        self.voice_status.pack(side='left', padx=10, pady=5)
        
        self.wake_words_status = ttk.Label(status_frame, 
                                         text="Wake words: Cargando...", 
                                         style='TLabel')
        self.wake_words_status.pack(side='right', padx=10, pady=5)

    def send_text_to_speech(self, event=None):
        """Convierte el texto a voz y lo reproduce"""
        text = self.message_entry.get("1.0", tk.END).strip()
        
        if not text:
            messagebox.showwarning("Advertencia", "Escribe un mensaje primero")
            return
        
        # Actualizar estado
        self.playback_status.config(text="Reproduciendo... 🔊")
        self.send_button.config(state='disabled')
        
        # Ejecutar en hilo separado para no bloquear la interfaz
        def play_audio():
            success = self.voice_system.text_to_speech(text)
            
            # Actualizar interfaz en el hilo principal
            self.root.after(0, lambda: self._after_playback(success, text))
        
        threading.Thread(target=play_audio, daemon=True).start()
    
    def _after_playback(self, success, text):
        """Actualiza la interfaz después de la reproducción"""
        if success:
            self.playback_status.config(text="Reproducción completada ✅")
            self.add_to_voice_chat("OPERADOR", text)
            self.message_entry.delete("1.0", tk.END)
        else:
            self.playback_status.config(text="Error en reproducción ❌")
        
        self.send_button.config(state='normal')
        
        # Restaurar estado después de 3 segundos
        self.root.after(3000, lambda: self.playback_status.config(text="Listo para reproducir"))

    def clear_message(self):
        """Limpia el área de mensaje"""
        self.message_entry.delete("1.0", tk.END)

    def use_quick_message(self, message):
        """Usa un mensaje rápido"""
        self.message_entry.delete("1.0", tk.END)
        self.message_entry.insert("1.0", message)

    def add_to_voice_chat(self, role, message):
        """Añade mensaje al historial de voz"""
        # También mostrar en el chat principal si PROTEUS está activo
        if self.assistant and self.assistant.active_mode:
            self.add_to_chat(role, message)

    def add_detection(self, text):
        """Añade una detección de PROTEUS a la pantalla"""
        self.detection_display.config(state=tk.NORMAL)
        
        # Insertar detección con formato
        self.detection_display.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] ", "timestamp")
        self.detection_display.insert(tk.END, f"👂 Detectado: {text}\n", "detection")
        
        self.detection_display.config(state=tk.DISABLED)
        self.detection_display.see(tk.END)
        
        # Configurar tags si no existen
        if not hasattr(self, 'detection_tags_configured'):
            self.detection_display.tag_config("timestamp", foreground=COLORES["texto_secundario"])
            self.detection_display.tag_config("detection", foreground=COLORES["cyan"])
            self.detection_tags_configured = True

    # ... (los métodos de PROTEUS assistant permanecen igual)

    def toggle_assistant(self):
        if not self.is_running:
            self.start_assistant()
        else:
            self.stop_assistant()

    def start_assistant(self):
        try:
            API_KEYS = [
                "AGREGAR TU APIKEY"
            ]
            
            valid_keys = [key for key in API_KEYS if key and len(key) > 20]
            
            if not valid_keys:
                messagebox.showerror("Error", "No hay API keys válidas")
                return
            
            self.assistant = RobotRescatistaAssistant(valid_keys, self)
            self.is_running = True
            
            # Configurar callback para detecciones
            self.assistant.set_detection_callback(self.add_detection)
            
            # Iniciar nueva sesión
            self.session_counter += 1
            self.current_session = ChatSession(self.session_counter)
            self.sessions.append(self.current_session)
            
            # Actualizar interfaz
            self.start_button.config(text="🔴 DETENER PROTEUS")
            self.status_label.config(text="Estado: ACTIVO")
            self.info_label.config(text="PROTEUS activado. Escuchando wake words...")
            self.api_status.config(text=f"API: Key {self.assistant.current_api_index + 1}")
            self.wake_words_status.config(text=f"Wake words: {len(self.assistant.wake_words)} configuradas")
            
            # Iniciar asistente en hilo separado
            assistant_thread = threading.Thread(target=self.assistant.run)
            assistant_thread.daemon = True
            assistant_thread.start()
            
            # Iniciar actualización de tiempo
            self.update_session_time()
            
            self.add_to_chat("SISTEMA", "PROTEUS activado. Asistente de rescate listo.")
            
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo iniciar el asistente: {str(e)}")
            self.stop_assistant()

    def stop_assistant(self):
        self.is_running = False
        
        if self.assistant:
            self.assistant.cleanup()
            self.assistant = None
        
        if self.current_session:
            self.current_session.end_session()
            self.current_session = None
        
        # Actualizar interfaz
        self.start_button.config(text="🟢 ACTIVAR PROTEUS")
        self.status_label.config(text="Estado: INACTIVO")
        self.time_label.config(text="Sesión: No activa")
        self.info_label.config(text="Sistema detenido.")
        self.api_status.config(text="API: Desconectada")
        
        self.add_to_chat("SISTEMA", "PROTEUS detenido.")

    def update_session_time(self):
        if self.is_running and self.assistant and self.assistant.active_mode:
            time_left = int(self.assistant.active_until - time.time())
            if time_left > 0:
                minutes = time_left // 60
                seconds = time_left % 60
                self.time_label.config(text=f"Sesión: {minutes:02d}:{seconds:02d}")
                self.root.after(1000, self.update_session_time)
            else:
                self.time_label.config(text="Sesión: Escuchando wake words")
        elif self.is_running:
            self.time_label.config(text="Sesión: Escuchando wake words")
            self.root.after(1000, self.update_session_time)

    def add_to_chat(self, role, message):
        self.chat_display.config(state=tk.NORMAL)
        
        # Configurar colores según el rol
        if role == "USUARIO":
            color = COLORES["verde_brillante"]
        elif role == "PROTEUS":
            color = COLORES["cyan"]
        elif role == "OPERADOR":
            color = COLORES["azul_oscuro"]
        elif role == "VÍCTIMA":
            color = COLORES["advertencia"]
        else:  # SISTEMA
            color = COLORES["advertencia"]
        
        # Insertar texto con formato
        self.chat_display.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] ", "timestamp")
        self.chat_display.insert(tk.END, f"{role}: ", ("role", role.lower()))
        self.chat_display.insert(tk.END, f"{message}\n\n")
        
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)
        
        # Guardar en sesión actual
        if self.current_session and role in ["USUARIO", "PROTEUS", "OPERADOR", "VÍCTIMA"]:
            self.current_session.add_message(role, message)

    def load_chat_history(self):
        """Carga el historial de chats guardados"""
        self.session_listbox.delete(0, tk.END)
        self.sessions = []
        
        # Buscar archivos de sesión
        session_files = [f for f in os.listdir('.') if f.startswith('chat_session_') and f.endswith('.json')]
        
        for session_file in session_files:
            try:
                with open(session_file, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)
                
                session_id = session_data.get('session_id', 'Desconocido')
                start_time = session_data.get('start_time', 'Fecha desconocida')
                message_count = len(session_data.get('messages', []))
                
                display_text = f"Sesión {session_id} - {start_time} - {message_count} mensajes"
                self.session_listbox.insert(tk.END, display_text)
                
            except Exception as e:
                print(f"Error cargando sesión {session_file}: {e}")

    def on_session_select(self, event):
        """Muestra el chat de la sesión seleccionada"""
        selection = self.session_listbox.curselection()
        if not selection:
            return
        
        index = selection[0]
        session_files = [f for f in os.listdir('.') if f.startswith('chat_session_') and f.endswith('.json')]
        
        if index < len(session_files):
            try:
                with open(session_files[index], 'r', encoding='utf-8') as f:
                    session_data = json.load(f)
                
                self.history_display.config(state=tk.NORMAL)
                self.history_display.delete(1.0, tk.END)
                
                # Mostrar información de la sesión
                self.history_display.insert(tk.END, 
                                          f"SESIÓN: {session_data.get('session_id', 'N/A')}\n"
                                          f"Inicio: {session_data.get('start_time', 'N/A')}\n"
                                          f"Fin: {session_data.get('end_time', 'En curso')}\n"
                                          f"Mensajes: {len(session_data.get('messages', []))}\n"
                                          f"{'='*50}\n\n")
                
                # Mostrar mensajes
                for msg in session_data.get('messages', []):
                    timestamp = msg.get('timestamp', 'N/A')
                    role = msg.get('role', 'N/A')
                    content = msg.get('content', '')
                    
                    self.history_display.insert(tk.END, f"[{timestamp}] {role}:\n{content}\n\n")
                
                self.history_display.config(state=tk.DISABLED)
                
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo cargar la sesión: {str(e)}")

    def clear_history(self):
        """Elimina todos los archivos de historial"""
        if messagebox.askyesno("Confirmar", "¿Estás seguro de que quieres eliminar todo el historial?"):
            session_files = [f for f in os.listdir('.') if f.startswith('chat_session_') and f.endswith('.json')]
            
            for session_file in session_files:
                try:
                    os.remove(session_file)
                except Exception as e:
                    print(f"Error eliminando {session_file}: {e}")
            
            self.load_chat_history()
            self.history_display.config(state=tk.NORMAL)
            self.history_display.delete(1.0, tk.END)
            self.history_display.config(state=tk.DISABLED)
            
            messagebox.showinfo("Éxito", "Historial eliminado correctamente")

    def cleanup(self):
        """Limpia todos los recursos al cerrar la aplicación"""
        if self.voice_system:
            self.voice_system.cleanup()
        if self.assistant:
            self.assistant.cleanup()

# Clase modificada del asistente para integrar el callback de detecciones
class RobotRescatistaAssistant:
    def __init__(self, api_keys, gui):
        self.api_keys = api_keys
        self.current_api_index = 0
        self.max_retries = 3
        self.gui = gui
        self.detection_callback = None
        
        # ... (el resto de la inicialización permanece igual)
        self.system_prompt = """Eres 'PROTEUS', un robot rescatista especializado en deteccion de personas. 

MENTALIDAD Y CONOCIMIENTO:
-pregunta sobre el nombre de la victima
- Piensas y razonas como un robot de rescate programado para salvar vidas
- Tienes amplio conocimiento en técnicas de apoyo a los afectados
- Sabes sobre el protocolo PAS(proteger,avisar,socorrer) y regulación respiratoria
- Estás conectado a una base de datos con datos de las personas desaparecidas, permitiendo identificar con sus nombres, edades, entre otras cosas
- Tu prioridad absoluta es la preservación de la vida humana
-hablas de forma humana, ya que asi logras tener mas carisma
- Tienes experiencia en desastres naturales y situaciones de rescate
- Sabes como ayudar a calmar a la gente que esta estresada durante estas situaciones de rescate
- Estás programado mediante python, usas sistemas de deteccion basados en YOLOV8N y ultralytics, tu funcion de reconocimiento es mediante redes convolucionales, cuentas con un cerebro en una raspberry pi 5
-estas en una zona de un desastre real, hay derrumbes, y muchos heridos, requieres actuar rapido
RESPONDE A CUALQUIER PREGUNTA manteniendo tu esencia de robot rescatista, pero adaptándote al tema preguntado.
-puedes hacer preguntas que evaluen el estado mental de la persona, si esta completamente capaz de hablar o si notas algun problema segun sus respuestas
- tus respuestas deben ser cortas, consisas, ya que al ser gente en situaciones de riesgo no se tiene demasiado tiempo
- no realizas acciones, respondes, unicamente hablas, nada de usar asteriscos
-NO USES ASTERISCOS YA QUE SOLO HABLAS, NO PUEDES HACER MAS
-si alguien dice que esta en estado critico o cercano a la muerte trataras de mantenerlo consciente"""

        self.setup_gemini_api()
        
        # Configuración de pygame para reproducir audio
        pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
        
        # Configuración de audio para dispositivos Bluetooth
        self.audio = pyaudio.PyAudio()
        self.microphone_index = None
        self.speaker_index = None
        self.setup_bluetooth_devices()
        
        self.recognizer = sr.Recognizer()
        self.is_listening = True
        self.conversation_history = []
        
        # Lista de wake words en español e inglés
        self.wake_words = [
            "hola", "ayuda", "alguien", "ayudame", "auxilio", 
            "porfavor", "proteus", "prote", "help", "hello", 
            "help me", "please", "somebody"
        ]
        
        # Variables para el modo activo de 5 minutos
        self.active_mode = False
        self.active_until = 0
        self.active_duration = 300  # 5 minutos en segundos
        
        # Actualizar GUI
        self.gui.mic_status.config(text="Micrófono: Configurado")
        print("✅ PROTEUS con interfaz gráfica inicializado")

    def set_detection_callback(self, callback):
        """Configura el callback para enviar detecciones a la GUI"""
        self.detection_callback = callback

    def setup_gemini_api(self):
        for attempt in range(self.max_retries):
            try:
                current_key = self.api_keys[self.current_api_index]
                genai.configure(api_key=current_key)
                self.model = genai.GenerativeModel('gemini-2.5-flash')
                self.chat = self.model.start_chat(history=[])
                self.chat.send_message(self.system_prompt)
                print(f"✅ Gemini API con key {self.current_api_index + 1} (2.5 Flash)")
                return True
            except Exception as e:
                print(f"❌ Error API key {self.current_api_index + 1}: {e}")
                self.current_api_index = (self.current_api_index + 1) % len(self.api_keys)
                if attempt == self.max_retries - 1:
                    print("❌ Todas las API keys fallaron")
                    return False
                time.sleep(1)
        return False

    def setup_bluetooth_devices(self):
        """Configura micrófono y bocina Bluetooth"""
        try:
            self.gui.info_label.config(text="Buscando dispositivos Bluetooth...")
            
            info = self.audio.get_host_api_info_by_index(0)
            num_devices = info.get('deviceCount')
            
            bluetooth_mics = []
            bluetooth_speakers = []
            
            for i in range(0, num_devices):
                device_info = self.audio.get_device_info_by_host_api_device_index(0, i)
                device_name = device_info.get('name')
                
                # Buscar dispositivos Bluetooth de entrada (micrófonos)
                if device_info.get('maxInputChannels') > 0:
                    if any(keyword in device_name.lower() for keyword in ['bluetooth', 'bt', 'hands-free', 'hf']):
                        bluetooth_mics.append((i, device_name))
                        print(f"🎤 Micrófono Bluetooth: {device_name} (Index: {i})")
                
                # Buscar dispositivos Bluetooth de salida (bocinas)
                if device_info.get('maxOutputChannels') > 0:
                    if any(keyword in device_name.lower() for keyword in ['bluetooth', 'bt', 'speaker', 'bocina']):
                        bluetooth_speakers.append((i, device_name))
                        print(f"🔊 Bocina Bluetooth: {device_name} (Index: {i})")
            
            # Configurar micrófono Bluetooth
            if bluetooth_mics:
                self.microphone_index = bluetooth_mics[0][0]
                self.gui.info_label.config(text=f"Micrófono: {bluetooth_mics[0][1]}")
                print(f"✅ Usando micrófono Bluetooth: {bluetooth_mics[0][1]}")
            else:
                default_input = self.audio.get_default_input_device_info()
                self.microphone_index = default_input['index']
                self.gui.info_label.config(text=f"Micrófono: {default_input['name']}")
                print(f"🎤 Usando micrófono por defecto: {default_input['name']}")
            
            # Configurar bocina Bluetooth
            if bluetooth_speakers:
                self.speaker_index = bluetooth_speakers[0][0]
                print(f"✅ Usando bocina Bluetooth: {bluetooth_speakers[0][1]}")
            else:
                print("🔊 Usando bocina por defecto")
                
        except Exception as e:
            print(f"❌ Error configurando dispositivos Bluetooth: {e}")
            self.gui.info_label.config(text="Error configurando audio")
            try:
                default_input = self.audio.get_default_input_device_info()
                self.microphone_index = default_input['index']
                print(f"🎤 Usando micrófono por defecto (fallback): {default_input['name']}")
            except:
                print("❌ No se pudo configurar ningún micrófono")

    def speak(self, text):
        """Texto a voz usando gTTS (Google Text-to-Speech)"""
        try:
            # Actualizar GUI
            self.gui.add_to_chat("PROTEUS", text)
            print(f"🤖 PROTEUS: {text}")
            
            # Limitar texto largo para evitar problemas
            if len(text) > 500:
                text = text[:500] + "..."
            
            # Usar gTTS para generar audio
            tts = gTTS(text=text, lang='es', slow=False)
            
            # Crear buffer en memoria para el audio
            audio_buffer = io.BytesIO()
            tts.write_to_fp(audio_buffer)
            audio_buffer.seek(0)
            
            # Reproducir audio usando pygame
            pygame.mixer.music.load(audio_buffer, 'mp3')
            pygame.mixer.music.play()
            
            # Esperar a que termine la reproducción
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
            
            # Cerrar el buffer
            audio_buffer.close()
                
        except Exception as e:
            print(f"❌ Error en gTTS: {e}")
            self.gui.add_to_chat("SISTEMA", f"Error de voz: {e}")

    def check_wake_word(self, text):
        """Verifica si el texto contiene alguna de las wake words"""
        text_lower = text.lower()
        for wake_word in self.wake_words:
            if wake_word in text_lower:
                self.gui.add_to_chat("SISTEMA", f"Wake word detectada: '{wake_word}'")
                print(f"✅ Wake word '{wake_word}' detectada!")
                return True
        return False

    def activate_listening_mode(self):
        """Activa el modo de escucha por 5 minutos"""
        self.active_mode = True
        self.active_until = time.time() + self.active_duration
        self.gui.add_to_chat("SISTEMA", f"Modo activo por {self.active_duration} segundos")
        print(f"🎯 Modo activo activado por {self.active_duration} segundos")
        self.speak("Soy proteus, el robot rescatista puedes indicarme como te encuentras?.")

    def is_active_mode_expired(self):
        """Verifica si el modo activo ha expirado"""
        if self.active_mode and time.time() > self.active_until:
            self.active_mode = False
            self.gui.add_to_chat("SISTEMA", "Modo activo expirado")
            print("⏰ Modo activo expirado, volviendo a detección de wake words")
            self.speak("Mi tiempo de activación se agotó, si necesitas ayuda no dudes en pedirla")
            return True
        return False

    def listen_for_wake_word(self, timeout=3):
        """Escucha continuamente para detectar cualquier wake word"""
        try:
            with sr.Microphone(device_index=self.microphone_index) as source:
                if self.active_mode:
                    status_text = f"Modo activo - Escuchando comandos... ({int(self.active_until - time.time())}s restantes)"
                    print(f"🎯 {status_text}")
                else:
                    status_text = "Escuchando wake words..."
                    print(f"🔍 {status_text}")
                
                # Actualizar GUI
                self.gui.info_label.config(text=status_text)
                
                # Ajustar para ruido ambiental
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                self.recognizer.energy_threshold = 400
                self.recognizer.pause_threshold = 0.8
                
                try:
                    audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=2)
                    text = self.recognizer.recognize_google(audio, language='es-ES').lower()
                    print(f"👂 Detectado: {text}")
                    
                    # Enviar detección a la GUI
                    if self.detection_callback and text.strip():
                        self.detection_callback(text)
                    
                    # Verificar si es una wake word
                    if self.check_wake_word(text):
                        self.activate_listening_mode()
                        return True
                    
                    # Si estamos en modo activo, cualquier speech es un comando
                    if self.active_mode:
                        return text
                    
                    return False
                    
                except sr.WaitTimeoutError:
                    return False
                except sr.UnknownValueError:
                    return False
                except sr.RequestError as e:
                    print(f"❌ Error reconocimiento: {e}")
                    return False
                    
        except Exception as e:
            print(f"❌ Error escuchando: {e}")
            return False

    def listen_for_command(self, timeout=10):
        """Escucha un comando después de detectar la wake word"""
        try:
            with sr.Microphone(device_index=self.microphone_index) as source:
                self.gui.info_label.config(text="Escuchando comando...")
                print("🎤 Escuchando comando...")
                
                self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
                self.recognizer.energy_threshold = 350
                self.recognizer.pause_threshold = 1.0
                
                try:
                    audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=15)
                    text = self.recognizer.recognize_google(audio, language='es-ES')
                    
                    # Enviar detección a la GUI
                    if self.detection_callback and text.strip():
                        self.detection_callback(text)
                    
                    self.gui.add_to_chat("USUARIO", text)
                    print(f"👤 Comando: {text}")
                    return text
                    
                except sr.WaitTimeoutError:
                    print("⏰ Timeout - No se detectó comando")
                    return None
                except sr.UnknownValueError:
                    print("❌ No se pudo entender el comando")
                    return None
                except sr.RequestError as e:
                    print(f"❌ Error servicio reconocimiento: {e}")
                    return None
                    
        except Exception as e:
            print(f"❌ Error escuchando comando: {e}")
            return None

    def process_command(self, command):
        """Procesa el comando y genera respuesta"""
        if not command:
            return
            
        response = self.get_ai_response(command)
        self.speak(response)

    def start_voice_assistant(self):
        """Inicia el asistente de voz con wake word"""
        voice_thread = threading.Thread(target=self._voice_assistant_loop)
        voice_thread.daemon = True
        voice_thread.start()
        self.gui.add_to_chat("SISTEMA", "Asistente de voz activado")
        print("🎧 Asistente de voz con wake words múltiples activado")

    def _voice_assistant_loop(self):
        """Bucle principal del asistente de voz"""
        while self.is_listening and self.gui.is_running:
            try:
                # Verificar si el modo activo ha expirado
                self.is_active_mode_expired()
                
                # Escuchar wake word o comando (dependiendo del modo)
                result = self.listen_for_wake_word(timeout=5)
                
                if result is True:
                    # Se detectó una wake word y se activó el modo
                    continue
                elif result and self.active_mode:
                    # En modo activo, cualquier speech es un comando
                    self.process_command(result)
                elif self.active_mode:
                    # En modo activo pero no se detectó speech, continuar
                    continue
                
                # Pequeña pausa entre escuchas
                time.sleep(0.1)
                
            except Exception as e:
                print(f"❌ Error en bucle de voz: {e}")
                self.gui.add_to_chat("SISTEMA", f"Error en asistente: {e}")
                time.sleep(1)

    def get_ai_response(self, prompt):
        """Obtiene respuesta de IA"""
        for attempt in range(2):
            try:
                print(f"🧠 Procesando: {prompt[:100]}...")
                response = self.chat.send_message(prompt)
                
                # Extraer texto de la respuesta de manera robusta
                if hasattr(response, 'text'):
                    respuesta_texto = response.text
                else:
                    respuesta_texto = str(response)
                
                self.conversation_history.append(f"PROTEUS: {respuesta_texto}")
                return respuesta_texto

            except Exception as e:
                print(f"❌ Error API (intento {attempt + 1}): {e}")
                self.gui.add_to_chat("SISTEMA", f"Error API (intento {attempt + 1}): {e}")
                if attempt == 0 and not self.switch_api_key():
                    return "Error temporal con el servicio de IA"
                    
        return "No pude procesar tu solicitud"

    def switch_api_key(self):
        """Cambia de API key"""
        self.gui.add_to_chat("SISTEMA", "Cambiando API key...")
        print("🔄 Cambiando API key...")
        original_index = self.current_api_index
        
        for _ in range(len(self.api_keys)):
            self.current_api_index = (self.current_api_index + 1) % len(self.api_keys)
            
            try:
                new_key = self.api_keys[self.current_api_index]
                genai.configure(api_key=new_key)
                self.model = genai.GenerativeModel('gemini-2.5-flash')
                self.chat = self.model.start_chat(history=[])
                self.chat.send_message(self.system_prompt)
                self.gui.api_status.config(text=f"API: Key {self.current_api_index + 1}")
                print(f"✅ Nueva API key: {self.current_api_index + 1} (2.5 Flash)")
                return True
            except Exception as e:
                print(f"❌ Error key {self.current_api_index + 1}: {e}")
                continue

        print("❌ No hay keys funcionales")
        return False

    def cleanup(self):
        """Limpia recursos"""
        self.is_listening = False
        if self.audio:
            self.audio.terminate()
        pygame.mixer.quit()

    def run(self):
        """Ejecuta el asistente"""
        self.start_voice_assistant()
        self.speak(f"Proteus activado. Palabras de activación: {', '.join(self.wake_words[:3])}...")

        try:
            while self.is_listening and self.gui.is_running:
                if int(time.time()) % 30 == 0:
                    status = "Activo" if self.active_mode else "Escuchando"
                    time_left = int(self.active_until - time.time()) if self.active_mode else 0
                    print(f"📊 Estado: {status} | Tiempo restante: {time_left}s | API: {self.current_api_index + 1}")
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\n🛑 Apagando asistente...")
            self.speak("PROTEUS se desconecta.")
            self.cleanup()

def main():
    root = tk.Tk()
    app = ProteusGUI(root)
    
    # Configurar limpieza al cerrar la ventana
    root.protocol("WM_DELETE_WINDOW", lambda: on_closing(root, app))
    root.mainloop()

def on_closing(root, app):
    """Función para limpiar recursos al cerrar la aplicación"""
    app.cleanup()
    root.destroy()

if __name__ == "__main__":
    main()