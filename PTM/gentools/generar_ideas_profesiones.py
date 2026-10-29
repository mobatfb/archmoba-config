#!/usr/bin/env python3
"""Amplia el catalogo PTM con ideas profesionales, conservando las 22.000 originales.

400 ocupaciones elegidas en 20 campos x 8 necesidades profesionales concretas = 3.200
ideas adicionales. No es una enumeracion oficial completa de ISCO-08. Los nombres,
ideas y propuestas son una curacion independiente inspirada en su cobertura amplia.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "ideas_22000_diferenciadas.csv"
OUT_ALL = HERE / "ideas_25200_sociedad_y_profesiones.csv"
OUT_JOBS = HERE / "ideas_3200_profesiones.csv"

# Cada entrada es nombre del oficio/profesion y su objeto de trabajo principal.
# 20 sectores x 20 roles de contextos y economias diversos.
ROLES = {
    "Salud y asistencia sanitaria": """
Medico de atencion primaria|consultas de atencion primaria
Pediatra|atencion pediatrica
Profesional de enfermeria|cuidados de enfermeria
Fisioterapeuta|sesiones de rehabilitacion
Odontologo|servicios odontologicos
Farmaceutico|dispensacion farmaceutica
Tecnico de radiologia|estudios por imagen
Tecnico de laboratorio clinico|analisis de muestras
Partera|acompanamiento prenatal
Nutricionista|consultas de nutricion
Terapeuta ocupacional|actividades de autonomia
Psicologo|consultas de psicologia
Optometrista|revisiones de vision
Audiologo|pruebas auditivas
Paramedico|atencion prehospitalaria
Patologo|muestras histopatologicas
Epidemiologo|analisis epidemiologicos
Veterinario|atencion veterinaria
Auxiliar de enfermeria|apoyos de cuidado
Protesico dental|protesis dentales
""",
    "Educacion y formacion": """
Docente de primaria|lecciones de primaria
Profesor de matematicas|clases de matematicas
Profesor de ciencias|clases de ciencias
Educador infantil|actividades de primera infancia
Profesor de lengua|talleres de lengua y lectura
Docente de educacion especial|adaptaciones de aprendizaje
Orientador escolar|sesiones de orientacion escolar
Bibliotecario escolar|servicios de biblioteca escolar
Profesor de artes|talleres de expresion artistica
Profesor de musica|clases de musica
Profesor de educacion fisica|actividades de educacion fisica
Coordinador academico|programacion academica
Instructor de oficios|practicas de capacitacion tecnica
Tutor de educacion a distancia|tutorias virtuales
Profesor universitario|seminarios universitarios
Investigador educativo|estudios sobre aprendizaje
Formador corporativo|capacitaciones de personal
Profesor de idiomas|clases de idiomas
Disenador instruccional|materiales de aprendizaje
Alfabetizador de adultos|sesiones de alfabetizacion
""",
    "Agricultura y ganaderia": """
Agronomo|asistencia agronomica
Agricultor de cereales|cultivos de cereales
Productor de hortalizas|produccion de hortalizas
Viticultor|cultivos de vid
Fruticultor|cultivos frutales
Caficultor|cultivos de cafe
Cacaotero|cultivos de cacao
Arrocero|cultivos de arroz
Floricultor|cultivos florales
Apicultor|colmenas y miel
Ganadero bovino|ganado bovino
Porcicultor|cria porcina
Avicultor|cria avicola
Criador de ovinos|rebanos ovinos
Zootecnista|manejo zootecnico
Tecnico de riego|sistemas de riego
Operador de invernadero|produccion bajo invernadero
Perito agricola|evaluaciones agricolas
Extensionista rural|asistencia tecnica rural
Productor de semillas|produccion de semillas
""",
    "Pesca y acuicultura": """
Pescador artesanal|pesca artesanal
Pescador de altura|pesca de altura
Acuicultor de tilapia|cultivos de tilapia
Acuicultor de salmon|cultivos de salmon
Camaronero|cultivos de camaron
Mariscador|recoleccion de mariscos
Buzo comercial|inspecciones subacuaticas
Biologo marino|estudios de biologia marina
Tecnico de acuicultura|instalaciones acuicolas
Inspector de productos pesqueros|lotes de productos pesqueros
Operador de planta de hielo|produccion de hielo para pesca
Encargado de lonja|operaciones de lonja
Tecnico de nutricion acuicola|alimentacion acuicola
Recolector de algas|recoleccion de algas
Armador de redes|artes y redes de pesca
Cultivador de moluscos|cultivos de moluscos
Tecnico de criadero de peces|criaderos de peces
Operador de planta pesquera|procesamiento de pescado
Investigador de arrecifes|monitoreos de arrecifes
Comercializador de pescado|distribucion de pescado
""",
    "Construccion y arquitectura": """
Arquitecto|proyectos arquitectonicos
Ingeniero civil|proyectos de obra civil
Maestro de obra|ejecucion de obras
Albanil|trabajos de albanileria
Encofrador|encofrados de hormigon
Carpintero de obra|carpinteria de construccion
Topografo|levantamientos topograficos
Calculista de estructuras|calculos estructurales
Dibujante tecnico|planos tecnicos
Urbanista|planes urbanisticos
Inspector de obra|inspecciones de obra
Gestor de proyectos de construccion|carteras de obra
Instalador de pisos|instalaciones de pisos
Colocador de ceramica|revestimientos ceramicos
Techador|cubiertas de edificios
Especialista en fachadas|instalaciones de fachada
Pintor de edificios|pintura de edificios
Tecnico de andamios|andamiajes certificados
Restaurador de patrimonio edificado|restauraciones patrimoniales
Operador de hormigonera|mezclas de hormigon
""",
    "Instalaciones y mantenimiento": """
Electricista residencial|instalaciones electricas domesticas
Electricista industrial|instalaciones electricas industriales
Fontanero|redes de agua domiciliaria
Tecnico de climatizacion|equipos de climatizacion
Tecnico de refrigeracion|sistemas de refrigeracion
Instalador fotovoltaico|paneles fotovoltaicos
Instalador de fibra optica|redes de fibra optica
Tecnico de ascensores|sistemas de elevacion
Reparador de electrodomesticos|electrodomesticos
Tecnico de maquinaria industrial|maquinas de planta
Mecanico automotriz|vehiculos automotores
Mecanico de bicicletas|bicicletas
Mecanico de motocicletas|motocicletas
Tecnico de calderas|calderas y calefactores
Soldador industrial|uniones soldadas
Tecnico de automatizacion|sistemas automatizados
Tecnico de seguridad electronica|sistemas de alarma
Instalador de gas|redes de gas
Mantenedor de piscinas|equipos de piscinas
Cerrajero|cierres y cerraduras
""",
    "Transporte y logistica": """
