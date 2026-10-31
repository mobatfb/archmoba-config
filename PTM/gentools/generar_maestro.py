#!/usr/bin/env python3
"""GENTOOLS: catalogo maestro de ideas de software para PTM/tools.

Integra 25.200 propuestas preexistentes sin alterar su identificador legado,
y suma proyectos integrales en ambitos sociales, profesiones y oficios.
Todo contenido es ideacion; las propuestas necesitan evaluacion humana.
"""
from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path
from collections import Counter, defaultdict

BASE = Path(__file__).resolve().parent
INPUT = BASE / "ideas_25200_sociedad_y_profesiones.csv"
OUTPUT = BASE / "maestro.csv"

# Cada ambito incorpora veinte problemas/reto reales, no cambios de estilo
# o de plataforma de un mismo programa. Separador: '|'.
NEW_AREAS = {
    "Politica y participacion ciudadana": "consultas publicas de propuestas normativas|calendarios de sesiones legislativas|preguntas ciudadanas a autoridades|seguimiento de promesas publicas|comparacion neutral de propuestas legislativas|registro de audiencias publicas|presupuestos participativos|convocatorias de cabildos abiertos|iniciativas populares normativas|seguimiento de peticiones ciudadanas|accesibilidad de discursos publicos|repositorio de debates parlamentarios|cartas ciudadanas a representantes|seguimiento de ordenanzas locales|alfabetizacion civica no partidista|historial de votaciones legislativas publicas|explicacion de funciones de gobierno|recopilacion de aportes comunitarios|agenda de observacion ciudadana|visualizacion de decisiones de concejos",
    "Transparencia y gobierno abierto": "catalogo de datasets abiertos|comparador de presupuestos institucionales|seguimiento de contrataciones publicas|explorador de gastos agregados|observatorio de obras publicas|agenda de obligaciones de transparencia|solicitudes de acceso a informacion|calidad de metadatos publicos|visualizacion de declaraciones de intereses publicas|verificador de integridad de archivos oficiales|participacion en planes de desarrollo|registro de compromisos institucionales|mapa de servicios publicos|buscador de documentos oficiales|catalogo de indicadores territoriales|control de versiones normativas|seguimiento de auditorias publicadas|panel de atencion ciudadana agregada|indice de datos reutilizables|archivo de rendicion de cuentas",
    "Procesos electorales neutrales": "informacion general sobre procesos electorales|simulador didactico de escrutinio|control logistico de materiales electorales|accesibilidad en informacion de votacion|guia de papeletas simuladas|calendario publico de hitos electorales|registro de capacitacion de miembros de mesa|repositorio de normativa electoral publica|visualizador de resultados oficiales agregados|detector de inconsistencias de datasets de resultados|observacion de procesos con datos anonimos|inventario de equipos de conteo|seguimiento de incidencias logisticas|instrucciones de accesibilidad de recintos|comparacion neutral de plataformas publicas|planificador de voluntariado civico imparcial|resumen comprensible de actas publicas|educacion sobre voto secreto|simulador de distribucion proporcional de escaños|archivo de historicos electorales agregados",
    "Administracion publica": "ventanilla de tramites internos|turnos de atencion al publico|seguimiento de expedientes anonimizados|gestion de archivos administrativos|gestion de inventario institucional|calendario de obligaciones de unidades|directorio de competencias publicas|control de solicitudes ciudadanas|accesibilidad de formularios|mapa de procesos institucionales|seguimiento de indicadores de servicios|inventario de infraestructura publica|registro de mantenimiento municipal|gestion de oficios digitales|control de tiempos de respuesta|archivo de resoluciones publicas|agenda de capacitacion de servidores|gestion de espacios comunales|cuadro de riesgos administrativos|tablero de mejoras de servicio",
    "Justicia y orientacion legal": "calendario de audiencias para profesionales|guia de rutas de acceso a justicia|directorio de asistencia legal|biblioteca de formularios legales generales|calculadora configurable de plazos|control documental de expedientes privados|organizador de jurisprudencia publica|mediacion comunitaria voluntaria|registro de acuerdos de mediacion|comparador de redacciones contractuales|seguimiento de requisitos de tramites judiciales|agenda de citas con defensoria|inventario de evidencias documentales|verificador de firmas y hashes|gestion de turnos en consultorios juridicos|educacion sobre derechos procesales|reporte anonimo de barreras legales|archivo de leyes y reglamentos|asistente de lectura de normas|agenda de vencimientos legales",
    "Derechos humanos y proteccion social": "mapa de servicios sociales|directorio de apoyo a victimas|registro confidencial de derivaciones|panel anonimo de barreras de acceso|accesibilidad de informacion de derechos|orientacion de servicios de proteccion|seguimiento de ayudas comunitarias|biblioteca de capacitacion en derechos|agenda de talleres de inclusion|indicadores agregados de atencion|herramientas de traduccion inclusiva|evaluacion de accesibilidad de oficinas|gestion de refugios temporales|verificacion de informacion de servicios|catalogo de programas de apoyo|planificador de voluntariado social|control de donaciones en especie|calendario de visitas sociales autorizadas|observatorio de necesidades no identificables|archivo de acuerdos de proteccion",
    "Proteccion de datos y privacidad": "inventario de datos personales|matriz de finalidades de tratamiento|calendario de retencion documental|registro de solicitudes de acceso a datos|gestion de consentimientos verificables|analisis local de metadatos|auditoria de permisos de archivos|separacion de datos identificativos|anonimizacion de datasets|cifrado de archivos sensibles|gestor de copias privadas|evaluacion de impacto de privacidad|registro de incidentes de datos|guia de privacidad para menores|control de exportaciones de datos|comparador de politicas de privacidad|gestor de pseudonimos de prueba|revision de carpetas compartidas|panel de obligaciones de privacidad|limpieza segura de archivos temporales",
    "Seguridad ciudadana preventiva": "mapa anonimo de riesgos reportados|agenda de patrullaje comunitario preventivo|registro de alumbrado averiado|seguimiento de rutas escolares seguras|plan de vigilancia vecinal respetuosa|inventario de senaletica preventiva|registro de solicitudes de atencion|biblioteca de prevencion del fraude|rutas seguras accesibles|talleres de convivencia|inventario de camaras autorizadas|gestion de eventos masivos|indicadores agregados de convivencia|agenda de reuniones de seguridad comunitaria|avisos publicos de prevencion|inspecciones de espacios comunes|guia de denuncia formal|seguimiento de medidas no intrusivas|registro de mantenimiento de alarmas|panel de compromisos preventivos",
    "Prevencion de violencia y convivencia": "ruta de apoyo ante violencia domestica|directorio seguro de servicios de ayuda|material de convivencia escolar|alertas sobre estafas frecuentes|agenda de mediacion vecinal|talleres de resolucion pacifica|protocolos de primeros contactos|recursos para prevencion del acoso|actividades de cultura de paz|informacion sobre violencia digital|seguimiento agregado de talleres|guia de proteccion de menores|control de riesgos de espacios compartidos|orientacion ante discriminacion|biblioteca de recursos psicosociales|plan de apoyo a comunidades|capacitacion sobre trato respetuoso|recursos sobre prevencion del hostigamiento|guia de seguridad en eventos|agenda de comites de convivencia",
    "Emergencias y proteccion civil": "inventario de suministros de emergencia|planes de evacuacion de edificios|checklist de simulacros|coordinacion de brigadas voluntarias|puntos de reunion comunitarios|estado de refugios temporales|registro de danos no personales|rutas de ayuda durante inundaciones|seguimiento de donaciones en desastres|agenda de mantenimiento de extintores|mapas de amenazas naturales publicas|catalogo de equipos de respuesta|formularios offline de evaluacion rapida|gestion de necesidades basicas|coordinacion de transporte de suministros|biblioteca de primeros auxilios educativos|panel de voluntarios habilitados|planificador de capacitaciones|archivo de lecciones aprendidas|verificacion de inventarios postevento",
    "Ciberseguridad personal": "auditoria de contrasenas propias|gestion de llaves de recuperacion|control de permisos de aplicaciones|deteccion de archivos duplicados sospechosos|analisis de enlaces potencialmente peligrosos|verificacion de descargas por hash|guia contra phishing|proteccion de cuentas familiares|revision de dispositivos autorizados|inventario de respaldos cifrados|auditoria de metadatos antes de compartir|educacion sobre autenticacion multifactor|simulador de estafas ficticias|comprobacion de cifrado de disco|registro personal de incidentes digitales|guia de privacidad en navegadores|catalogo de software de confianza|planificador de actualizaciones locales|auditoria de configuraciones de privacidad|verificador de certificados publicos",
    "Ciberseguridad empresarial defensiva": "inventario de activos autorizados|gestion de parches|matriz de controles de seguridad|auditoria de configuracion de endpoints|analizador de registros propios|seguimiento de incidentes defensivos|inventario de certificados TLS|gestion de permisos de usuarios|verificacion de respaldos corporativos|evaluacion de riesgo de proveedores|cuadro de mando de continuidad|clasificacion de activos criticos|simulador didactico de respuesta a incidentes|registro de evidencias con integridad|verificador de actualizaciones de software|gestion de vulnerabilidades publicadas|inventario de dispositivos de red|evaluacion de cumplimiento de controles|calendario de capacitacion anti phishing|plan de respuesta a perdida de datos",
    "Conectividad e internet comunitario": "mapa de zonas sin cobertura|registro de fallas de conectividad|mediciones voluntarias de velocidad|inventario de puntos de acceso|planificador de mantenimiento de antenas|registro de costos de internet comunitario|catalogo de proveedores regionales|guia de configuracion de router domestico|monitor de cortes de red propios|analisis de estabilidad de conexiones|plataforma de contenidos offline comunitarios|calendario de alfabetizacion en internet|control de uso de enlace compartido|gestion de solicitudes de soporte|mapa de redes de bibliotecas publicas|inventario de cableado local|sistema de avisos de interrupciones|organizador de redes WiFi autorizadas|control de energizacion de equipos|comparador de planes con datos ingresados",
    "Telecomunicaciones e infraestructura": "inventario de fibra optica|mapa de enlaces punto a punto propios|seguimiento de empalmes de fibra|bitacora de nodos de comunicaciones|ordenes de trabajo de tecnicos|registro de potencia optica|planificador de canalizaciones|control de repuestos de telecom|registro de pruebas de latencia|matriz de dependencias de enlaces|gestion de mantenimientos de torres|planificacion de turnos de NOC|inventario de radioenlaces|seguimiento de ticket de averias|documentacion de topologias|plan de capacidad de backbone|gestion de licencias de equipos|control de visitas a sitios|registro de energia de nodos|verificacion de normas internas de instalacion",
    "Desarrollo de software y calidad": "generacion de esqueletos de aplicaciones|gestion de requisitos funcionales|documentacion automatizada de APIs|visualizador de dependencias|catalogo de componentes reutilizables|analizador estatico local|seguimiento de errores reproducibles|gestion de versiones semanticas|revisor de formatos CSV|pruebas de compatibilidad multiplataforma|laboratorio de interfaz accesible|registro de rendimiento de apps|control de paquetes desplegados|constructor de instaladores|gestor de traducciones|auditoria de licencias de dependencias|validador de configuraciones|gestion de entornos virtuales|editor visual de esquemas JSON|verificador de respaldos de repositorios",
    "Inteligencia artificial responsable": "registro de conjuntos de datos|evaluacion de sesgos de muestras|catalogo de modelos locales|comparacion de resultados de prompts|explicaciones de clasificaciones|auditoria de datos de entrenamiento|seguimiento de versiones de modelos|deteccion de cambios de distribucion|reporte de errores de prediccion|laboratorio de etiquetado humano|anonimizacion previa al entrenamiento|registro de evaluaciones humanas|gestion de consentimiento de corpus|medicion de consumo de inferencia|pruebas de robustez no adversariales|prototipado de asistentes privados|seguimiento de fuentes de respuestas|revision de contenidos generados|planificacion de evaluaciones de modelos|matriz de riesgos de automatizacion",
    "Datos, estadistica y analitica": "limpieza de archivos tabulares|comparacion de series temporales|catalogo de diccionarios de datos|conversor de codificaciones|deteccion de valores atipicos|seguimiento de calidad de datasets|editor de consultas SQL local|organizador de proyectos de estadistica|generador de graficos descriptivos|comparador de indicadores geograficos|gestor de metadatos tabulares|evaluador de formularios de encuesta|analizador de respuestas anonimas|constructor de paneles offline|generador de tablas pivote|auditoria de versiones de datasets|registro de transformaciones de datos|verificador de consistencia de claves|analisis de correlaciones exploratorias|paquetes de informes reproducibles",
    "Nube y centros de datos": "inventario de recursos de nube|estimador de costos de infraestructura|registro de incidencias de datacenter|matriz de backup y recuperacion|control de accesos a servidores|plan de capacidad de almacenamiento|monitoreo de temperaturas de sala|seguimiento de vencimiento de dominios|inventario de certificados digitales|matriz de servicios criticos|plan de migracion de servidores|seguimiento de despliegues|bitacora de mantenimiento de racks|registro de pruebas de recuperacion|control de imagenes de maquinas virtuales|catalogo de redes virtuales|gestor de gastos por proyecto|seguimiento de alertas de disponibilidad|inventario de automatizaciones|planificador de reemplazo de hardware",
    "Soporte informatico": "mesa de ayuda local|inventario de computadores|control de garantias de equipos|registro de intervenciones de soporte|biblioteca de soluciones comunes|agenda de mantenimiento preventivo|gestor de prestamos de periféricos|control de licencias de software|diagnostico guiado de impresoras|registro de configuraciones autorizadas|gestor de imagenes de sistema|control de piezas de repuesto|evaluacion de satisfaccion postsoporte|historial de reparaciones|verificador de espacio en disco|catalogo de controladores compatibles|gestor de cuentas de laboratorio|organizador de cableado|plan de renovacion de equipos|reporte de incidencias recurrentes",
    "Robotica e internet de las cosas": "simulador de sensores domesticos|inventario de dispositivos IoT|panel de consumo de sensores propios|registro de calibraciones|control de firmware de dispositivos|planificador de tareas de robots educativos|simulador de automatizacion de riego|monitor de temperatura con datos propios|catalogo de componentes electronicos|seguimiento de baterias de sensores|visualizador de telemetria local|registro de fallas de actuadores|biblioteca de circuitos educativos|seguimiento de pruebas de prototipos|verificador de seguridad de dispositivos|gestor de proyectos Arduino|repositorio de configuraciones MQTT|registro de mantenimiento de robots|comparador de lecturas calibradas|cuadro de mando de experimentos IoT",
    "Energias limpias y electricidad": "simulador de consumo solar domiciliario|inventario de paneles fotovoltaicos|calendario de mantenimiento de inversores|comparador de consumo electrico|control de baterias de respaldo|guia de dimensionamiento formativo|registro de cortes de energia|monitor de energia con medidores propios|planificador de eficiencia de edificios|seguimiento de mantenimiento de generadores|catalogo de luminarias eficientes|calculadora de costos de recarga electrica|registro de instalacion autorizada|inventario de tableros electricos|analizador de facturas de energia|estimador de ahorro por aislamiento|plan de reemplazo de luminarias|bitacora de inspecciones de puesta a tierra|control de repuestos electricos|panel de energia comunitaria",
    "Agua, clima y resiliencia": "medicion manual de lluvia|inventario de puntos de agua|planificador de mantenimiento de pozos|mapa comunitario de inundaciones reportadas|registro de sequias locales|agenda de conservacion de microcuencas|comparador de calidad de agua de laboratorio|biblioteca de medidas de ahorro de agua|inventario de cisternas y tanques|registro de perdidas de agua|simulador didactico de balance hidrico|control de turnos de riego|panel de reportes de abastecimiento|archivo de series climaticas publicas|inventario de sistemas de drenaje|agenda de inspecciones de alcantarillado|plan de captacion de lluvia|guia de proteccion ante olas de calor|reporte de puntos de calor urbano|seguimiento de infraestructura verde",
    "Residuos y economia circular": "catalogo de materiales reutilizables|plataforma de intercambio de objetos|control de residuos en oficinas|inventario de puntos limpios|agenda de recoleccion diferenciada|registro de reparaciones que evitan descarte|plan de compostaje comunitario|clasificacion educativa de materiales|control de residuos electronicos|seguimiento de reciclaje de vidrio|reporte de volumen recuperado|mapa de talleres de reparacion|guia de separacion domiciliaria|control de equipos reacondicionados|agenda de jornadas de limpieza|intercambio de excedentes comerciales|registro de envases retornables|inventario de herramientas compartidas|simulador de huella de residuos|documentacion de cadenas de reciclaje",
    "Vivienda y urbanismo": "registro de mantenimiento de edificios|mapa de espacios publicos accesibles|planificador de mejoras de barrio|inventario de mobiliario urbano|agenda de asambleas de condominios|reporte de baches comunitarios|seguimiento de obras de vivienda|catalogo de planos domesticos|presupuesto de remodelacion|registro de eficiencia termica|seguimiento de ocupacion de espacios|plan de seguridad contra incendios residencial|inventario de parques infantiles|mapa de rutas peatonales seguras|seguimiento de permisos de construccion|control de contratos de mantenimiento|agenda de limpieza comunal|registro de conflictos de convivencia|inventario de areas verdes|comparador de alternativas de iluminacion urbana",
    "Transporte publico y operaciones": "tablero de frecuencias planificadas|registro de ocupacion agregada|reporte de accesibilidad de paradas|agenda de mantenimiento de buses|inventario de senales de transito|control de limpieza de unidades|planificacion de despachos|registro de incidencias de pasajeros anonimas|comparador de rutas en datos abiertos|informador de transbordos frecuentes|agenda de capacitacion de conductores|control de consumos de flota|inventario de paradas rurales|seguimiento de horarios publicados|reporte de unidades disponibles|registro de condiciones de terminales|mapa de conexiones intermodales|analisis de retrasos historicos|planificador de repuestos|archivo de protocolos operacionales",
    "Movilidad activa y accesible": "mapa de rampas peatonales|registro de obstaculos en aceras|directorio de talleres de bicicletas|planificador de rutas ciclistas|inventario de aparcabicicletas|guia de movilidad de escolares|agenda de caminatas comunitarias|registro de reparaciones de bicicletas|evaluacion de cruces peatonales|mapa de sombra para caminantes|guia de accesibilidad de estaciones|seguimiento de mantenimiento de senderos|registro de iluminacion en ciclovias|biblioteca de seguridad ciclista|comparador de rutas accesibles|control de bicicletas compartidas propias|inventario de senaletica tactil|simulador educativo de semaforos|agenda de educacion vial|seguimiento de puntos de conflicto peatonal",
    "Migracion y movilidad humana": "directorio multilingue de servicios|lista de documentos de viaje|calendario de tramites migratorios|archivo privado de traducciones|guia general de validacion de titulos|mapa de centros de atencion|planificador de alojamiento temporal|agenda de cursos de idioma|biblioteca de informacion oficial vigente|control de citas de orientacion|comparador general de rutas documentales|registro anonimo de barreras de atencion|gestor de documentos personales cifrados|directorios de apoyo comunitario|guia de acceso educativo para recien llegados|seguimiento de ayudas legales|glosario de tramites frecuentes|plan de integracion laboral|archivo de recursos culturales|agenda de actividades interculturales",
    "Cooperacion y diplomacia": "agenda de compromisos de convenio|tablero de proyectos de cooperacion|repositorio de acuerdos publicos|directorio de actores internacionales|seguimiento de objetivos multilaterales|calendario de eventos interculturales|gestor de traducciones institucionales|archivo de informes de misiones|control de presupuestos de proyectos|biblioteca de protocolos ceremoniales|monitor de indicadores de programas|inventario de donaciones internacionales|panel de reuniones bilaterales|seguimiento de becas de cooperacion|gestor de acciones de enlace|archivo de notas diplomaticas publicas|mapa de programas conjuntos|agenda de capacitacion internacional|registro de entregables de convenio|tablero de compromisos de ayuda",
    "Organizaciones sociales y ONG": "registro de proyectos comunitarios|seguimiento de beneficiarios anonimos|agenda de voluntarios autorizados|control de donaciones monetarias|inventario de donaciones en especie|tablero de metas de impacto|generador de informes de proyectos|registro de alianzas territoriales|seguimiento de actividades de campo|gestor de capacitaciones|archivo de estatutos y actas|control de presupuestos de programa|mapa de servicios gratuitos|planificador de campañas informativas no partidistas|control de rendicion de cuentas|registro de asistencia a talleres|comparador de indicadores de resultados|agenda de redes de apoyo|gestion de solicitudes de ayuda|reporte de necesidades territoriales agregadas",
    "Banca y finanzas inclusivas": "presupuesto para trabajadores informales|guia de productos bancarios generales|registro de ahorro en grupos|calculadora de tasas de interes|control de cuotas de prestamo|comparador de costos financieros|planificador de fondo de emergencia|simulador de amortizacion|control de comisiones de servicios|agenda de pagos de cooperativas|registro de aportaciones comunitarias|educacion financiera interactiva|historial de metas de ahorro|inventario de gastos de microtiendas|calculadora de punto de equilibrio|control de pagos parciales|presupuesto para productores rurales|seguimiento de credito responsable|comparacion de escenarios de deuda|organizador de recibos digitales",
    "Comercio internacional y aduanas": "catalogo de requisitos de exportacion|seguimiento de documentacion aduanera|calculadora de costos de importacion|control de embalajes internacionales|agenda de vencimientos comerciales|registro de proveedores externos|simulador de rutas logisticas|inventario de certificados de origen|cuadro de control de incoterms educativos|planificador de envios internacionales|trazabilidad de lotes exportados|control de fletes y seguros|catalogo de clasificaciones arancelarias de referencia|comparador de monedas con tipo de cambio ingresado|registro de inspecciones documentales|control de pedidos de importacion|agenda de ferias comerciales exteriores|calculadora de volumen y peso logistico|archivo de contratos de comercio|panel de tiempos de despacho",
    "Cooperativas y microfinanzas": "registro de aportaciones de socios|control de caja comunitaria|administracion de turnos de credito|simulador de prestamos asociativos|registro de acuerdos de asamblea|planificador de pagos solidarios|inventario de activos comunes|control de fondos rotatorios|agenda de reuniones de directiva|comparador de costos de ahorro|seguimiento de programas productivos|registro de compras conjuntas|cuadro de cuotas vencidas|archivo de actas y estatutos|control de caja chica|agenda de capacitacion financiera|panel de uso de recursos colectivos|calculadora de distribucion de excedentes|seguimiento de metas cooperativas|registro de comites de vigilancia",
    "Emprendimiento y productos digitales": "validacion de propuestas de valor|registro de entrevistas a clientes consentidas|tablero de experimentos de producto|plan de lanzamientos de aplicaciones|catalogo de planes de precios|simulador de costos SaaS|seguimiento de incidencias de usuarios|gestor de suscripciones locales|biblioteca de activos de marca|planificador de contenidos propios|indicadores agregados de conversion|control de contratos de servicios digitales|seguimiento de soporte a clientes|editor de landing pages locales|pruebas de usabilidad de prototipos|archivo de comentarios de clientes|registro de hipotesis de negocio|cuadro de prioridades de funcionalidades|generador de propuestas comerciales|seguimiento de renovaciones de licencias",
    "Artesanias y saberes tradicionales": "catalogo de patrones textiles propios|archivo de tecnicas artesanales|inventario de herramientas de taller|calculadora de costo de piezas|agenda de ferias artesanales|control de pedidos personalizados|etiquetado de materiales artesanales|registro de procesos de produccion|galeria digital de artesanos|planificador de compras de insumos|biblioteca de historias de oficio|simulador de combinaciones de colores|archivo de disenos propios|registro de tiempos de elaboracion|control de mermas de taller|mapa de talleres comunitarios|agenda de clases de oficio|calculadora de precios mayoristas|gestor de envios de piezas|inventario de moldes y herramientas",
    "Manufactura y produccion industrial": "control de ordenes de produccion|registro de fallos de maquina|inventario de repuestos de planta|checklist de seguridad de turno|seguimiento de lotes fabricados|plan de mantenimiento de equipos|control de desperdicio de materia prima|gestion de tiempos de ciclo|calculo de capacidad de linea|registro de inspecciones de calidad|trazabilidad de piezas|calendario de calibracion|plan de compras de suministros|bitacora de paradas de produccion|inventario de herramientas|calculadora de costos de lote|panel de productividad por etapa|seguimiento de instrucciones de trabajo|control de entregas de proveedor|archivo de planos de fabricacion",
    "Mineria responsable y geologia": "catalogo de muestras geologicas|agenda de sondeos autorizados|registro de mantenimiento minero|inventario de equipos de seguridad|planificador de capacitacion geologica|archivo de mapas topograficos|seguimiento de calidad de agua en operaciones|control documental de permisos|registro de transporte de muestras|comparador de composiciones minerales de laboratorio|archivo fotografico de taludes|agenda de inspecciones de seguridad|inventario de explosivos solo administrativo autorizado|control de polvo ambiental medido|seguimiento de restauracion ambiental|panel de energia de operaciones|registro de calibracion de instrumentos|seguimiento de residuos mineros|catalogo de equipos de perforacion|agenda de reportes regulatorios",
    "Agricultura regenerativa": "plan de rotacion de cultivos|registro de coberturas vegetales|calendario de compostaje|monitoreo manual de humedad del suelo|catalogo de semillas locales|control de uso de agua de riego|registro de biodiversidad de parcela|bitacora de manejo agroecologico|agenda de asociaciones campesinas|calculo de costos por parcela|inventario de herramientas agricolas|registro de experimentos de suelo|planificador de barreras vivas|seguimiento de rendimiento cosechado|biblioteca de practicas regenerativas|mapa de parcelas con coordenadas ingresadas|agenda de mantenimiento de riego|registro de intercambio de semillas|control de insumos organicos|simulador de escenarios de produccion",
    "Conservacion de biodiversidad": "inventario de especies observadas|bitacora de monitoreo de aves|mapa de arboles urbanos|seguimiento de restauracion de habitat|archivo de fotografias de fauna|agenda de censos comunitarios|registro de polinizadores|mapa de corredores ecologicos|catalogo de plantas nativas|seguimiento de rescate de fauna autorizado|biblioteca de sonidos ambientales propios|control de viveros de especies nativas|agenda de limpieza de humedales|indicadores de reforestacion|registro de amenazas ambientales publicas|planificador de parcelas de investigacion|archivo de muestras botanicas|control de herramientas de guardaparques|visualizador de series de monitoreo|directorio de iniciativas de conservacion",
    "Salud publica y epidemiologia": "tablero de indicadores sanitarios agregados|seguimiento de campañas educativas de prevencion|inventario de equipos de centros de salud|agenda de brigadas de salud|control de materiales educativos|registro anonimo de encuestas de habitos|visualizador de tasas publicadas|agenda de mantenimiento sanitario|directorio de puntos de vacunacion publicados|control de cadena de frio con datos propios|archivo de boletines epidemiologicos|panel de atencion por horarios sin pacientes|seguimiento de visitas de saneamiento|indicadores de calidad del aire|mapa de recursos sanitarios|agenda de capacitacion del personal|control de suministros no farmacologicos|planificador de jornadas preventivas|biblioteca de informacion sanitaria verificada|registro de intervenciones comunitarias agregadas",
    "Salud mental y apoyo comunitario": "diario privado de bienestar emocional|agenda de grupos de apoyo voluntario|directorio de profesionales habilitados|recursos de respiracion y pausas|biblioteca psicoeducativa no diagnostica|organizador de rutinas de autocuidado|registro de objetivos de bienestar|calendario de actividades sociales|formulario anonimo de satisfaccion de talleres|guia de recursos para cuidadores|planificador de descanso|registro de logros personales|agenda de talleres de convivencia|coleccion de contenidos de apoyo|control de privacidad del diario personal|orientacion hacia servicios de urgencia|registro de participacion anonima|biblioteca de estrategias de regulacion general|panel de habitos saludables|directorio de centros de atencion comunitaria",
    "Inclusion y discapacidad": "agenda de servicios accesibles|catalogo de apoyos tecnicos|lector de documentos con alto contraste|convertidor de formatos accesibles|mapa de barreras arquitectonicas|planificador de adaptaciones educativas|registro de mantenimiento de ayudas tecnicas|directorio de interpretes autorizados|creador de pictogramas propios|gestor de subtitulos para videos|catalogo de actividades inclusivas|agenda de capacitacion en accesibilidad|inspector de accesibilidad de sitios locales|almacenamiento de preferencias de lectura|control de prestamos de ayudas tecnicas|comunicador alternativo configurable|generador de fichas con lectura facil|organizador de recursos de inclusion laboral|biblioteca de materiales adaptados|panel de revisiones de accesibilidad",
    "Formacion tecnica y oficios": "simulador de circuitos electricos educativos|biblioteca de planos de carpinteria|agenda de practicas de soldadura|control de herramientas de taller|evaluador de checklists de seguridad|creador de guias de mantenimiento|simulador de mezclas de pintura|planificador de modulos formativos|inventario de materiales de practica|registro de competencias adquiridas|seguimiento de practicas profesionales|agenda de uso de laboratorio|biblioteca de videos formativos propios|control de equipos prestados|calendario de evaluaciones practicas|reporte de consumibles de taller|generador de ordenes de practica|repositorio de proyectos de estudiantes|simulador de presupuestos de oficio|panel de progreso de aprendices",
    "Investigacion cientifica": "registro de hipotesis de investigacion|bitacora de experimentos|catalogo de instrumentos cientificos|control de muestras de laboratorio|calculadora de tamanos de muestra educativos|planificador de recoleccion de datos|gestor de bibliografia|registro de consentimiento de participantes|repositorio de protocolos aprobados|analizador descriptivo de resultados|visualizador de series experimentales|control de calibracion de instrumentos|inventario de reactivos de laboratorio|agenda de revisiones por pares|registro de versiones de manuscritos|plan de gestion de datos de investigacion|archivo de resultados negativos|seguimiento de replicaciones|generador de informes tecnicos|matriz de reproducibilidad de procedimientos",
    "Periodismo y medios informativos": "verificador de citas contra fuentes aportadas|archivo de entrevistas consentidas|agenda de coberturas periodisticas|control de derechos de imagen|repositorio de notas de campo|organizador de fuentes publicas|transcriptor local de audios propios|comparador de versiones de comunicados|panel de correcciones editoriales|gestor de publicaciones de redaccion|biblioteca de fotografia con licencias|seguimiento de solicitudes de entrevista|registro de fechas de publicacion|archivo de enlaces y copias permitidas|editor de boletines informativos|control de equipos de grabacion|planificador de podcasts propios|tablero de secciones de revista|verificador de metadatos de imagenes|organizador de investigaciones documentales",
    "Artes, cultura y produccion creativa": "catalogo de obras originales|agenda de exposiciones artisticas|archivo de bocetos y versiones|gestor de contratos de exhibicion|inventario de material escenografico|calculadora de presupuesto creativo|organizador de giras culturales|archivo de partituras originales|editor de guiones de escena|control de licencias de obra|biblioteca de referencias visuales autorizadas|agenda de talleres culturales|gestor de colecciones de museos|inventario de iluminacion de espectaculos|simulador de montaje de exposiciones|planificador de sesiones fotograficas|registro de restauracion de obras|editor de tarjetas curatoriales|galeria de proyectos creativos propios|agenda de residencias artisticas",
}

