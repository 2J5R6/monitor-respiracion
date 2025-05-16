#include <Wire.h>
#include <Adafruit_ICM20948.h>
#include <LiquidCrystal.h>

// LCD
LiquidCrystal lcd(4, 5, 6, 7, 15, 17);

// Sensor
Adafruit_ICM20948 icm;
#define SDA_PIN 8
#define SCL_PIN 18
#define ICM20948_I2C_ADDRESS 0x68

// Buzzer para alertas
#define BUZZER_PIN 10  // PIN 10 para el buzzer
#define ALERT_HIGH 25  // RPM alto - alerta
#define ALERT_LOW 12   // RPM bajo - alerta

// Variables de calibración
float baselineZ = 0;       // Valor base para eje Z (principal para respiración)
bool calibrated = false;
float noiseLevel = 0.05;   // Nivel de ruido estimado (se ajustará durante calibración)

// Variables para detección de respiración
float threshold = 0.2;     // Umbral inicial (se ajustará durante calibración)
bool inBreathCycle = false; // Indica si estamos en medio de un ciclo respiratorio
unsigned long lastBreathTime = 0;
unsigned long breathTimes[5] = {0}; // Últimas 5 respiraciones
int breathIndex = 0;
int breathCount = 0;

// Buffer para filtrado de señal
#define SIGNAL_BUFFER_SIZE 10
float signalBuffer[SIGNAL_BUFFER_SIZE];
int signalBufferIndex = 0;
float lastFilteredValue = 0;

// Variables para detección robusta
unsigned long cycleStartTime = 0;      // Tiempo cuando empezó el ciclo actual
unsigned long lastSignificantMovement = 0; // Último movimiento significativo
int consecutiveStableReadings = 0;     // Lecturas estables consecutivas
float maxDeltaInCycle = 0;             // Delta máximo en el ciclo actual
bool validBreathCycle = false;         // Indicador de ciclo válido
#define MIN_CYCLE_DURATION 1500        // Duración mínima de un ciclo respiratorio (ms)
#define STABLE_READINGS_THRESHOLD 5    // Número de lecturas estables para confirmar fin de ciclo

// Variables para cálculo de RPM
unsigned long lastRpmUpdateTime = 0;
int rpm = 0;

// Variables para mensajes y feedback
bool alertActive = false;
unsigned long lastAnimationTime = 0;
byte animState = 0;
bool breathPromptActive = false;

void setup() {
  Serial.begin(115200);
  Wire.begin(SDA_PIN, SCL_PIN);

  // Inicializar LCD
  lcd.begin(16, 2);
  lcd.print("Monitor Resp.");
  lcd.setCursor(0, 1);
  lcd.print("Inicializando...");
  
  // Inicializar buffer de señal
  for (int i = 0; i < SIGNAL_BUFFER_SIZE; i++) {
    signalBuffer[i] = 0.0;
  }
  
  // Configurar pin del buzzer como salida
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  // Intentar conectar con sensor
  byte intentos = 0;
  while (!icm.begin_I2C(ICM20948_I2C_ADDRESS, &Wire)) {
    lcd.setCursor(0, 1);
    lcd.print("Sensor no detectado");
    Serial.println("Sensor no encontrado");
    
    // Beep de error
    tone(BUZZER_PIN, 400, 200);
    delay(200);
    tone(BUZZER_PIN, 300, 200);
    delay(800);
    
    intentos++;
    if (intentos > 5) {
      while(1); // No continuar si no hay sensor
    }
  }

  // Configuración básica
  icm.setAccelRange(ICM20948_ACCEL_RANGE_2_G);
  delay(100);
  
  // Tono de inicio exitoso
  tone(BUZZER_PIN, 800, 200);
  delay(200);
  tone(BUZZER_PIN, 1000, 200);
  delay(200);
  
  // Realizar calibración inicial
  calibrateSensor();
  
  lcd.clear();
  lcd.print("Listo!");
  lcd.setCursor(0, 1);
  lcd.print("Respire normal");
  
  // Tono de calibración completada
  tone(BUZZER_PIN, 1000, 100);
  delay(100);
  tone(BUZZER_PIN, 1200, 100);
  delay(100);
  tone(BUZZER_PIN, 1400, 100);
  
  delay(1000);
}