Conductor de autobus|servicios de autobus
Conductor de taxi|viajes en taxi
Conductor de camion|transporte en camion
Repartidor de paquetes|entregas de paquetes
Piloto comercial|operaciones de vuelo comercial
Piloto civil de drones|vuelos civiles de inspeccion
Tripulante de cabina|servicios de cabina
Maquinista de tren|trayectos ferroviarios
Tecnico de via ferroviaria|mantenimiento de vias
Capitan de buque mercante|travesias mercantes
Marinero mercante|operaciones de cubierta
Operador portuario|movimientos portuarios
Controlador de transito aereo|coordinacion de transito aereo
Planificador de rutas|redes de rutas
Coordinador de flota|flotas de transporte
Despachador de transporte|asignaciones de transporte
Encargado de almacen|almacenamiento de mercancias
Operador de montacargas|movimientos de montacargas
Agente de aduanas|despachos aduaneros
Mensajero motorizado|rutas de mensajeria
""",
    "Comercio y ventas": """
Vendedor minorista|ventas minoristas
Dependiente de ferreteria|articulos de ferreteria
Cajero de supermercado|cajas de supermercado
Asesor de productos de farmacia|productos farmaceuticos no sujetos a receta
Agente inmobiliario|operaciones inmobiliarias
Corredor de seguros|polizas de seguros
Ejecutivo de ventas B2B|cuentas empresariales
Agente de televentas|campanas de televentas
Comerciante de mercado|puestos de mercado
Especialista en comercio electronico|tiendas de comercio electronico
Escaparatista|exhibiciones comerciales
Gerente de tienda|operaciones de tienda
Asesor de automoviles|ventas de automoviles
Comerciante ambulante|puestos de comercio ambulante
Representante de insumos agricolas|suministros agricolas
Librero|ventas de libros
Encargado de bazar|articulos de bazar
Especialista en servicio al cliente|solicitudes de clientes
Comprador mayorista|adquisiciones mayoristas
Distribuidor minorista|distribucion local
""",
    "Gastronomia y alimentacion": """
Chef de restaurante|servicios de cocina de restaurante
Cocinero de comedor|menus de comedor
Panadero|produccion de pan
Pastelero|productos de pasteleria
Carnicero|cortes de carne
Pescadero|preparacion de pescados
Cocinero de comida callejera|puestos de comida callejera
Responsable de catering|servicios de catering
Barista|preparacion de cafe
Chocolatero|productos de chocolate
Heladero|elaboracion de helados
Dietista de cocina colectiva|menus de cocina colectiva
Inspector de higiene alimentaria|revisiones higienicas de alimentos
Procesador de lacteos|procesamiento de lacteos
Quesero|fabricacion de queso
Fermentador de alimentos|fermentaciones alimentarias
Productor de conservas|conservas artesanales
Cocinero de cocina vegetal|menus de cocina vegetal
Jefe de cocina|operacion de cocinas
Encargado de comedor escolar|servicios de comedor escolar
""",
    "Turismo y hoteleria": """
Gerente hotelero|operaciones hoteleras
Recepcionista de hotel|atencion de recepcion
Camarero de pisos|limpieza de habitaciones
Conserje de hotel|servicios de conserjeria
Guia turistico|recorridos turisticos
Guia de montana|excursiones de montana
Agente de viajes|reservas de viajes
Operador de excursiones|excursiones guiadas
Gestor de turismo sostenible|actividades de turismo sostenible
Animador turistico|animaciones turisticas
Agente de reservas|reservas de alojamiento
Organizador de congresos|congresos y eventos
Gestor de albergue|operacion de albergues
Responsable de hospedaje rural|hospedajes rurales
Instructor de buceo recreativo|sesiones de buceo recreativo
Guia de museo|visitas a museos
Agente de cruceros|reservas de cruceros
Coordinador de transporte turistico|traslados turisticos
Encargado de campamento|servicios de campamento
Operador de turismo comunitario|experiencias comunitarias
""",
    "Tecnologia e informatica": """
Desarrollador frontend|interfaces web
Desarrollador backend|servicios de backend
Desarrollador full stack|aplicaciones full stack
Ingeniero DevOps|pipelines de desarrollo
Administrador de bases de datos|bases de datos
Analista de datos|conjuntos de datos
Cientifico de datos|modelos de datos
Ingeniero de aprendizaje automatico|proyectos de aprendizaje automatico
Administrador de sistemas|servidores y equipos
Tecnico de soporte informatico|solicitudes de soporte
Analista de ciberseguridad defensiva|controles de defensa digital
Disenador de experiencia de usuario|investigaciones UX
Ingeniero de pruebas de software|pruebas de software
Arquitecto de software|arquitecturas de aplicaciones
Disenador de videojuegos|sistemas de juego
Desarrollador movil|aplicaciones moviles
Ingeniero de nube|infraestructura de nube
Tecnico de redes informaticas|redes locales
Gestor de contenidos web|publicaciones web
Ingeniero de integracion API|integraciones de API
""",
    "Ciencia e investigacion": """
Fisico|experimentos de fisica
Quimico|analisis quimicos
Biologo|observaciones biologicas
Matematico|investigaciones matematicas
Estadistico|estudios estadisticos
Astronomo|observaciones astronomicas
Geologo|muestras geologicas
Oceanografo|campanas oceanograficas
Antropologo|estudios antropologicos
Arqueologo|hallazgos arqueologicos
Sociologo|investigaciones sociales
Economista investigador|modelos economicos
Meteorologo|observaciones meteorologicas
Genetista|estudios geneticos
Microbiologo|cultivos microbiologicos
Ecologo|inventarios ecologicos
Geografo|datos geograficos
Linguista|corpus linguisticos
Historiador|fuentes historicas
Analista de materiales|ensayos de materiales
""",
    "Medio ambiente y energia": """