# Una suite completa por necesidad: no separar editor/consulta/alerta en tools redundantes.
APP_FEATURES = {
    "Civico": ["repositorio de fuentes publicas", "cronologia", "filtros neutrales", "resumen verificable", "exportacion abierta"],
    "Gobierno": ["captura de tramites", "seguimiento de estados", "documentos", "busqueda", "reportes de servicio"],
    "Seguridad": ["formularios seguros", "checklists preventivos", "roles", "registro no identificable", "estadisticas agregadas"],
    "Digital": ["inventario tecnico", "pruebas sobre recursos propios", "diagnosticos", "registro de cambios", "exportacion"],
    "Social": ["registro de recursos", "agenda", "seguimiento", "control de acceso", "reportes agregados"],
    "Economia": ["registros contables", "calculadoras", "documentos", "calendario", "reportes"],
    "Ambiente": ["registro de observaciones", "series temporales", "mapas opcionales", "planes", "reportes"],
    "Educacion": ["contenido guiado", "ejercicios", "rubricas", "seguimiento de aprendizaje", "exportacion"],
    "Cultura": ["catalogo multimedia", "etiquetas", "licencias", "busqueda", "publicacion local"],
    "Industria": ["ordenes y activos", "checklists", "stock", "calendario", "indicadores"],
    "Salud": ["contenido educativo revisable", "agenda", "inventario no clinico", "estadisticas anonimas", "privacidad"],
    "General": ["captura de informacion", "organizador", "filtros y busqueda", "calendario", "exportacion CSV/PDF"],
}
CIVIC = ("Politica", "Transparencia", "electoral", "diplomacia", "participacion")
SECURITY = ("Seguridad", "Ciberseguridad", "violencia", "Emergencias", "datos y privacidad")
DIGITAL = ("Telecomunicaciones", "Conectividad", "Desarrollo de software", "Inteligencia", "Datos, estadistica", "Nube", "Soporte informatico", "Robotica")
ECONOMY = ("Banca", "Comercio internacional", "Cooperativas", "Emprendimiento", "economia", "finanzas")
INDUSTRY = ("Manufactura", "Mineria", "transporte", "Energias")
ENVIRONMENT = ("Agua", "Residuos", "Agricultura regenerativa", "Conservacion", "Vivienda", "Movilidad")
EDU = ("Formacion", "Investigacion")
HEALTH = ("Salud", "Inclusion")
CULTURE = ("Periodismo", "Artes", "cultura")
SOCIAL = ("Derechos", "Migracion", "Organizaciones", "Justicia", "publica")


