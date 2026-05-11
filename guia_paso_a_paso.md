# Guía Paso a Paso para Iniciar Lunar Tear

### Lo que ya se hizo (Configuración Inicial)
1. El APK de NieR Re[in]carnation fue reparcheado exitosamente para apuntar a la IP local de tu PC (`192.168.1.36`) en el puerto por defecto de gRPC (`443`) y HTTP (`8080`), sin tocar binarios sensibles.
2. El APK fue compilado, firmado e instalado exitosamente en tu teléfono Xiaomi vía ADB.
3. Se verificó que el puerto 443 está libre en tu máquina Windows.
4. Se arregló el acceso directo de tu escritorio (`NieR Lunar Tear Server.lnk`) para que ejecute el servidor en el puerto correcto.

### Pasos para jugar (Lo que debes hacer cada vez)

1. **Asegura la red local**: 
   Asegúrate de que tu celular Android esté conectado a la red WiFi local (la que le da la IP `192.168.1.36` a tu PC), y no tengas los datos móviles encendidos.

2. **Inicia el servidor**:
   Haz doble clic en tu acceso directo **`NieR Lunar Tear Server.lnk`** que está en el escritorio. 
   *(Al hacer esto, se ejecutará automáticamente el comando correcto: `lunar-tear.exe --host 192.168.1.36 --http-port 8080 --grpc-port 8003`).*
   *Nota: Si Windows Defender salta preguntando si permites el acceso a la red, pulsa "Permitir" tanto en Privado como Público.*

3. **Inicia el Auth Server (Opcional)**:
   Si tenías tu `auth-server` corriendo en el puerto 3000, inícialo como sueles hacerlo. (La rama actual main ignora el auth server, pero tenerlo encendido no afecta en nada).

4. **Abre el juego en tu celular**:
   Inicia la aplicación de NieR que te acabo de instalar.

5. **Conecta**:
   Toca la pantalla para conectar. La app conecta por gRPC al puerto 8003. El servidor debe estar corriendo antes de abrir el juego.

---

### Solución de problemas comunes (2026-04-20)

**Si el juego se traba al 40% o 60%:**

1. Verifica que la estructura de assets sea exactamente así:

   - `assets/revisions/0/list.bin`
   - `assets/revisions/0/info.json`
   - `assets/revisions/0/assetbundle/`
   - `assets/revisions/0/resources/`

2. No debe haber otras carpetas de revisión (solo la 0). Si existe `assets/revisions/revisions/0`, mueve todo su contenido a `assets/revisions/0` y elimina la carpeta redundante.
3. Reinicia el server después de corregir la estructura.
4. El cliente debería avanzar normalmente.

**Resumen del fix aplicado:**
- Se detectó que el server buscaba assets en `assets/revisions/0/` pero la carpeta estaba anidada incorrectamente.
- Se corrigió la estructura y se eliminó la carpeta redundante.
- Tras reiniciar, el juego funciona perfecto.

¡A disfrutar de la preservación!