Ingeniero ambiental|proyectos de gestion ambiental
Tecnico de reciclaje|procesos de reciclaje
Gestor de residuos|rutas de residuos
Guardaparques|recorridos de conservacion
Gestor de cuencas|monitoreos de cuencas
Analista de calidad del aire|muestras de calidad del aire
Operador de depuradora|operaciones de depuracion
Tecnico de energia solar|sistemas de energia solar
Ingeniero eolico|parques eolicos
Auditor energetico|auditorias de consumo energetico
Tecnico forestal|manejos forestales
Bombero forestal|prevencion de incendios forestales
Restaurador ecologico|proyectos de restauracion ecologica
Consultor de biodiversidad|estudios de biodiversidad
Analista de huella de carbono|inventarios de emisiones
Tecnico de eficiencia termica|sistemas de eficiencia termica
Inspector ambiental de vertidos|revisiones de vertidos
Tecnico de residuos peligrosos|residuos peligrosos
Educador ambiental|talleres de educacion ambiental
Conservacionista de fauna|monitoreos de fauna
""",
    "Industria y manufactura": """
Operador textil|procesos textiles
Modista|prendas a medida
Patronista|patrones de confeccion
Inspector de calidad industrial|controles de calidad industrial
Ingeniero de procesos|procesos de produccion
Operador de CNC|piezas mecanizadas
Ensamblador electrico|ensambles electricos
Supervisor de fabrica|turnos de fabrica
Impresor industrial|tirajes de impresion
Tornero|piezas torneadas
Fresador|piezas fresadas
Joyero|piezas de joyeria
Vidriero|productos de vidrio
Alfarero|piezas de ceramica
Ebanista|muebles de madera
Tecnico de embalaje|embalajes industriales
Inspector de metrologia|mediciones industriales
Operador de envasado|lineas de envasado
Disenador industrial|prototipos de producto
Tecnico de mantenimiento productivo|equipos de produccion
""",
    "Administracion y finanzas": """
Contador|registros contables
Auditor financiero|revisiones financieras
Analista presupuestario|presupuestos institucionales
Responsable de compras|procesos de compras
Asistente administrativo|tramites administrativos
Secretario ejecutivo|agendas de direccion
Tesorero|flujos de tesoreria
Gestor de nomina|procesos de nomina
Analista de riesgos empresariales|matrices de riesgos
Gerente de proyectos|carteras de proyectos
Administrador de ONG|proyectos de organizaciones sociales
Responsable de recursos humanos|procesos de talento humano
Gestor documental|fondos documentales
Analista de inventarios|inventarios empresariales
Consultor de negocios|diagnosticos empresariales
Planificador estrategico|planes estrategicos
Gestor de subvenciones|convocatorias de subvenciones
Coordinador de voluntariado|equipos de voluntariado
Analista tributario|registros tributarios
Auxiliar de facturacion|documentos de facturacion
""",
    "Derecho y servicio publico": """
Abogado laboral|casos de derecho laboral
Abogado civil|expedientes civiles
Abogado de familia|expedientes familiares
Notario|documentos notariales
Mediador comunitario|sesiones de mediacion
Funcionario de registro civil|tramites registrales
Gestor municipal|servicios municipales
Archivista publico|archivos administrativos publicos
Inspector municipal|actas de inspeccion municipal
Asesor de consumo|reclamaciones de consumo
Trabajador social|intervenciones sociales
Funcionario de migracion|tramites migratorios
Gestor de politicas publicas|programas publicos
Analista de contratacion publica|expedientes de contratacion
Defensor comunitario|solicitudes comunitarias
Traductor juridico|traducciones juridicas
Coordinador de atencion ciudadana|peticiones ciudadanas
Conciliador vecinal|acuerdos vecinales
Especialista de transparencia|solicitudes de transparencia
Asesor de procedimientos administrativos|procedimientos administrativos
""",
    "Arte cultura y medios": """
Artista plastico|obras plasticas
Ilustrador|ilustraciones editoriales
Animador 2D|animaciones bidimensionales
Animador 3D|animaciones tridimensionales
Fotografo de estudio|sesiones fotograficas
Fotografo documental|reportajes fotograficos
Editor de video|proyectos de montaje de video
Disenador de sonido|ediciones sonoras
Musico instrumentista|presentaciones musicales
Compositor musical|composiciones musicales
Director de teatro|montajes teatrales
Actor|interpretaciones actorales
Guionista audiovisual|guiones audiovisuales
Novelista|manuscritos literarios
Disenador grafico|piezas de diseno grafico
Periodista|reportajes periodisticos
Locutor|producciones de locucion
Editor literario|ediciones de libros
Conservador de museo|colecciones museisticas
Productor audiovisual|producciones audiovisuales
""",
    "Servicios personales y cuidado": """
Cuidador de personas mayores|servicios de acompanamiento a mayores
Cuidador infantil|actividades de cuidado infantil
Peluquero|servicios de peluqueria
Barbero|servicios de barberia
Esteticista|servicios de estetica
Masajista de bienestar|sesiones de masaje no clinico
Tatuador|proyectos de tatuajes
Limpiador profesional|servicios de limpieza profesional
Jardinero|trabajos de jardineria
Florista|arreglos florales
Paseador de mascotas|rutas de paseo de mascotas
Adiestrador canino|sesiones de entrenamiento canino
Organizador de hogares|organizaciones domesticas
Asistente domestico|tareas de asistencia domestica
Limpiacristales|servicios de limpieza de cristales
Administrador de edificios|mantenimiento de edificios
Tecnico de lavanderia|servicios de lavanderia
Personal funerario|servicios funerarios
Coordinador de centro de dia|actividades de centro de dia
Auxiliar de apoyo a discapacidad|actividades de apoyo a discapacidad
""",
    "Deporte y recreacion": """
Entrenador de futbol|sesiones de futbol
Entrenador de baloncesto|sesiones de baloncesto
Entrenador de atletismo|practicas de atletismo
Entrenador de natacion|sesiones de natacion
Entrenador de gimnasia|sesiones de gimnasia
Entrenador de ciclismo|practicas de ciclismo
Instructor de yoga|sesiones de yoga
Entrenador personal|sesiones de entrenamiento personal
Arbitro de futbol|encuentros arbitrados
Preparador fisico|planificaciones fisicas
Entrenador de deportes adaptados|sesiones de deporte adaptado
Monitor de senderismo|rutas de senderismo
Guia de escalada recreativa|practicas de escalada recreativa
Coordinador de actividades recreativas|programas recreativos
Gestor de instalaciones deportivas|reservas de instalaciones deportivas
Analista de rendimiento deportivo|mediciones de rendimiento deportivo
Instructor de danza|clases de danza
Gestor de eventos deportivos|encuentros deportivos
Entrenador de deportes electronicos|equipos de deportes electronicos
Monitor de juegos tradicionales|talleres de juegos tradicionales
""",
    "Seguridad y emergencias": """