def profile(area):
    for key, prefixes in (("Civico", CIVIC), ("Seguridad", SECURITY), ("Digital", DIGITAL),
                          ("Economia", ECONOMY), ("Industria", INDUSTRY),
                          ("Ambiente", ENVIRONMENT), ("Educacion", EDU),
                          ("Salud", HEALTH), ("Cultura", CULTURE), ("Social", SOCIAL)):
        if any(area.casefold().startswith(x.casefold()) for x in prefixes):
            return key
    return "General"


# Cinco aplicaciones completas por profesion, cada una con proposito y salida distintos.
PRO_APPS = [
    ("Centro operativo", "coordinar el trabajo real de {work} desde la planificacion hasta el cierre", "ordenes de trabajo, agenda, tareas, responsables, evidencias, cierre de actividad", "Gestion"),
    ("Estudio de presupuestos", "estimar recursos y costos de {work} y comparar alternativas", "costos de materiales, horas, tarifas, cotizaciones, escenarios, exportacion", "Finanzas"),
    ("Academia practica", "entrenar decisiones y procedimientos propios de {work} usando casos ficticios", "lecciones, ejercicios, casos simulados, autoevaluacion, progreso, recursos", "Educacion"),
    ("Observatorio de calidad", "medir resultados y detectar oportunidades de mejora en {work}", "indicadores configurables, listas de verificacion, reportes, graficos, tendencias, auditoria", "Analitica"),
    ("Archivo del oficio", "conservar y encontrar procedimientos, materiales y buenas practicas de {work}", "fichas tecnicas, imagenes, documentos, etiquetas, busqueda, versiones, acceso local", "Conocimiento"),
]
FIELDS = [
    "id", "origen", "categoria", "tema", "profesion", "titulo", "publico",
    "necesidad", "solucion_informatica", "funciones_principales", "resultado_esperado",
    "tipo_app", "proyecto_agrupador", "complejidad", "conectividad", "datos_sensibles",
    "precauciones", "prioridad_sugerida", "estado_desarrollo", "id_fuente",
]