void loop() {
  // Leer aceleración del eje Z
  sensors_event_t accel;
  icm.getAccelerometerSensor()->getEvent(&accel);
  
  float zAccel = accel.acceleration.z;
  float zDelta = zAccel - baselineZ;
  
  // Aplicar filtro para reducir ruido
  float filteredDelta = filterSignal(zDelta);
  
  // Detectar respiración basada en cambio del eje Z
  detectBreathRobust(filteredDelta);
  
  // Actualizar RPM y mostrar en pantalla cada segundo
  if (millis() - lastRpmUpdateTime > 1000) {
    calculateRPM();
    updateDisplay();
    checkAlerts();
    lastRpmUpdateTime = millis();
    
    // Enviar datos en formato JSON para la GUI
    Serial.print("{");
    Serial.print("\"acceleration\":");
    Serial.print(zAccel);
    Serial.print(",\"delta\":");
    Serial.print(zDelta);
    Serial.print(",\"filtered\":");
    Serial.print(filteredDelta);
    Serial.print(",\"threshold\":");
    Serial.print(threshold);
    Serial.print(",\"noise\":");
    Serial.print(noiseLevel);
    Serial.print(",\"rpm\":");
    Serial.print(rpm);
    Serial.print(",\"breathCount\":");
    Serial.print(breathCount);
    Serial.print(",\"status\":\"");
    
    // Agregar estado de alerta
    if (rpm > ALERT_HIGH) {
      Serial.print("ALTO");
    } else if (rpm < ALERT_LOW && rpm > 0) {
      Serial.print("BAJO");
    } else if (rpm > 0) {
      Serial.print("NORMAL");
    } else {
      Serial.print("ESPERANDO");
    }
    Serial.print("\"");
    Serial.println("}");
  }
  
  // Animación de respiración si está activa
  if (breathPromptActive) {
    updateBreathingAnimation();
  }
  
  delay(50); // Pequeño retraso para estabilidad
}

// Aplica un filtro de media móvil ponderada para reducir el ruido
float filterSignal(float rawValue) {
  // Actualizar buffer
  signalBuffer[signalBufferIndex] = rawValue;
  signalBufferIndex = (signalBufferIndex + 1) % SIGNAL_BUFFER_SIZE;
  
  // Calcular media ponderada (dando más peso a valores recientes)
  float sumWeighted = 0;
  float weightSum = 0;
  
  for (int i = 0; i < SIGNAL_BUFFER_SIZE; i++) {
    int idx = (signalBufferIndex - 1 - i + SIGNAL_BUFFER_SIZE) % SIGNAL_BUFFER_SIZE;
    float weight = SIGNAL_BUFFER_SIZE - i;  // Mayor peso a muestras recientes
    sumWeighted += signalBuffer[idx] * weight;
    weightSum += weight;
  }
  
  float filteredValue = sumWeighted / weightSum;
  
  // Aplicar un poco de histéresis para evitar oscilaciones pequeñas
  if (abs(filteredValue - lastFilteredValue) < noiseLevel) {
    filteredValue = lastFilteredValue;
  }
  
  lastFilteredValue = filteredValue;
  return filteredValue;
}