Bombero urbano|actividades de estacion de bomberos
Operador de llamadas de emergencia|registros anonimos de llamadas de emergencia
Agente de transito|gestiones de movilidad vial
Policia comunitario|programas de proximidad comunitaria
Investigador de incendios|informes de causas de incendio
Tecnico de prevencion de riesgos|evaluaciones preventivas
Coordinador de proteccion civil|planes de preparacion comunitaria
Socorrista acuatico|turnos de vigilancia acuatica
Guardia de seguridad privada|rondas de seguridad fisica
Inspector de seguridad laboral|inspecciones preventivas laborales
Operador de centro de alarmas|bitacoras de central de alarmas
Rescatista de montana|entrenamientos de rescate de montana
Coordinador de busqueda y rescate|programas de formacion de rescate
Especialista en evacuacion|simulacros de evacuacion
Auditor de seguridad edilicia|inspecciones de seguridad edilicia
Coordinador de refugios temporales|instalaciones de refugio temporal
Instructor de primeros auxilios|talleres de primeros auxilios
Analista de gestion de riesgos|mapas de riesgos comunitarios
Guardacostas civil|actividades preventivas de guardacostas
Mediador de conflictos|intervenciones de mediacion preventiva
""",
}

# Una propuesta por necesidad REAL del oficio. Son aplicaciones completas,
# no cinco variantes visuales del mismo producto.
# formato: titulo con {foco} | problema | funciones | resultado | tipo_app
TASKS = {
    "Salud y asistencia sanitaria": """
Agenda de atenciones de {foco}|organizar turnos y tiempos de atencion|calendario; cupos; lista de espera; recordatorios|agenda verificable|Organizacion
Inventario de insumos para {foco}|prever materiales necesarios sin desperdicio|existencias; lotes; vencimientos; alertas|control de materiales|Gestion
Bitacora anonimizada de {foco}|documentar actividad sin identificar a personas atendidas|plantillas anonimas; fechas; indicadores; exportacion|registro agregado de actividad|Registro
Checklist de preparacion de {foco}|comprobar el estado de materiales antes de iniciar una actividad|listas configurables; confirmaciones; incidencias; historial|lista de preparacion completada|Revision
Simulador formativo de {foco}|practicar decisiones en casos ficticios sin utilizarse para diagnosticos|casos simulados; alternativas; retroalimentacion; niveles|practica educativa sin uso clinico|Simulacion
Biblioteca de procedimientos de {foco}|localizar rapidamente guias internas autorizadas|fichas; versionado; etiquetas; marcadores|biblioteca de consulta interna|Consulta
Plan de turnos y relevo de {foco}|coordinar relevos sin perder tareas pendientes|turnos; pendientes; asignaciones; avisos|traspaso ordenado entre turnos|Productividad
Panel de actividad de {foco}|conocer cargas de trabajo sin publicar datos sensibles|metricas agregadas; filtros; series; CSV|reporte estadistico anonimo|Analitica
""",
    "Educacion y formacion": """
Planificador didactico de {foco}|ordenar objetivos y sesiones de aprendizaje|objetivos; calendario; unidades; materiales|plan de sesiones coherente|Educacion
Banco de ejercicios de {foco}|reutilizar actividades graduadas|preguntas; niveles; soluciones; etiquetas|coleccion de ejercicios|Educacion
Evaluador formativo de {foco}|ofrecer retroalimentacion sobre practicas sin sustituir al docente|rubricas; evidencias; comentarios; progreso|reporte formativo|Educacion
Biblioteca de recursos de {foco}|evitar dispersion de materiales didacticos|catalogo; metadatos; filtros; enlaces|biblioteca navegable|Organizacion
Simulador educativo de {foco}|permitir practicas con escenarios ficticios|escenarios; decisiones; pistas; resultados|laboratorio didactico|Simulacion
Juego de retos de {foco}|practicar contenidos de forma ludica|misiones; intentos; logros; progreso|juego con niveles|Juego
Portafolio de evidencias de {foco}|reunir muestras de progreso por proyectos|proyectos; archivos; comentarios; exportacion|portafolio de aprendizaje|Productividad
Plan de recuperacion en {foco}|identificar temas pendientes y organizar refuerzo|diagnostico formativo; rutas; ejercicios; seguimiento|ruta personalizada de repaso|Educacion
""",
    "Agricultura y ganaderia": """
Calendario productivo de {foco}|organizar labores estacionales|etapas; calendario; dependencias; avisos|plan de temporada|Productividad
Control de insumos de {foco}|registrar existencias y consumo de materiales|inventario; entradas; salidas; alertas|stock disponible|Gestion
Bitacora de campo de {foco}|documentar observaciones a lo largo de la temporada|fechas; parcelas; notas; adjuntos|historial productivo|Registro
Calculadora de costos de {foco}|estimar gastos por lote o campana|insumos; mano de obra; escenarios; reportes|presupuesto editable|Analitica
Trazabilidad de lotes de {foco}|relacionar lotes con eventos de produccion|etiquetas; fechas; movimientos; exportacion|historial por lote|Organizacion
Simulador educativo de {foco}|comparar decisiones de produccion sin recomendacion automatica obligatoria|supuestos; escenarios; parametros; graficos|comparacion de escenarios|Simulacion
Mantenimiento de equipamiento de {foco}|no olvidar revisiones preventivas|maquinas; vencimientos; checklists; historial|calendario de mantenimiento|Gestion
Panel de rendimientos de {foco}|comparar resultados historicos|indicadores; series; categorias; CSV|resumen de produccion|Analitica
""",
    "Pesca y acuicultura": """
Registro de faenas de {foco}|organizar operaciones y condiciones declaradas|bitacora; fechas; equipos; incidencias|historial operativo|Registro
Planificador de insumos de {foco}|anticipar recursos necesarios|existencias; reservas; avisos; proveedores|plan de materiales|Gestion
Trazabilidad de producto y muestras de {foco}|documentar origen y movimientos|identificadores; fechas; lotes; reportes|ruta documental del producto|Organizacion
Control de equipos de {foco}|registrar revisiones preventivas|inventario; checklists; historial; alertas|agenda de equipamiento|Revision
Panel de condiciones observadas de {foco}|conservar registros ambientales y operativos|formularios; series; filtros; CSV|historial de condiciones|Analitica
Calculadora de consumo de {foco}|comparar combustible o materiales utilizados|cantidades; precios; supuestos; resumen|costos estimados|Analitica
Simulador de sostenibilidad de {foco}|mostrar consecuencias hipoteticas de extraccion y cuidado|escenarios; limites editables; graficos; ejercicios|simulacion educativa|Simulacion
Centro de documentacion de {foco}|encontrar fichas y registros por actividad|archivos; etiquetas; busqueda; favoritos|archivo especializado|Organizacion
""",
    "Construccion y arquitectura": """
