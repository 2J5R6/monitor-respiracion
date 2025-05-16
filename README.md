# Sistema de Monitoreo Respiratorio

Este proyecto implementa un sistema completo para monitorear la respiración utilizando un sensor ICM-20948 conectado a un ESP32-S3, que se comunica con una aplicación GUI en Python para visualización en tiempo real.

## Componentes del Sistema

1. **Hardware:**
   - ESP32-S3
   - Sensor ICM-20948
   - LCD 16x2
   - Buzzer

2. **Software:**
   - Firmware para ESP32-S3 (Arduino)
   - Aplicación GUI en Python

## Características Principales

- Calibración automática del sensor
- Detección robusta de ciclos respiratorios
- Cálculo de respiraciones por minuto (RPM)
- Alertas para valores fuera del rango saludable (12-25 RPM)
- Transmisión de datos en formato JSON
- Visualización en tiempo real con gráficos

## Configuración

### Hardware

1. Conecte el sensor ICM-20948 al ESP32-S3:
   - SDA: Pin 8
   - SCL: Pin 18
   
2. Conecte el LCD 16x2:
   - RS: Pin 4
   - E: Pin 5
   - D4: Pin 6
   - D5: Pin 7
   - D6: Pin 15
   - D7: Pin 17

3. Conecte el buzzer al pin 10

### Firmware (Arduino)

1. Abra el archivo `Respira_code.ino` en el IDE de Arduino
2. Seleccione la placa ESP32-S3
3. Compile y cargue el código al dispositivo

### Aplicación GUI (Python)

1. Instale las dependencias requeridas:
   ```
   pip install -r requirements.txt
   ```

2. Ejecute la aplicación:
   ```
   python respira_gui.py
   ```

3. Seleccione el puerto COM correcto y haga clic en "Conectar"

## Uso del Sistema

### Calibración

El sistema requiere una calibración al inicio:
1. Fase 1: Manténgase quieto y no respire (3 segundos)
2. Fase 2: Realice una inhalación y exhalación completa siguiendo las instrucciones

### Monitoreo

Después de la calibración, el sistema:
- Mostrará la tasa de respiración en tiempo real (RPM)
- Alertará con sonidos y visualmente cuando la respiración esté fuera del rango saludable
- Mostrará gráficos de la señal respiratoria y el historial de RPM

### Guardado de Datos

La aplicación GUI permite guardar los datos recopilados en formato JSON para análisis posterior.

## Solución de Problemas

- **No se detecta el sensor:** Verifique las conexiones SDA y SCL
- **No hay datos en la GUI:** Asegúrese de seleccionar el puerto COM correcto
- **Calibración incorrecta:** Reinicie el dispositivo y siga las instrucciones de calibración cuidadosamente
- **Detección incorrecta:** Ajuste la posición del sensor para que capture mejor el movimiento respiratorio

## Notas Técnicas

- El algoritmo de detección utiliza un enfoque de máquina de estados para identificar ciclos respiratorios completos
- Se aplica un filtro de media móvil ponderada para reducir el ruido
- La comunicación utiliza formato JSON a 115200 baudios
- El sistema es ideal para pacientes con ansiedad, con una interfaz calmante y retroalimentación visual
