# PYRION 3D Engine 0.2.0

Motor de renderizado 3D por software, independiente de OpenGL y de librerías externas.

## Escena principal (PYRION OS 0.4.1)

La escena predeterminada ahora muestra **únicamente una esfera tridimensional girando
infinitamente en el centro de la pantalla**, sobre un fondo oscuro uniforme.
No hay texto, barras, anillos orbitales, estrellas, indicadores ni botones visibles.
La geometría UV de la esfera tiene 546 vértices y 1.088 triángulos.

## Ejecutar

- Desde `PYRION/`: `python app.py --windowed --no-update` para pruebas.
- Desde `PYRION/`: `python app.py` para el escritorio a pantalla completa y OTA.
- Alternativa modular: `python -m engine3d` desde `PYRION/`.

## Controles opcionales, sin elementos gráficos

- Arrastrar la esfera: cambiar orientación.
- Rueda del mouse, `+` y `-`: zoom.
- Espacio: pausar o continuar el giro.
- Flecha izquierda/derecha: variar la velocidad.
- `F11` o `Escape`: salir de pantalla completa al modo ventana.
- `Ctrl+Q`: cerrar.

## Arquitectura

- `mesh.py`: esfera UV y topología de triángulos.
- `renderer.py`: cámara, proyección, iluminación y material procesal.
- `app.py`: escena minimalista, animación continua y eventos.
- `build.py`: genera `PYRION/app.py` autocontenido para el sistema de actualizaciones.

La versión previa del escritorio está archivada en
`PYRION/release/v0.4.0/`. No requiere Pillow ni GPU.

## Materiales de escena (PYRION 0.4.6)

El cargador de `scene.json` interpreta el atributo `material` de cada objeto.
La esfera de OnlyDeskPlace carga `materials/gold_reflective.mat` con
`base_color`, `metallic` y `roughness`. El renderizador CPU calcula un
acabado dorado utilizando iluminaciones reflejadas y Fresnel aproximados:
no equivale a trazado de rayos ni a un motor PBR físicamente exacto.

El campo opcional `texture` admite imágenes JPEG/PNG cuando se instale Pillow
(`pip install Pillow`) y el material indique `texture_status: "ready"`.
Sin Pillow, sin textura o sin conexión, el material sigue funcionando con
color y reflejos procedurales; no requiere GPU ni dependencias extra.
Cuando se suba la imagen, hay que establecer su estado en `ready`.

El archivo independiente `PYRION/app.py` incluye el mismo renderizador y
cargador de materiales. En el primer arranque necesita conexión para leer la
escena y los materiales que no estén instalados localmente.