Planificador de etapas de {foco}|ordenar actividades y dependencias de proyecto|cronograma; hitos; tareas; responsables|plan de ejecucion|Productividad
Calculadora de materiales de {foco}|preparar estimaciones configurables de suministros|medidas; coeficientes; mermas; presupuesto|estimacion documentada|Analitica
Registro fotografico de {foco}|documentar avances y observaciones en obra|fotos; fechas; ubicaciones; etiquetas|bitacora visual|Registro
Checklist preventivo de {foco}|documentar verificaciones preparatorias|criterios editables; estados; evidencias; informe|lista de verificacion|Revision
Control de presupuestos de {foco}|revisar diferencias entre costos previstos y registrados|partidas; importes; variaciones; graficos|balance de costos|Analitica
Gestor de planos de {foco}|administrar revisiones de archivos tecnicos|versiones; marcadores; comparacion; exportacion|archivo de planos versionado|Organizacion
Inventario de equipos para {foco}|coordinar herramientas y mantenimiento|equipos; asignaciones; vencimientos; historial|registro de equipos|Gestion
Simulador formativo de {foco}|practicar secuencias de trabajo en escenarios ficticios|pasos; incidencias; decisiones; pistas|practica educativa|Simulacion
""",
    "Instalaciones y mantenimiento": """
Agenda de intervenciones de {foco}|coordinar visitas y mantenimientos|clientes; fechas; tareas; confirmaciones|agenda de intervenciones|Productividad
Diagnostico documentado de {foco}|guardar sintomas y resultados de inspeccion sin automatizar reparaciones peligrosas|fichas; hallazgos; adjuntos; exportacion|informe de observaciones|Registro
Inventario de repuestos para {foco}|controlar materiales requeridos|referencias; existencias; ubicaciones; avisos|inventario de repuestos|Gestion
Historial de mantenimiento de {foco}|seguir servicios realizados por equipo|fichas; fechas; tareas; costos|trazabilidad de mantenimiento|Organizacion
Calculadora de presupuestos de {foco}|estimar trabajo y materiales con tarifas propias|partidas; cantidades; tarifas; PDF|presupuesto desglosado|Analitica
Checklist de puesta en servicio de {foco}|no omitir pasos documentales de entrega|verificaciones editables; evidencias; estados; firma interna|acta de entrega|Revision
Planificador de mantenimiento preventivo de {foco}|anticipar revisiones recurrentes|periodicidades; calendario; recordatorios; equipos|plan preventivo|Productividad
Biblioteca tecnica de {foco}|consultar manuales y fichas propias|documentos; busqueda; versiones; favoritos|repositorio tecnico|Consulta
""",
    "Transporte y logistica": """
Planificador de rutas de {foco}|ordenar itinerarios y ventanas de trabajo|paradas; horarios; cargas; incidencias|plan de ruta|Productividad
Bitacora de operaciones de {foco}|conservar eventos y novedades declaradas|fechas; ubicaciones; adjuntos; reportes|historial operativo|Registro
Control de disponibilidad de {foco}|saber que recursos estan asignados|recursos; calendario; reservas; estados|tablero de disponibilidad|Gestion
Checklist documental de {foco}|verificar documentos y permisos cargados por el usuario|expedientes; vencimientos; alertas; exportacion|registro documental|Revision
Calculadora de costos de {foco}|estimar combustible materiales y tiempos declarados|tarifas; cantidades; kilometraje; escenarios|presupuesto de operacion|Analitica
Panel de puntualidad de {foco}|comparar horarios registrados con planificados|hitos; tiempos; filtros; graficos|indicadores de puntualidad|Analitica
Centro de mantenimiento de {foco}|dar seguimiento a equipos de transporte|activos; tareas; revisiones; historial|agenda de mantenimiento|Gestion
Simulador de contingencias de {foco}|entrenar con situaciones operativas ficticias sin reemplazar normas|escenarios; opciones; consecuencias; aprendizaje|simulador formativo|Simulacion
""",
    "Comercio y ventas": """
Catalogo de productos de {foco}|reunir informacion comercial en un solo lugar|fichas; fotos; precios; busqueda|catalogo consultable|Comercio
Agenda de clientes de {foco}|registrar contactos y solicitudes|clientes; citas; notas; etiquetas|agenda comercial|Organizacion
Control de stock de {foco}|prevenir faltantes y sobrantes|entradas; salidas; minimo; alertas|inventario actualizado|Gestion
Cotizador de {foco}|construir presupuestos con reglas editables|productos; descuentos; impuestos configurables; PDF|cotizacion detallada|Comercio
Panel de ventas de {foco}|conocer productos y periodos de mayor actividad|ventas; categorias; graficos; CSV|reporte comercial|Analitica
Organizador de pedidos de {foco}|seguir pedidos desde recepcion hasta entrega|estados; responsables; fechas; notas|control de pedidos|Productividad
Simulador de atencion en {foco}|practicar conversaciones comerciales respetuosas|casos ficticios; opciones; feedback; niveles|entrenamiento comercial|Simulacion
Registro de devoluciones de {foco}|documentar reclamos y soluciones|casos; fechas; motivos; resoluciones|historial de incidencias|Registro
""",
    "Gastronomia y alimentacion": """
Planificador de produccion de {foco}|ordenar lotes y turnos de preparacion|recetas; cantidades; calendario; equipos|plan de produccion|Productividad
Fichero de recetas de {foco}|estandarizar preparaciones propias|ingredientes; versiones; fotos; pasos|recetario tecnico|Organizacion
Control de materias primas de {foco}|registrar disponibilidad y fechas de uso|lotes; vencimientos; entradas; alertas|inventario alimentario|Gestion
Calculadora de costos de {foco}|estimar costo por porcion o producto|ingredientes; rendimientos; precios; escenarios|ficha de costos|Analitica
Registro de temperaturas de {foco}|documentar mediciones aportadas por el usuario|formularios; horas; series; alertas configurables|bitacora de mediciones|Registro
Checklist de higiene de {foco}|seguir rutinas preventivas documentadas|criterios editables; responsables; evidencias; informe|control preventivo|Revision
Organizador de pedidos de {foco}|coordinar preparaciones y entregas|pedidos; prioridades; estados; avisos|tablero de pedidos|Productividad
Simulador de capacidad de {foco}|comparar escenarios de volumen y turnos|insumos; tiempos; escenarios; graficos|estimacion de capacidad|Simulacion
""",
    "Turismo y hoteleria": """
