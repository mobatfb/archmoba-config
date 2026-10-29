# PYRION OS - Historial de versiones

Cada carpeta `vX.Y.Z/` contiene una copia INMUTABLE de:
- `app.py`: codigo fuente exacto de esa version, recuperado del historial de Git.
- `config.json`: configuracion publicada con esa version.

Versiones recuperadas: v0.1.0, v0.1.1, v0.1.2, v0.1.3, v0.1.4, v0.1.5, v0.2.0, v0.3.0.

## Publicaciones futuras

El flujo `.github/workflows/pyrion-release.yml` crea automaticamente un
directorio cuando se publica una version nueva mediante `PYRION/config.json`.
Comprueba que `APP_VERSION` del codigo en el commit `release_commit`
coincida con la version publicada.

IMPORTANTE:
1. Actualizar `PYRION/app.py` con una version nueva.
2. Publicar ese codigo en un commit de GitHub.
3. Actualizar `PYRION/config.json` con `version` y el SHA exacto
   de ese commit en `release_commit`.
4. El flujo crea `PYRION/release/vVERSION/app.py` y `config.json`
   sin sobrescribir archivos ya existentes.

Las imagenes de `PYRION/assets/` se comparten entre versiones y no se
duplican en este historial. Los archivos originales tambien siguen
accesibles a traves del historial de Git.

La automatizacion requiere que GitHub Actions este habilitado en el
repositorio y tenga permiso de escritura en contenidos para GITHUB_TOKEN.
Si la ejecucion falla, revisar la pestana Actions y sus permisos.
