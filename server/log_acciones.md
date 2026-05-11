# log_acciones.md

## 2026-04-20 - Fix 40%/60% stuck (NieR Re[in]carnation local server)

1. Eliminé todas las carpetas de revisión excepto la 0 en assets/revisions/ para cumplir con la guía oficial y evitar conflictos de assets.
2. Detecté que la carpeta 0 estaba dentro de assets/revisions/revisions/0 en vez de directamente en assets/revisions/0.
3. Moví la carpeta 0 a la ubicación correcta: assets/revisions/0/.
4. Verifiqué que assets/revisions/0/ contiene list.bin, info.json, assetbundle/ y resources/.
5. Eliminé la carpeta redundante assets/revisions/revisions/.
6. Reinicié el server y confirmé que el cliente avanza correctamente.

Resultado: El cliente ya no se traba al 40% ni al 60%. Estructura de assets corregida y funcional.