void calibrateSensor() {
  lcd.clear();
  lcd.print("Fase 1 de 2");
  lcd.setCursor(0, 1);
  lcd.print("MANTENGA QUIETO");
  Serial.println("Calibrando - Mantenga quieto y no respire");
  
  // Pequeña pausa para prepararse
  delay(2000);
  
  // Fase 1: Quieto sin respirar (5 segundos)
  lcd.clear();
  lcd.print("NO RESPIRE");
  lcd.setCursor(0, 1);
  lcd.print("Midiendo base... ");
  
  float sumZ = 0;
  int samples = 0;
  float maxZ = -100, minZ = 100;
  float deviationSum = 0;
  
  // Primera pasada para obtener la media
  unsigned long startTime = millis();
  while (millis() - startTime < 3000) {
    sensors_event_t accel;
    icm.getAccelerometerSensor()->getEvent(&accel);
    
    sumZ += accel.acceleration.z;
    samples++;
    
    int progress = ((millis() - startTime) * 100) / 3000;
    lcd.setCursor(14, 1);
    lcd.print(map(progress, 0, 100, 0, 99)); // Mostrar 0-99%
    lcd.print("%");
    delay(50);
  }
  
  // Media provisional
  float meanZ = sumZ / samples;
  
  // Segunda pasada para estimar desviación (ruido)
  samples = 0;
  startTime = millis();
  while (millis() - startTime < 2000) {
    sensors_event_t accel;
    icm.getAccelerometerSensor()->getEvent(&accel);
    
    float diff = abs(accel.acceleration.z - meanZ);
    deviationSum += diff;
    samples++;
    
    if (accel.acceleration.z > maxZ) maxZ = accel.acceleration.z;
    if (accel.acceleration.z < minZ) minZ = accel.acceleration.z;
    
    int progress = ((millis() - startTime) * 100) / 2000;
    lcd.setCursor(14, 1);
    lcd.print(map(progress, 0, 100, 0, 99)); // Mostrar 0-99%
    lcd.print("%");
    
    // Parpadeo del buzzer cada segundo para marcar el tiempo
    if ((millis() - startTime) / 1000 != ((millis() - startTime - 50) / 1000)) {
      tone(BUZZER_PIN, 600, 50);
    }
    
    delay(50);
  }
  
  // Estimar nivel de ruido
  noiseLevel = deviationSum / samples;
  
  // Ajustar la línea base
  baselineZ = meanZ;
  
  // Tono de fase completada
  tone(BUZZER_PIN, 1000, 300);
  
  // Fase 2: Respiración guiada (5 segundos)
  lcd.clear();
  lcd.print("Fase 2 de 2");
  lcd.setCursor(0, 1);
  lcd.print("Preparese...");
  delay(1500);
  
  lcd.clear();
  lcd.print("INHALE PROFUNDO");
  lcd.setCursor(0, 1);
  lcd.print("Ahora! ");
  
  // Tono para inhalar
  tone(BUZZER_PIN, 800, 300);
  
  Serial.println("Ahora inhale profundo");
  
  startTime = millis();
  maxZ = -100;
  minZ = 100;
  unsigned long halfTime = 2500; // 2.5 segundos para inhalar
  
  // Primera mitad: inhalación
  while (millis() - startTime < halfTime) {
    sensors_event_t accel;
    icm.getAccelerometerSensor()->getEvent(&accel);
    
    if (accel.acceleration.z > maxZ) maxZ = accel.acceleration.z;
    if (accel.acceleration.z < minZ) minZ = accel.acceleration.z;
    
    int progress = ((millis() - startTime) * 100) / halfTime;
    lcd.setCursor(7, 1);
    lcd.print(map(progress, 0, 100, 0, 99)); // Mostrar 0-99%
    lcd.print("%   ");
    delay(50);
  }
  
  // Tono para exhalar
  tone(BUZZER_PIN, 600, 300);
  
  // Segunda mitad: exhalación
  lcd.clear();
  lcd.print("EXHALE COMPLETO");
  lcd.setCursor(0, 1);
  lcd.print("Ahora! ");
  Serial.println("Ahora exhale completamente");
  
  startTime = millis();
  
  while (millis() - startTime < halfTime) {
    sensors_event_t accel;
    icm.getAccelerometerSensor()->getEvent(&accel);
    
    if (accel.acceleration.z > maxZ) maxZ = accel.acceleration.z;
    if (accel.acceleration.z < minZ) minZ = accel.acceleration.z;
    
    int progress = ((millis() - startTime) * 100) / halfTime;
    lcd.setCursor(7, 1);
    lcd.print(map(progress, 0, 100, 0, 99)); // Mostrar 0-99%
    lcd.print("%   ");
    delay(50);
  }
  
  // Calcular umbral dinámicamente basado en el rango observado
  float rangeDelta = abs(maxZ - minZ);
  threshold = rangeDelta * 0.35; // 35% del rango de respiración
  
  // Asegurar un umbral mínimo (3 veces el nivel de ruido)
  if (threshold < noiseLevel * 3) threshold = noiseLevel * 3;
  if (threshold < 0.2) threshold = 0.2;
  
  calibrated = true;
  Serial.print("Calibración completa. Base Z: ");
  Serial.print(baselineZ);
  Serial.print(" | Nivel de ruido: ");
  Serial.print(noiseLevel);
  Serial.print(" | Umbral: ");
  Serial.println(threshold);
  
  // Tono de calibración completada
  tone(BUZZER_PIN, 1000, 100);
  delay(150);
  tone(BUZZER_PIN, 1200, 200);
}