Calendario de reservas de {foco}|organizar disponibilidad y solicitudes|cupos; calendario; fichas; confirmaciones|agenda de reservas|Productividad
Creador de itinerarios de {foco}|diseñar actividades por tramos|paradas; horarios; duraciones editables; exportacion|itinerario compartible|Organizacion
Catalogo de experiencias de {foco}|ordenar ofertas y servicios|fichas; fotos; etiquetas; tarifas|catalogo de servicios|Comercio
Registro de incidencias de {foco}|documentar novedades y su tratamiento|formularios; estados; responsables; archivo|historial de incidencias|Registro
Gestor de recursos de {foco}|controlar disponibilidad de instalaciones y materiales|inventario; reservas; mantenimiento; avisos|panel de recursos|Gestion
Calculadora de presupuestos de {foco}|estimar costos de servicios turisticos|tarifas; conceptos; escenarios; PDF|presupuesto desglosado|Analitica
Simulador de atencion de {foco}|ensayar comunicacion con viajeros en situaciones ficticias|dialogos; opciones; pistas; progresion|entrenamiento de atencion|Simulacion
Panel de satisfaccion de {foco}|resumir opiniones voluntarias sin identificar personas|formularios anonimos; temas; graficos; CSV|resumen de experiencia|Analitica
""",
    "Tecnologia e informatica": """
Gestor de incidencias de {foco}|controlar problemas reproducibles y correcciones|tickets; prioridad; estados; historial|tablero de incidencias|Desarrollo
Mapa de dependencias de {foco}|identificar componentes relacionados|nodos; enlaces; versiones; visualizador|grafo de dependencias|Desarrollo
Laboratorio de pruebas de {foco}|guardar escenarios de prueba y resultados|casos; ejecuciones; resultados; comparacion|reporte de pruebas|Desarrollo
Documentador de {foco}|mantener documentacion tecnica actualizada|secciones; ejemplos; versionado; exportacion|manual tecnico|Documentacion
Panel de rendimiento de {foco}|comparar metricas de sistemas o trabajos|series; umbrales configurables; graficos; CSV|tablero de rendimiento|Analitica
Generador de proyectos de {foco}|crear estructuras iniciales compatibles con estandares propios|plantillas; carpetas; presets; empaquetado|esqueleto de proyecto|Desarrollo
Auditor de configuracion de {foco}|registrar diferencias contra configuraciones declaradas|inventario; reglas; diff; informe|informe de configuracion|Revision
Simulador defensivo de {foco}|aprender en entornos ficticios sin tocar sistemas de terceros|escenarios aislados; logs de ejemplo; pistas; evaluacion|laboratorio formativo|Simulacion
""",
    "Ciencia e investigacion": """
Bitacora de experimentos de {foco}|conservar procedimiento y observaciones|protocolos; fechas; muestras; notas|cuaderno de investigacion|Investigacion
Organizador de bibliografia de {foco}|encontrar articulos y referencias propias|referencias; etiquetas; busqueda; citas|biblioteca documental|Organizacion
Validador de conjuntos de datos de {foco}|detectar valores faltantes o formatos inconsistentes|reglas; perfiles; alertas; exportacion|reporte de calidad de datos|Analitica
Visualizador de resultados de {foco}|explorar tendencias y distribuciones registradas|graficos; filtros; tablas; exportacion|panel de resultados|Analitica
Planificador de muestreos de {foco}|definir cronogramas y trazabilidad de muestras|muestras; lotes; tiempos; estados|plan de muestreo|Investigacion
Simulador educativo de {foco}|probar hipotesis con datos ficticios|parametros; escenarios; graficos; explicaciones|laboratorio formativo|Simulacion
Gestor de equipamiento de {foco}|mantener control de instrumentos y calibraciones|equipos; verificaciones; fechas; historial|inventario tecnico|Gestion
Repositorio reproducible de {foco}|organizar insumos scripts resultados y versiones|archivos; hashes; metadatos; exportacion|paquete de investigacion|Investigacion
""",
    "Medio ambiente y energia": """
Mapa de observaciones de {foco}|organizar registros geograficos declarados|coordenadas; capas; fechas; exportacion|visor georreferenciado|Ambiental
Bitacora de mediciones de {foco}|seguir mediciones ambientales y cambios|formularios; sensores manuales; graficos; alertas|historial ambiental|Registro
Planificador de inspecciones de {foco}|programar revisiones y visitas|calendario; lugares; checklist; informe|agenda de inspeccion|Productividad
Calculadora de indicadores de {foco}|estimar consumos o emisiones con supuestos editables|factores configurables; escenarios; graficos; CSV|estimacion transparente|Analitica
Inventario de recursos de {foco}|controlar materiales y equipos|fichas; cantidades; ubicaciones; mantenimiento|inventario operativo|Gestion
Centro de evidencias de {foco}|organizar fotos documentos y muestras|adjuntos; etiquetas; fechas; archivo|expediente ambiental|Organizacion
Simulador didactico de {foco}|comparar escenarios hipoteticos de sostenibilidad|supuestos; parametros; visualizaciones; ejercicios|escenarios educativos|Simulacion
Panel de evolucion de {foco}|mostrar tendencias temporales y eventos relevantes|series; filtros; anotaciones; reportes|tablero de tendencias|Analitica
""",
    "Industria y manufactura": """
Planificador de lotes de {foco}|ordenar trabajos y prioridades de produccion|ordenes; calendario; recursos; estados|plan de fabricacion|Productividad
Control de calidad documentado de {foco}|registrar inspecciones contra criterios editables|criterios; muestras; evidencias; informe|ficha de control|Revision
Inventario de herramientas de {foco}|controlar ubicacion y mantenimiento de equipos|activos; responsables; fechas; alertas|inventario de equipos|Gestion
Calculadora de materiales de {foco}|estimar materias primas y desperdicios|formulas editables; lotes; mermas; costos|estimacion productiva|Analitica
Bitacora de produccion de {foco}|registrar eventos por turno|fechas; cantidades; incidencias; exportacion|historial de produccion|Registro
Gestor de trazabilidad de {foco}|relacionar insumos productos y lotes|lotes; etapas; movimientos; etiquetas|trazabilidad por pieza|Organizacion
Simulador formativo de {foco}|ensayar decisiones de calidad con ejemplos ficticios|escenarios; opciones; consecuencias; feedback|entrenamiento de planta|Simulacion
Panel de rendimiento de {foco}|comparar produccion planificada y observada|indicadores; turnos; graficos; CSV|reporte de produccion|Analitica
""",
    "Administracion y finanzas": """
