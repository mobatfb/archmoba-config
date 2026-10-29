# monumentalShock

Santuario monumental de cristales para PYRION 3D. La torre central es la más alta;
dos hileras de cristales giratorios forman escalones que ascienden desde la
izquierda hasta su cima y descienden a la derecha. Otros cristales giran entre
los monumentos laterales.

- `scene.json`: escena y cámara de entrada.
- `models/`: mallas de monumento, pedestal y cristal de seis caras.
- `materials/`: piedra azul, obsidiana, oro y cristales cian, violeta, rosa y hielo.
- `project.json`: metadatos del proyecto.
- `build_scene.py`: regenera los archivos de la escena con Python estándar.

La escena está seleccionada en `engine3d/scene_selected.json`. Desde PYRION en
modo local, pulsa `↻` para cargar la versión nueva y entrar en este proyecto.
El cambio de proyecto coloca la cámara frente al santuario.

## Material de las torres (PYRION 0.4.23, motor 0.4.1)

Las siete torres usan `materials/tower_stone.mat` y la textura generada
`textures/limestone_ashlar.png`: piedra de cantera con juntas, poros y desgaste.
El material es rugoso y casi no metálico. La escena activa IMG por defecto.

Con Pillow, el motor proyecta la imagen sobre las caras de cada torre y conserva
en caché las superficies mientras la cámara, las luces y la orientación no cambien.
Sin Pillow, Tk permite la carga de PNG y conserva el muestreo de color por faceta.
El botón MAT/IMG sigue disponible para comparar ambos materiales.

La textura original y su prompt se documentan en `textures/PROVENANCE.md`.

## Bosque de fondo (PYRION 0.4.24)

`textures/forest_background.png` es una imagen panorámica de bosque con niebla.
Se ajusta al tamaño de la ventana sin deformarse y se dibuja detrás de todos
los objetos 3D. El fondo redimensionado se conserva en caché y se renueva
al cambiar el tamaño de la ventana o al cargar una nueva imagen mediante `↻`.

## Integración visual (PYRION 0.4.25, motor 0.4.2)

- Terreno irregular de piedra y musgo que continúa fuera del encuadre, sin el
  borde flotante de la antigua plataforma azul.
- Texturas con corrección de perspectiva sobre suelo y monumentos.
- Escalones de piedra y remates de metal envejecido, con acabados rugosos.
- Foco menos intenso y cristales con reflejos moderados para conservar facetas.
- Niebla azul suave por distancia y sombras de contacto difuminadas bajo las torres.

Las sombras son una aproximación de contacto sobre el terreno, no sombras
proyectadas completas. Tanto las superficies estáticas como las sombras quedan
en caché hasta que cambia la cámara, el zoom o la escena.

## Reset completo con refresh (PYRION 0.4.26, motor 0.4.3)

Cada clic en `↻` consulta el origen seleccionado y ejecuta de nuevo el arranque
del motor, incluso cuando no cambia la versión. Se recarga el código y se
restablecen escena, cámara, controles, animación, métricas y cachés.

La ventana Tk y el Canvas actúan como contenedor padre y permanecen abiertos.
Los callbacks del motor anterior se cancelan y una nueva generación inicia un
único bucle de animación. Si falla la preparación o el arranque, se recupera la
sesión anterior. Este comportamiento sustituye a la antigua recarga que
conservaba la posición de la cámara.

En modo local se recompilan `mesh.py`, `renderer.py` y `app.py` en un paquete
aislado por generación, sin reutilizar el caché de imports ni `.pyc`. Así se
aplican también cambios en los módulos de `engine3d` sin cambiar de versión.
