# Versiones y actualizaciones

- Cada cambio en una aplicación debe incrementar la versión de su `config.json` correspondiente y mantenerla igual a `APP_VERSION` en su código.
- Actualizar la fecha y hora de actualización cuando la aplicación declare esos campos. Usar America/Guayaquil.
- Antes de publicar, ajustar `release_commit` al commit real que contiene el código de esa versión; no inventar hashes ni publicar una versión con el hash de código anterior.

# Origen global

- El interruptor local/repositorio de AMDEV controla también las actualizaciones manuales y automáticas, catálogos, herramientas y recursos de sus aplicaciones. Propagar el modo a los procesos hijos.
- En modo local, consultar el código y los JSON del disco; no desactivar el botón de actualizar ni recurrir a GitHub cuando falte un recurso.
- Cada clic en refresh de PYRION debe recargar el código y reiniciar completamente el estado del motor en la ventana existente, incluso sin cambio de versión. Restablecer cámara, escena, animación, controles y cachés. La ventana es el contenedor padre; no cerrar ni abrir otro proceso. Cancelar callbacks del motor anterior y evitar bucles duplicados. Si falla el reset, conservar la sesión anterior.
