# PYRION 3D Engine 0.1.0

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