def normalized(text):
    return " ".join(unicodedata.normalize("NFKD", str(text)).casefold().split())


def risk_level(category, title, problem):
    text = normalized(" ".join((category,title,problem)))
    hi = ("pacient", "salud mental", "clinica", "medico", "personal", "victima", "violencia", "identidad",
          "menor", "consentimiento", "elector", "policia", "seguridad ciudadana", "psicolog", "juridic", "legal",
          "financier", "banc", "biometr", "privacidad", "expediente", "datos personales", "proteccion")
    return "POSIBLES" if any(word in text for word in hi) else "NO PREVISTOS"


def safety_note(category, sensitive):
    a = normalized(category)
    if "elector" in a or "politica" in a:
        return "Informacion no partidista; sin microsegmentacion politica ni datos de voto individual."
    if sensitive == "POSIBLES":
        return "Minimizar datos; consentimiento, permisos y cifrado segun el contexto; validar normas aplicables."
    if any(word in a for word in ("ciberseguridad", "redes", "seguridad digital")):
        return "Operar solo sobre sistemas propios o con autorizacion explicita."
    if "salud" in a:
        return "Contenido administrativo o educativo; no sustituye criterio de personal habilitado."
    return "Prototipo sujeto a pruebas con usuarios; no presupone cumplimiento normativo."


