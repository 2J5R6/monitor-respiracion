import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import serial
import serial.tools.list_ports
import json
import threading
import time
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.animation as animation
import numpy as np
from datetime import datetime
import os

# Colores de tema calmante
COLORS = {
    "bg": "#E8F4F8",         # Azul suave de fondo
    "highlight": "#5DA9E9",  # Azul destacado
    "text": "#003459",       # Azul oscuro para texto
    "accent": "#66CED6",     # Turquesa acento
    "warning": "#FF7E6B",    # Rojo suave para alertas
    "success": "#8FD694",    # Verde suave para normal
    "neutral": "#D8E1E9"     # Gris neutro
}

class RespiraMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Monitor de Respiración - Respira")
        self.root.geometry("900x700")
        self.root.configure(bg=COLORS["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Configuración predeterminada
        self.com_port = None
        self.serial_conn = None
        self.is_connected = False
        self.data_buffer = []
        self.breath_data = []
        self.rpm_history = []
        self.timestamps = []
        self.stop_event = threading.Event()
        
        # Valores de referencia
        self.ALERT_LOW = 12
        self.ALERT_HIGH = 25
        
        # Variables para gráficos
        self.data_points = 100  # Puntos a mostrar en las gráficas
        self.acceleration_history = [0] * self.data_points
        self.delta_history = [0] * self.data_points
        self.filtered_history = [0] * self.data_points
        self.threshold_history = [0] * self.data_points
        
        # Inicializar variables Tkinter
        self.status_var = tk.StringVar(value="Desconectado")
        self.rpm_var = tk.StringVar(value="--")
        self.breath_count_var = tk.StringVar(value="0")
        self.state_var = tk.StringVar(value="ESPERANDO")
        
        # Crear la interfaz
        self.create_widgets()
        
        # Cargar puertos disponibles
        self.load_ports()

    def create_widgets(self):
        # Frame principal
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Estilo personalizado
        style = ttk.Style()
        style.configure("TFrame", background=COLORS["bg"])
        style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Segoe UI", 10))
        style.configure("TButton", background=COLORS["highlight"], foreground="white", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"), background=COLORS["bg"], foreground=COLORS["text"])
        style.configure("Subtitle.TLabel", font=("Segoe UI", 12), background=COLORS["bg"], foreground=COLORS["text"])
        style.configure("Value.TLabel", font=("Segoe UI", 28, "bold"), background=COLORS["bg"])
        style.configure("RPM.TLabel", font=("Segoe UI", 36, "bold"), background=COLORS["bg"])
        style.configure("Normal.RPM.TLabel", foreground=COLORS["success"])
        style.configure("High.RPM.TLabel", foreground=COLORS["warning"])
        style.configure("Low.RPM.TLabel", foreground=COLORS["warning"])
        
        # Barra superior con logo y controles
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Título y logo
        title_frame = ttk.Frame(top_frame)
        title_frame.pack(side=tk.LEFT)
        
        logo_label = ttk.Label(title_frame, text="🫁", font=("Segoe UI", 24))
        logo_label.pack(side=tk.LEFT, padx=(0, 5))
        
        title_label = ttk.Label(title_frame, text="Monitor Respiratorio", style="Title.TLabel")
        title_label.pack(side=tk.LEFT)
        
        # Controles de conexión
        control_frame = ttk.Frame(top_frame)
        control_frame.pack(side=tk.RIGHT)
        
        self.port_combo = ttk.Combobox(control_frame, width=15)
        self.port_combo.pack(side=tk.LEFT, padx=5)
        
        refresh_btn = ttk.Button(control_frame, text="↻", width=2, command=self.load_ports)
        refresh_btn.pack(side=tk.LEFT, padx=5)
        
        self.connect_btn = ttk.Button(control_frame, text="Conectar", command=self.toggle_connection)
        self.connect_btn.pack(side=tk.LEFT, padx=5)
        
        # Panel de información principal
        info_frame = ttk.Frame(main_frame)
        info_frame.pack(fill=tk.X, pady=10)
        
        # Panel de RPM
        rpm_frame = ttk.Frame(info_frame)
        rpm_frame.pack(side=tk.LEFT, padx=(0, 20), fill=tk.Y)
        
        ttk.Label(rpm_frame, text="Respiraciones por Minuto", style="Subtitle.TLabel").pack(pady=(0, 5))
        
        self.rpm_label = ttk.Label(rpm_frame, textvariable=self.rpm_var, style="RPM.TLabel")
        self.rpm_label.pack()
        
        ttk.Label(rpm_frame, text="respiraciones/min", style="TLabel").pack()
        
        # Panel de estado
        status_frame = ttk.Frame(info_frame)
        status_frame.pack(side=tk.LEFT, padx=20, fill=tk.Y)
        
        ttk.Label(status_frame, text="Estado", style="Subtitle.TLabel").pack(pady=(0, 5))
        
        self.state_label = ttk.Label(status_frame, textvariable=self.state_var, style="Value.TLabel")
        self.state_label.pack()
        
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, style="TLabel")
        self.status_label.pack(pady=(5, 0))
        
        # Acumulado de respiraciones
        breath_frame = ttk.Frame(info_frame)
        breath_frame.pack(side=tk.LEFT, padx=20, fill=tk.Y)
        
        ttk.Label(breath_frame, text="Respiraciones Totales", style="Subtitle.TLabel").pack(pady=(0, 5))
        
        self.breath_count_label = ttk.Label(breath_frame, textvariable=self.breath_count_var, style="Value.TLabel")
        self.breath_count_label.pack()
        
        # Contenedor para los gráficos
        graph_container = ttk.Frame(main_frame)
        graph_container.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Gráfico de señal de respiración
        self.create_respiration_graph(graph_container)
        
        # Gráfico histórico de RPM
        self.create_rpm_history_graph(graph_container)
        
        # Panel inferior con información y acciones
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X, pady=(10, 0))
        
        # Información del rango saludable
        info_label = ttk.Label(bottom_frame, 
                              text=f"Rango saludable: {self.ALERT_LOW}-{self.ALERT_HIGH} RPM",
                              style="TLabel")
        info_label.pack(side=tk.LEFT)
        
        # Botones adicionales
        save_btn = ttk.Button(bottom_frame, text="Guardar Datos", command=self.save_data)
        save_btn.pack(side=tk.RIGHT, padx=5)
        
        help_btn = ttk.Button(bottom_frame, text="Ayuda", command=self.show_help)
        help_btn.pack(side=tk.RIGHT, padx=5)
        
        # Etiqueta de estado de conexión
        self.connection_status = ttk.Label(self.root, text="Desconectado", foreground="red")
        self.connection_status.pack(anchor=tk.SE, padx=10, pady=5)

    def create_respiration_graph(self, parent):
        # Frame para gráfico de respiración
        resp_frame = ttk.LabelFrame(parent, text="Señal de Respiración en Tiempo Real")
        resp_frame.pack(fill=tk.BOTH, expand=True, side=tk.TOP)
        
        # Crear figura y ejes para matplotlib
        self.resp_fig = Figure(figsize=(5, 2.5), dpi=100)
        self.resp_fig.patch.set_facecolor(COLORS["bg"])
        
        self.resp_ax = self.resp_fig.add_subplot(111)
        self.resp_ax.set_facecolor(COLORS["bg"])
        self.resp_ax.grid(True, linestyle='--', alpha=0.7)
        self.resp_ax.set_ylabel('Aceleración')
        self.resp_ax.set_xlabel('Tiempo')
        self.resp_ax.set_title('Señal Respiratoria')
        
        # Configurar líneas para los diferentes datos
        self.line_filtered, = self.resp_ax.plot(np.arange(self.data_points), 
                                         self.filtered_history, 
                                         label='Señal Filtrada', 
                                         color=COLORS["highlight"],
                                         linewidth=2)
        
        self.line_threshold, = self.resp_ax.plot(np.arange(self.data_points), 
                                          self.threshold_history, 
                                          label='Umbral', 
                                          color=COLORS["warning"],
                                          linestyle='--')
        
        # Añadir leyenda
        self.resp_ax.legend(loc='upper right')
        
        # Crear canvas para la figura
        self.resp_canvas = FigureCanvasTkAgg(self.resp_fig, resp_frame)
        self.resp_canvas.draw()
        self.resp_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def create_rpm_history_graph(self, parent):
        # Frame para gráfico de historia de RPM
        rpm_frame = ttk.LabelFrame(parent, text="Histórico de Respiraciones por Minuto")
        rpm_frame.pack(fill=tk.BOTH, expand=True, side=tk.TOP, pady=(10, 0))
        
        # Crear figura y ejes para matplotlib
        self.rpm_fig = Figure(figsize=(5, 2.5), dpi=100)
        self.rpm_fig.patch.set_facecolor(COLORS["bg"])
        
        self.rpm_ax = self.rpm_fig.add_subplot(111)
        self.rpm_ax.set_facecolor(COLORS["bg"])
        self.rpm_ax.grid(True, linestyle='--', alpha=0.7)
        self.rpm_ax.set_ylabel('RPM')
        self.rpm_ax.set_xlabel('Tiempo (s)')
        self.rpm_ax.set_title('Histórico de RPM')
        
        # Configurar línea para RPM
        self.line_rpm, = self.rpm_ax.plot([], [], 
                                    label='RPM', 
                                    color=COLORS["accent"],
                                    marker='o',
                                    markersize=3,
                                    linewidth=2)
        
        # Añadir líneas para los límites
        self.rpm_ax.axhline(y=self.ALERT_LOW, color=COLORS["warning"], linestyle='--', alpha=0.7, label=f'Mín ({self.ALERT_LOW})')
        self.rpm_ax.axhline(y=self.ALERT_HIGH, color=COLORS["warning"], linestyle='--', alpha=0.7, label=f'Máx ({self.ALERT_HIGH})')
        
        # Límites del eje Y
        self.rpm_ax.set_ylim(0, 40)
        
        # Añadir leyenda
        self.rpm_ax.legend(loc='upper right')
        
        # Crear canvas para la figura
        self.rpm_canvas = FigureCanvasTkAgg(self.rpm_fig, rpm_frame)
        self.rpm_canvas.draw()
        self.rpm_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def load_ports(self):
        """Cargar los puertos seriales disponibles en el Combobox"""
        ports = serial.tools.list_ports.comports()
        port_list = [port.device for port in ports]
        
        if port_list:
            self.port_combo['values'] = port_list
            self.port_combo.current(0)
        else:
            self.port_combo['values'] = ["No hay puertos disponibles"]
            self.status_var.set("No se encontraron puertos seriales")

    def toggle_connection(self):
        """Alternar entre conectar y desconectar"""
        if not self.is_connected:
            self.connect_to_device()
        else:
            self.disconnect_from_device()

    def connect_to_device(self):
        """Conectar al dispositivo en el puerto seleccionado"""
        selected_port = self.port_combo.get()
        
        if selected_port == "No hay puertos disponibles":
            messagebox.showerror("Error", "No hay puertos disponibles para conectar")
            return
        
        try:
            # Intentar conectar al puerto serial
            self.serial_conn = serial.Serial(selected_port, 115200, timeout=1)
            self.is_connected = True
            self.com_port = selected_port
            
            # Actualizar interfaz
            self.connect_btn.config(text="Desconectar")
            self.status_var.set("Conectado a " + selected_port)
            self.connection_status.config(text="Conectado", foreground="green")
            
            # Iniciar hilo para leer datos
            self.stop_event.clear()
            self.data_thread = threading.Thread(target=self.read_serial_data)
            self.data_thread.daemon = True
            self.data_thread.start()
            
            # Iniciar animación de gráficos
            self.ani_resp = animation.FuncAnimation(
                self.resp_fig, self.update_respiration_graph, 
                interval=100, blit=False
            )
            
            self.ani_rpm = animation.FuncAnimation(
                self.rpm_fig, self.update_rpm_graph, 
                interval=1000, blit=False
            )
            
        except (OSError, serial.SerialException) as e:
            messagebox.showerror("Error de conexión", f"No se pudo conectar al puerto {selected_port}.\nError: {str(e)}")
            self.status_var.set(f"Error: {str(e)}")

    def disconnect_from_device(self):
        """Desconectar del dispositivo"""
        # Detener el hilo de lectura
        self.stop_event.set()
        if hasattr(self, 'data_thread') and self.data_thread.is_alive():
            self.data_thread.join(1.0)
        
        # Detener animaciones
        if hasattr(self, 'ani_resp'):
            self.ani_resp.event_source.stop()
        
        if hasattr(self, 'ani_rpm'):
            self.ani_rpm.event_source.stop()
        
        # Cerrar conexión serial
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        
        # Actualizar interfaz
        self.is_connected = False
        self.connect_btn.config(text="Conectar")
        self.status_var.set("Desconectado")
        self.connection_status.config(text="Desconectado", foreground="red")

    def read_serial_data(self):
        """Leer datos del puerto serial en segundo plano"""
        buffer = ""
        
        while not self.stop_event.is_set():
            try:
                if self.serial_conn and self.serial_conn.is_open:
                    # Leer datos disponibles
                    data = self.serial_conn.read(self.serial_conn.in_waiting or 1)
                    
                    if data:
                        # Decodificar y agregar al buffer
                        buffer += data.decode('utf-8', errors='ignore')
                        
                        # Buscar líneas completas en el buffer
                        lines = buffer.split('\n')
                        
                        # Procesar todas las líneas completas
                        if len(lines) > 1:
                            for line in lines[:-1]:
                                self.process_line(line.strip())
                            
                            # Conservar la última línea (posiblemente incompleta)
                            buffer = lines[-1]
                
                # Pequeño retraso para no sobrecargar la CPU
                time.sleep(0.01)
                
            except Exception as e:
                print(f"Error leyendo datos: {e}")
                # Si hay un error, pausa breve antes de reintentar
                time.sleep(0.1)

    def process_line(self, line):
        """Procesar una línea de datos recibida"""
        if not line:
            return
            
        try:
            # Intentar parsear JSON
            if line.startswith('{') and line.endswith('}'):
                data = json.loads(line)
                
                # Almacenar datos en el buffer
                self.data_buffer.append(data)
                if len(self.data_buffer) > 100:
                    self.data_buffer.pop(0)
                
                # Actualizar variables de la UI
                if 'rpm' in data:
                    rpm = data['rpm']
                    self.rpm_var.set(str(rpm) if rpm > 0 else "--")
                    
                    # Actualizar histórico de RPM si hay un valor válido
                    if rpm > 0:
                        self.rpm_history.append(rpm)
                        self.timestamps.append(time.time())
                        
                        # Mantener solo los últimos 60 valores (1 minuto)
                        if len(self.rpm_history) > 60:
                            self.rpm_history.pop(0)
                            self.timestamps.pop(0)
                
                if 'breathCount' in data:
                    self.breath_count_var.set(str(data['breathCount']))
                
                if 'status' in data:
                    status = data['status']
                    self.state_var.set(status)
                    
                    # Actualizar estilo según el estado
                    if status == "ALTO":
                        self.rpm_label.configure(style="High.RPM.TLabel")
                        self.state_label.configure(foreground=COLORS["warning"])
                    elif status == "BAJO":
                        self.rpm_label.configure(style="Low.RPM.TLabel")
                        self.state_label.configure(foreground=COLORS["warning"])
                    elif status == "NORMAL":
                        self.rpm_label.configure(style="Normal.RPM.TLabel")
                        self.state_label.configure(foreground=COLORS["success"])
                    else:
                        self.rpm_label.configure(style="RPM.TLabel")
                        self.state_label.configure(foreground=COLORS["text"])
                
                # Actualizar datos para gráficos
                if 'filtered' in data:
                    self.filtered_history.append(data['filtered'])
                    if len(self.filtered_history) > self.data_points:
                        self.filtered_history.pop(0)
                
                if 'threshold' in data:
                    # Crear un array con el valor del umbral repetido
                    self.threshold_history = [data['threshold']] * self.data_points
                
        except json.JSONDecodeError:
            # Si no es JSON, ignorar
            pass
        except Exception as e:
            print(f"Error procesando datos: {e}")

    def update_respiration_graph(self, frame):
        """Actualizar el gráfico de respiración"""
        if not self.is_connected:
            return
            
        try:
            # Actualizar datos de las líneas
            self.line_filtered.set_ydata(self.filtered_history)
            self.line_threshold.set_ydata(self.threshold_history)
            
            # Ajustar los límites del eje Y si es necesario
            if self.filtered_history:
                max_val = max(max(self.filtered_history), max(self.threshold_history)) * 1.2
                min_val = min(min(self.filtered_history), 0) * 1.2
                self.resp_ax.set_ylim(min_val, max_val)
            
            # Redibujar
            self.resp_canvas.draw_idle()
            
        except Exception as e:
            print(f"Error actualizando gráfico de respiración: {e}")

    def update_rpm_graph(self, frame):
        """Actualizar el gráfico histórico de RPM"""
        if not self.is_connected or not self.rpm_history:
            return
            
        try:
            # Convertir timestamps a segundos relativos
            if self.timestamps:
                relative_time = [t - self.timestamps[0] for t in self.timestamps]
                
                # Actualizar datos
                self.line_rpm.set_data(relative_time, self.rpm_history)
                
                # Ajustar límites del eje X
                self.rpm_ax.set_xlim(0, max(relative_time) + 1)
                
                # Redibujar
                self.rpm_canvas.draw_idle()
                
        except Exception as e:
            print(f"Error actualizando gráfico RPM: {e}")

    def save_data(self):
        """Guardar los datos recopilados en un archivo"""
        if not self.data_buffer:
            messagebox.showinfo("Información", "No hay datos para guardar")
            return
            
        try:
            # Crear directorio si no existe
            save_dir = "datos_respiracion"
            os.makedirs(save_dir, exist_ok=True)
            
            # Crear nombre de archivo con fecha y hora
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(save_dir, f"resp_data_{timestamp}.json")
            
            # Guardar datos
            with open(filename, 'w') as f:
                json.dump(self.data_buffer, f, indent=2)
                
            messagebox.showinfo("Éxito", f"Datos guardados en {filename}")
            
        except Exception as e:
            messagebox.showerror("Error", f"No se pudieron guardar los datos: {str(e)}")

    def show_help(self):
        """Mostrar información de ayuda"""
        help_text = """
Monitor de Respiración - Respira

Este programa muestra datos de respiración en tiempo real desde un sensor conectado.

Instrucciones:
1. Seleccione el puerto COM y haga clic en "Conectar"
2. Los datos de respiración se mostrarán en los gráficos
3. El valor RPM indica las respiraciones por minuto
4. Rango saludable: 12-25 RPM

Alertas:
- ALTO: Respiración demasiado rápida (>25 RPM)
- BAJO: Respiración demasiado lenta (<12 RPM)
- NORMAL: Respiración en rango saludable

Para más información, consulte el manual del dispositivo.
        """
        messagebox.showinfo("Ayuda", help_text)

    def on_closing(self):
        """Manejar el cierre de la aplicación"""
        if self.is_connected:
            self.disconnect_from_device()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = RespiraMonitorApp(root)
    root.mainloop()