Agenda de procesos de {foco}|ordenar fechas y actividades recurrentes|calendario; tareas; responsables; avisos|calendario operativo|Productividad
Consolidador de registros de {foco}|reunir hojas y formularios sin duplicar|importacion; validaciones; filtros; exportacion|consolidado de registros|Gestion
Panel de indicadores de {foco}|comparar datos financieros u operativos|kpis configurables; series; filtros; reportes|tablero gerencial|Analitica
Generador de informes de {foco}|estructurar documentos periodicos con datos declarados|plantillas; secciones; tablas; exportacion|informe editable|Documentacion
Control de expedientes de {foco}|mantener seguimiento por tramite o expediente|estados; etiquetas; fechas; historial|registro de expedientes|Organizacion
Simulador de presupuestos de {foco}|comparar escenarios sin ejecutar operaciones reales|supuestos; proyecciones; graficos; exportacion|comparador de presupuestos|Simulacion
Biblioteca de procedimientos de {foco}|centralizar instructivos y controles internos|documentos; versiones; favoritos; busqueda|manual de procesos|Consulta
Auditor de coherencia de {foco}|identificar campos vacios y discrepancias formales|reglas editables; alertas; evidencias; informe|reporte de inconsistencias|Revision
""",
    "Derecho y servicio publico": """
Agenda de plazos de {foco}|ordenar vencimientos declarados sin asesorar sobre fechas legales|hitos editables; avisos; responsables; notas|agenda de tramites|Productividad
Organizador de expedientes de {foco}|mantener documentos relacionados y versiones|carpetas; etiquetas; estados; busqueda|expediente ordenado|Organizacion
Plantillas documentales de {foco}|preparar borradores revisables por profesionales|formatos; variables; versionado; exportacion|documento de trabajo|Documentacion
Registro de solicitudes de {foco}|seguir peticiones y respuestas|numeros; fechas; estados; anexos|tablero de solicitudes|Registro
Biblioteca de referencias de {foco}|consultar normas y fuentes cargadas por el usuario|documentos; etiquetas; versiones; busqueda|biblioteca de referencias|Consulta
Cuadro de seguimiento de {foco}|revisar actividad y estados sin datos personales|indicadores; filtros; reportes; CSV|panel administrativo|Analitica
Simulador educativo de {foco}|practicar entrevistas y tramites ficticios|casos ficticios; dialogos; opciones; feedback|entrenamiento administrativo|Simulacion
Checklist documental de {foco}|verificar integridad de anexos segun reglas declaradas|requisitos editables; adjuntos; alertas; informe|lista documental completa|Revision
""",
    "Arte cultura y medios": """
Portafolio de {foco}|reunir proyectos y mostrar procesos creativos|obras; galerias; versiones; exportacion|portafolio navegable|Creatividad
Planificador de produccion de {foco}|dividir proyectos creativos en tareas y etapas|cronograma; recursos; hitos; notas|plan de produccion|Productividad
Catalogador de archivos de {foco}|encontrar recursos digitales y obras|metadatos; etiquetas; favoritos; filtros|archivo creativo|Organizacion
Control de permisos de {foco}|registrar licencias y autorizaciones declaradas|titulares; usos; fechas; anexos|registro de permisos|Documentacion
Presupuestador de proyectos de {foco}|estimar honorarios gastos y materiales|conceptos; cantidades; tarifas; exportacion|presupuesto de proyecto|Analitica
Diario de proceso de {foco}|documentar cambios e ideas de una obra|entradas; bocetos; archivos; lineas de tiempo|bitacora creativa|Registro
Galeria interactiva de {foco}|publicar colecciones navegables sin servicios externos|salas; fichas; multimedia; busqueda|exposicion digital local|Publicacion
Editor de fichas de {foco}|preparar entregables con credito y ficha tecnica|plantillas; textos; imagenes; exportacion|dossier de proyecto|Creatividad
""",
    "Servicios personales y cuidado": """
Agenda de servicios de {foco}|coordinar citas y disponibilidades|horarios; reservas; recordatorios; estados|agenda de servicios|Productividad
Ficha de preferencias de {foco}|registrar necesidades declaradas con privacidad local|preferencias; notas; consentimientos; busqueda|ficha de atencion|Registro
Inventario de materiales de {foco}|controlar productos y herramientas de trabajo|entradas; salidas; alertas; proveedores|inventario operativo|Gestion
Calculadora de tarifas de {foco}|estimar precios transparentes segun tiempo y recursos|tarifas; duracion; materiales; descuentos|presupuesto editable|Analitica
Checklist de preparacion de {foco}|confirmar materiales y condiciones de servicio|criterios editables; registros; avisos; historial|lista de preparacion|Revision
Panel de citas de {foco}|comparar demanda por periodo y servicio|calendario; conteos; graficos; CSV|estadisticas de ocupacion|Analitica
Biblioteca de ideas de {foco}|organizar estilos ejemplos y guias propias|imagenes; etiquetas; fichas; favoritos|coleccion de referencias|Consulta
Diario de seguimiento de {foco}|conservar observaciones no clinicas y tareas posteriores|fechas; notas; responsables; archivo|historial de actividad|Registro
""",
    "Deporte y recreacion": """
Agenda de sesiones de {foco}|planificar entrenamientos encuentros o talleres|calendario; grupos; material; estados|programacion deportiva|Productividad
Registro de progresos de {foco}|comparar indicadores voluntarios y actividades|mediciones manuales; historico; graficos; CSV|evolucion documentada|Analitica
Biblioteca de ejercicios de {foco}|ordenar actividades segun metas educativas|fichas; niveles; materiales; etiquetas|coleccion de actividades|Educacion
Gestor de instalaciones de {foco}|coordinar espacios y equipos reservados|reservas; mantenimiento; disponibilidad; alertas|cuadro de instalaciones|Gestion
Simulador educativo de {foco}|practicar decisiones deportivas con ejemplos ficticios|jugadas simuladas; estrategias; feedback; niveles|juego formativo|Juego
Organizador de eventos de {foco}|coordinar participantes y cronogramas|inscripciones; horarios; resultados; avisos|agenda de evento|Productividad
Inventario de material de {foco}|administrar equipamiento y prestamos|fichas; asignaciones; devoluciones; alertas|inventario deportivo|Organizacion
Panel de participacion de {foco}|resumir actividad de grupos sin datos sensibles|conteos; categorias; tendencias; exportacion|reporte agregado|Analitica
""",
    "Seguridad y emergencias": """