def connectivity(category, title):
    x=normalized(category + " " + title)
    if any(q in x for q in ("nube", "internet", "web", "online", "redes", "telecom", "api", "externo")):
        return "MIXTA"
    return "OFFLINE_PREFERENTE"


def complexity(kind):
    kind=normalized(kind)
    if any(x in kind for x in ("simulacion", "inteligencia", "multimedia", "video", "seguridad", "juego", "mapas", "geografica", "navegacion")):
        return "ALTA"
    if any(x in kind for x in ("analitica", "automatizacion", "educacion", "calculo", "gestor", "integral")):
        return "MEDIA"
    return "MEDIA"


def add(writer, seen_titles, seen_keys, item, stats):
    title=normalized(item["titulo"])
    # Dedupe por titulo y contexto: no descartar apps con propositos distintos
    # que compartan categoria, tema y tipo_app.
    key=(title, normalized(item["categoria"]), normalized(item["profesion"]))
    if title in seen_titles or key in seen_keys:
        stats["omitidos_duplicados"] += 1
        return False
    seen_titles.add(title)
    seen_keys.add(key)
    item["id"] = stats["total"] + 1
    item["datos_sensibles"] = risk_level(item["categoria"],item["titulo"],item["necesidad"])
    item["precauciones"] = safety_note(item["categoria"],item["datos_sensibles"])
    item["conectividad"] = item.get("conectividad") or connectivity(item["categoria"],item["titulo"])
    item["complejidad"] = item.get("complejidad") or complexity(item["tipo_app"])
    writer.writerow({key: item.get(key, "") for key in FIELDS})
    stats["total"] += 1
    stats["origen_"+item["origen"]] += 1
    stats["area_"+item["categoria"]] += 1
    return True


