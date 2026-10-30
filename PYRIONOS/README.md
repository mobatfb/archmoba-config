# PYRION OS — imagenes ISO

Esta carpeta contiene las publicaciones de PYRION OS.

## Version v0.6

- Archivo previsto: `PYRION_OS_v0.6.iso`
- Tamano exacto: `92080128` bytes (87.81 MiB)
- SHA-256: `582f4eb432eb2d4f70fdb67a0d9396b3935e4b17c4327e1417722df90e66af0a`
- Arranque: cubo animado hasta que se preparen los servicios, 3 segundos adicionales de cubo, cierre de boot.py, 1 segundo de pantalla negra e inicio del escritorio.

**Estado de publicacion:** la carpeta y los datos de verificacion estan creados. La imagen ISO binaria aun no esta incorporada al historial Git. No confundir este registro con la subida de la ISO.

Para incorporar el archivo, copiarlo como `PYRIONOS/PYRION_OS_v0.6.iso` dentro de una copia local del repositorio y utilizar Git (no la interfaz de subida web):

```bash
git add PYRIONOS/PYRION_OS_v0.6.iso
git commit -m "PYRIONOS: publish PYRION OS v0.6 ISO"
git push origin main
```

Una vez publicada, verificar que el SHA-256 de la ISO coincida con el indicado arriba.