Plan de simulacros de {foco}|organizar ejercicios preventivos sin guiar intervenciones reales|calendario; responsables; listas; evaluacion|plan de simulacros|Productividad
Inventario preventivo de {foco}|controlar disponibilidad y revision de equipos|activos; vencimientos; mantenimiento; alertas|inventario preventivo|Gestion
Bitacora administrativa de {foco}|documentar novedades no sensibles y tareas|fechas; categorias; estados; adjuntos|registro administrativo|Registro
Mapa de recursos para {foco}|situar instalaciones y recursos declarados|mapas locales; etiquetas; filtros; exportacion|visor de recursos|Visualizacion
Evaluador documental de {foco}|revisar integridad de formularios y evidencias|reglas editables; checklists; incidencias; informe|revision documental|Revision
Simulador comunitario de {foco}|ensayar medidas de prevencion con escenarios ficticios|escenarios; opciones; preguntas; feedback|practica educativa|Simulacion
Agenda de capacitacion de {foco}|programar jornadas formativas y participantes|sesiones; listas; materiales; constancias|agenda formativa|Educacion
Panel agregado de actividad de {foco}|analizar conteos sin datos operativos sensibles|indicadores anonimos; periodos; graficos; CSV|reporte agregado|Analitica
""",
}

ALL_COLUMNS = ["id", "origen", "categoria", "tema", "profesion", "titulo", "publico", "problema", "descripcion", "funciones_principales", "resultado_esperado", "tipo_app", "alcance", "estado_desarrollo"]

def normalize(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def read_professions():
    assert len(ROLES) == 20, len(ROLES)
    assert set(ROLES) == set(TASKS)
    profiles = []
    for sector, raw in ROLES.items():
        rows = [x.strip() for x in raw.strip().splitlines() if x.strip()]
        assert len(rows) == 20, (sector, len(rows))
        for item in rows:
            name, focus = (x.strip() for x in item.split("|", 1))
            profiles.append((sector, name, focus))
    assert len({normalize(x[1]) for x in profiles}) == 400, "Profesion duplicada"
    return profiles


def read_tasks(sector):
    rows = [x.strip() for x in TASKS[sector].strip().splitlines() if x.strip()]
    assert len(rows) == 8, (sector, len(rows))
    parsed = []
    for entry in rows:
        title, problem, features, result, kind = (x.strip() for x in entry.split("|"))
        assert "{foco}" in title
        parsed.append((title, problem, features, result, kind))
    return parsed


def write_catalog():
    profiles = read_professions()
    assert SOURCE.exists(), SOURCE
    OUT_ALL.parent.mkdir(parents=True, exist_ok=True)
    saved_titles = set()
    old_rows = 0
    with SOURCE.open(encoding="utf-8-sig", newline="") as src, OUT_ALL.open("w", encoding="utf-8-sig", newline="") as fdest:
        old = csv.DictReader(src, delimiter=";")
        merged = csv.DictWriter(fdest, fieldnames=ALL_COLUMNS, delimiter=";")
        merged.writeheader()
        for item in old:
            old_rows += 1
            assert int(item["id"]) == old_rows
            title_key = normalize(item["titulo"])
            assert title_key not in saved_titles, f"Titulo previo repetido: {item['titulo']}"
            saved_titles.add(title_key)
            row = {**item, "id": old_rows, "origen": "SOCIEDAD", "profesion": "", "alcance": "General"}
            merged.writerow({col: row.get(col, "") for col in ALL_COLUMNS})
        assert old_rows == 22000, old_rows
        with OUT_JOBS.open("w", encoding="utf-8-sig", newline="") as jobfile:
            jobs = csv.DictWriter(jobfile, fieldnames=ALL_COLUMNS, delimiter=";")
            jobs.writeheader()
            n = 0
            for sector, profession, focus in profiles:
                for title_fmt, problem, features, result, kind in read_tasks(sector):
                    n += 1
                    title = f"{title_fmt.format(foco=focus)} | {profession}"
                    title_key = normalize(title)
                    assert title_key not in saved_titles, f"Titulo duplicado: {title}"
                    saved_titles.add(title_key)
                    desc = (f"Aplicacion PTM para la ocupacion {profession.lower()}: {problem}. "
                            f"Cubre {focus} con {features.replace('; ', ', ')}. "
                            "Preparada para uso local y adaptacion de requisitos por pais; "
                            "no sustituye certificaciones, regulaciones ni criterio profesional.")
                    row = {
                        "id": old_rows + n,
                        "origen": "PROFESION",
                        "categoria": sector,
                        "tema": focus,
                        "profesion": profession,
                        "titulo": title,
                        "publico": f"Profesionales de {profession.lower()} y sus equipos",
                        "problema": f"En {focus}, quienes trabajan como {profession.lower()} necesitan {problem}.",
                        "descripcion": desc,
                        "funciones_principales": features,
                        "resultado_esperado": result,
                        "tipo_app": kind,
                        "alcance": "Internacional adaptable por pais",
                        "estado_desarrollo": "PENDIENTE",
                    }
                    merged.writerow(row)
                    jobs.writerow(row)
    assert n == 3200, n
    assert old_rows+n == 25200
    return validate()


def validate():
    allcounts = Counter()
    sectors = Counter()
    roles = set()
    keys = set()
    with OUT_ALL.open(encoding="utf-8-sig", newline="") as f:
        rows = csv.DictReader(f, delimiter=";")
        assert rows.fieldnames == ALL_COLUMNS
        for i, r in enumerate(rows, start=1):
            assert str(i) == r["id"]
            assert all(r[x].strip() for x in ("categoria","tema","titulo","problema","descripcion","funciones_principales","resultado_esperado","tipo_app"))
            allcounts[r["origen"]] += 1
            if r["origen"] == "PROFESION":
                roles.add(r["profesion"])
                sectors[r["categoria"]] += 1
            key = normalize(r["titulo"])
            assert key not in keys, f"Duplicado: {key}"
            keys.add(key)
    assert allcounts == {"SOCIEDAD":22000, "PROFESION":3200}, allcounts
    assert len(roles) == 400 and len(sectors) == 20
    assert all(x == 160 for x in sectors.values()), sectors
    return {"total":len(keys),"sociales":22000,"profesionales":3200,
            "ocupaciones":len(roles),"sectores":len(sectors),
            "csv_combinado":str(OUT_ALL),"csv_profesiones":str(OUT_JOBS),
            "tamano_combinado_bytes":OUT_ALL.stat().st_size}


if __name__ == "__main__":
    print(write_catalog())