def generate():
    if not INPUT.is_file():
        raise FileNotFoundError(f"Falta catalogo anterior: {INPUT}")
    stats=Counter(); seen_titles=set(); seen_keys=set()
    areas_existing=defaultdict(set)
    roles=[]; role_seen=set()
    with OUTPUT.open("w",newline="",encoding="utf-8-sig") as dst:
        w=csv.DictWriter(dst,fieldnames=FIELDS,delimiter=";",extrasaction="ignore")
        w.writeheader()
        with INPUT.open("r",newline="",encoding="utf-8-sig") as src:
            base=csv.DictReader(src,delimiter=";")
            for old in base:
                area=old["categoria"].strip(); topic=old["tema"].strip()
                if old["origen"] == "SOCIEDAD":
                    areas_existing[area].add(topic)
                elif old["profesion"] and old["profesion"] not in role_seen:
                    roles.append((area, old["profesion"].strip(), topic));role_seen.add(old["profesion"])
                category=old["categoria"]
                item = {
                    "origen":"LEGADO_25200", "categoria":category, "tema":topic,
                    "profesion":old["profesion"], "titulo":old["titulo"],"publico":old["publico"],
                    "necesidad":old["problema"],"solucion_informatica":old["descripcion"],
                    "funciones_principales":old["funciones_principales"],
                    "resultado_esperado":old["resultado_esperado"],"tipo_app":old["tipo_app"],
                    "proyecto_agrupador":f"Suite {topic} ({area})" if old["origen"] == "SOCIEDAD" else f"Suite {old['profesion']}",
                    "prioridad_sugerida":"POR_EVALUAR", "estado_desarrollo":old["estado_desarrollo"],
                    "id_fuente":old["id"],
                }
                add(w,seen_titles,seen_keys,item,stats)
        if len(areas_existing)!=55 or len(roles)!=400:
            raise ValueError(f"Fuente inesperada: {len(areas_existing)} areas sociales y {len(roles)} profesiones")
        # 55*20 = 1100 suites de problema social integradas.
        for area in sorted(areas_existing):
            p=profile(area)
            feats=APP_FEATURES[p]
            for topic in sorted(areas_existing[area]):
                add(w,seen_titles,seen_keys,{
                    "origen":"SUITE_SOCIAL_INTEGRAL", "categoria":area,"tema":topic,"profesion":"",
                    "titulo":f"Solucion integral de {topic} - {area}", "publico":"Personas y organizaciones interesadas en el tema",
                    "necesidad":f"Resolver de principio a fin la necesidad de {topic} sin instalar diez herramientas aisladas.",
                    "solucion_informatica":f"Aplicacion unica que organiza el trabajo relativo a {topic}, centraliza datos y documentos, ayuda a ejecutar procesos y entrega resultados verificables.",
                    "funciones_principales":"; ".join(feats),
                    "resultado_esperado":f"Gestion completa y trazable de {topic} en un solo proyecto PTM.",
                    "tipo_app":"Suite integral", "proyecto_agrupador":f"Suite {topic} ({area})",
                    "prioridad_sugerida":"ALTA", "estado_desarrollo":"CANDIDATA","id_fuente":"",
                },stats)
        # 45*20 = 900 nuevas ideas verticales integrales para areas insuficientes.
        assert len(NEW_AREAS) == 45, f"Se esperaban 45 nuevos ambitos: {len(NEW_AREAS)}"
        for area, raw in NEW_AREAS.items():
            topics=[x.strip() for x in raw.split("|") if x.strip()]
            assert len(topics)==20, f"{area}: {len(topics)} temas, se esperaban 20"
            p=profile(area)
            feats=APP_FEATURES[p]
            for topic in topics:
                add(w,seen_titles,seen_keys,{
                    "origen":"NUEVA_AREA_SOCIAL", "categoria":area,"tema":topic,"profesion":"",
                    "titulo":f"Centro de {topic} - {area}",
                    "publico": f"Ciudadania y equipos relacionados con {area.casefold()}",
                    "necesidad":f"Quienes trabajan con {topic} necesitan organizar informacion, acciones y resultados concretos para evitar dispersion y tareas manuales.",
                    "solucion_informatica":f"Software especializado para {topic} en el ambito de {area.casefold()}, con flujos completos, validacion de entradas, historial y resultados exportables.",
                    "funciones_principales":"; ".join(feats),
                    "resultado_esperado":f"Una aplicacion PTM unica y funcional para gestionar {topic}.",
                    "tipo_app":f"Suite {p}", "proyecto_agrupador":f"Centro de {topic} ({area})",
                    "prioridad_sugerida":"ALTA", "estado_desarrollo":"CANDIDATA","id_fuente":"",
                },stats)
        # 400*5 = 2000 programas complementarios de proposito diferenciado.
        for sector, job, work in roles:
            for name, target, funcs, kind in PRO_APPS:
                add(w,seen_titles,seen_keys,{
                    "origen":"NUEVA_PROFESION", "categoria":sector,"tema":work,"profesion":job,
                    "titulo":f"{name} para {job}","publico":job,
                    "necesidad":f"Los profesionales de {job.casefold()} necesitan {target.format(work=work)}.",
                    "solucion_informatica":f"Aplicacion orientada a {job.casefold()} que permite {target.format(work=work)}; incorpora datos configurables de {work}, almacenamiento local y exportacion.",
                    "funciones_principales":funcs,
                    "resultado_esperado":f"Herramienta operativa con entregables propios de {work}.",
                    "tipo_app":kind,"proyecto_agrupador":f"Suite profesional {job}",
                    "prioridad_sugerida":"MEDIA", "estado_desarrollo":"CANDIDATA", "id_fuente":"",
                },stats)
    # 25200 + 1100 + 900 + 2000 = 29200
    expected=29200
    if stats["total"] != expected:
        raise RuntimeError(f"No esperado: {stats['total']} en lugar de {expected}; {stats['omitidos_duplicados']} omitidos")
    if len(seen_titles)!=expected:
        raise AssertionError("Se detectaron titulos repetidos")
    print("FILAS:",stats["total"])
    print("TAMANO_MB:",round(OUTPUT.stat().st_size/(1024*1024),2))
    print("ORIGENES:",{k[7:]:v for k,v in stats.items() if k.startswith('origen_')})
    print("AREAS:",len([k for k in stats if k.startswith('area_')]))
    print("ARCHIVO:", OUTPUT)


if __name__ == "__main__":
    generate()