void detectBreathRobust(float zDelta) {
  // Magnitud del movimiento (valor absoluto)
  float magnitude = abs(zDelta);
  
  // Paso 1: Detectar inicio de ciclo respiratorio
  if (!inBreathCycle && magnitude > threshold) {
    // Solo iniciar un nuevo ciclo si ha pasado suficiente tiempo desde la última respiración
    if (millis() - lastBreathTime > 1000) {
      inBreathCycle = true;
      cycleStartTime = millis();
      maxDeltaInCycle = magnitude;
      consecutiveStableReadings = 0;
      validBreathCycle = false;
      breathPromptActive = true;
      Serial.println("Inicio de ciclo respiratorio potencial");
    }
  } 
  // Paso 2: Actualizar máximo durante el ciclo
  else if (inBreathCycle) {
    // Actualizar el valor máximo detectado
    if (magnitude > maxDeltaInCycle) {
      maxDeltaInCycle = magnitude;
      lastSignificantMovement = millis();
      // Si el movimiento es suficientemente fuerte, marcar como ciclo válido
      if (magnitude > threshold * 1.2) {
        validBreathCycle = true;
      }
    }
    
    // Paso 3: Detectar fin del ciclo respiratorio
    // Considerar fin del ciclo si:
    // a) La señal ha vuelto cerca del valor base durante varias lecturas seguidas
    // b) Ha pasado suficiente tiempo desde el inicio del ciclo
    
    if (magnitude < (threshold * 0.3)) {
      consecutiveStableReadings++;
    } else {
      consecutiveStableReadings = 0;
    }
    
    // Confirmar fin del ciclo cuando tenemos suficientes lecturas estables
    // o ha pasado demasiado tiempo sin más movimiento significativo
    bool timeoutExpired = (millis() - lastSignificantMovement) > 2000;
    bool stableEnough = consecutiveStableReadings >= STABLE_READINGS_THRESHOLD;
    bool minDurationMet = (millis() - cycleStartTime) > MIN_CYCLE_DURATION;
    
    if ((stableEnough || timeoutExpired) && minDurationMet) {
      inBreathCycle = false;
      breathPromptActive = false;
      
      // Solo registrar si fue un ciclo válido con movimiento significativo
      if (validBreathCycle) {
        unsigned long cycleDuration = millis() - cycleStartTime;
        
        // Verificar que la duración sea razonable (entre 1.5 y 15 segundos)
        if (cycleDuration >= MIN_CYCLE_DURATION && cycleDuration < 15000) {
          breathTimes[breathIndex] = cycleDuration;
          breathIndex = (breathIndex + 1) % 5;  // Circular buffer
          breathCount++;
          lastBreathTime = millis();
          
          Serial.print("Respiración #");
          Serial.print(breathCount);
          Serial.print(" - Duración: ");
          Serial.print(cycleDuration);
          Serial.print("ms - Max: ");
          Serial.println(maxDeltaInCycle);
          
          // Pequeño beep para confirmar detección
          tone(BUZZER_PIN, 880, 50);
        } else {
          Serial.println("Duración de ciclo fuera de rango razonable - ignorando");
        }
      } else {
        Serial.println("Ciclo con movimiento insuficiente - ignorando");
      }
    }
  }
}

void calculateRPM() {
  unsigned long totalTime = 0;
  int validSamples = 0;
  
  // Calcular el tiempo promedio entre respiraciones
  for (int i = 0; i < 5; i++) {
    if (breathTimes[i] > 0) {
      totalTime += breathTimes[i];
      validSamples++;
    }
  }
  
  if (validSamples > 0) {
    unsigned long avgTime = totalTime / validSamples;
    rpm = 60000 / avgTime;  // Convertir a respiraciones por minuto
    
    // Asegurar un rango de RPM razonable
    if (rpm > 60) rpm = 60;
  } else {
    // Si no tenemos muestras válidas pero hay respiraciones detectadas,
    // usar el tiempo desde la última respiración para estimar
    if (breathCount > 0 && (millis() - lastBreathTime) > 1000) {
      unsigned long sinceLastBreath = millis() - lastBreathTime;
      // Estimar RPM basado en tiempo desde la última respiración
      // Solo si ha pasado un tiempo razonable (para evitar valores extremos)
      if (sinceLastBreath < 20000) { // Menos de 20 segundos
        rpm = 60000 / sinceLastBreath;
        if (rpm > 60) rpm = 60;
      }
    }
  }
  
  // Reset RPM si no hay respiraciones por más de 30 segundos
  if (breathCount > 0 && (millis() - lastBreathTime) > 30000) {
    rpm = 0;
  }
}

void checkAlerts() {
  // Verificar si estamos fuera de rango y activar alerta
  bool needAlert = false;
  
  if (rpm > ALERT_HIGH || (rpm < ALERT_LOW && rpm > 0)) {
    needAlert = true;
  }
  
  if (needAlert && !alertActive) {
    // Iniciar alerta
    alertActive = true;
    if (rpm > ALERT_HIGH) {
      // Tono de alerta para RPM alto (más agudo)
      tone(BUZZER_PIN, 2000, 300);
    } else {
      // Tono de alerta para RPM bajo (más grave)
      tone(BUZZER_PIN, 400, 300);
    }
  } 
  else if (!needAlert && alertActive) {
    // Desactivar alerta
    alertActive = false;
    noTone(BUZZER_PIN);
  }
  else if (alertActive) {
    // Repetir alerta cada 3 segundos
    static unsigned long lastAlertTime = 0;
    if (millis() - lastAlertTime > 3000) {
      if (rpm > ALERT_HIGH) {
        // Patrón rápido para RPM alto
        tone(BUZZER_PIN, 2000, 200);
        delay(200);
        tone(BUZZER_PIN, 2000, 200);
      } else {
        // Patrón lento para RPM bajo
        tone(BUZZER_PIN, 400, 500);
      }
      lastAlertTime = millis();
    }
  }
}

void updateBreathingAnimation() {
  // Animar una guía de respiración cada 250ms
  if (millis() - lastAnimationTime > 250) {
    lastAnimationTime = millis();
    animState = (animState + 1) % 4;
    
    // Solo actualizar esta parte de la pantalla sin borrar todo
    lcd.setCursor(14, 0);
    
    switch(animState) {
      case 0: lcd.write('|'); break;
      case 1: lcd.write('/'); break;
      case 2: lcd.write('-'); break;
      case 3: lcd.write('\\'); break;
    }
  }
}

void updateDisplay() {
  lcd.clear();
  
  // Si estamos en medio de un ciclo de respiración
  if (inBreathCycle) {
    lcd.print("Detectando...");
    lcd.setCursor(0, 1);
    lcd.print("Complete ciclo");
    return;
  }
  
  // Si no hay RPM pero hay respiraciones, mostrar "Calculando"
  if (rpm == 0 && breathCount > 0) {
    lcd.print("Calculando RPM");
    lcd.setCursor(0, 1);
    lcd.print("Resp: ");
    lcd.print(breathCount);
    lcd.print(" Siga resp.");
    return;
  }
  
  // Si no hay respiraciones detectadas todavía
  if (breathCount == 0) {
    lcd.print("Respire normal");
    lcd.setCursor(0, 1);
    lcd.print("Esperando datos");
    return;
  }
  
  // Mostrar RPM normal
  lcd.print("Respiraciones: ");
  lcd.setCursor(0, 1);
  lcd.print(rpm);
  lcd.print(" RPM");
  
  // Mostrar alerta si está fuera del rango saludable
  if (rpm > ALERT_HIGH) {
    lcd.setCursor(8, 1);
    lcd.print("ALTO!");
  } else if (rpm < ALERT_LOW && rpm > 0) {
    lcd.setCursor(8, 1);
    lcd.print("BAJO!");
  } else {
    // Si está en rango normal
    lcd.setCursor(8, 1);
    lcd.print("Normal");
  }
}