# Verificación de 007-gmail

## Resumen

Verificación local del cambio existente, sin autorizar una cuenta Google real
ni archivar el cambio. No se encontraron bloqueos en los requisitos del delta.

| Dimensión | Resultado |
| --- | --- |
| Completitud | 4/4 tareas marcadas completas; 2/2 requisitos con implementación |
| Corrección | Ambos escenarios del delta cubiertos por pruebas aprobadas |
| Coherencia | OAuth servidor, readonly, cifrado, polling y evidencia MIME acordes al diseño |

## Evidencia

- **Sincronización recuperable:** `api/app/gmail/client.py:13` define scope readonly,
  PKCE y cifrado Fernet ligado al propietario. `api/app/gmail/service.py:263` persiste
  cursores y trabajos, serializa cambios por conexión y programa full resync ante
  un 404 de History. `api/tests/test_gmail.py` cubre estado OAuth ligado al
  navegador, expiración/replay, cifrado, full sync y History paginados, 404,
  reintentos, rollback de página, revocación, reconexión y concurrencia.
- **Decodificación recursiva:** `api/app/gmail/mime.py:8` recorre MIME anidado,
  decodifica transferencias y RFC2047, usa el charset MIME y conserva incidencias
  y procedencia. Las pruebas cubren HTML quoted-printable con charset interno
  contradictorio, base64 y charset desconocido. La evidencia queda en
  `gmail_messages`; su API paginada permite revisar texto y metadatos, sin
  interpretar el correo como una transacción ni verificar firmas por su cuenta.
- **Aislamiento y conservación:** las pruebas verifican aislamiento por Plan,
  desconexión sin pérdida de correos, trabajos antiguos inertes, ausencia de
  mutaciones financieras y trigger de inmutabilidad de evidencia.

## Comprobaciones ejecutadas

- Desde `api`: `.venv/bin/python scripts/run_postgres_tests.py -q`:
  **181 aprobadas, 0 omitidas**. Incluye las 14 pruebas de Gmail y migraciones
  sobre PostgreSQL 18 real. Google está simulado mediante `httpx.MockTransport`.
- Desde `web`: `npm test`: **12 aprobadas** en 2 archivos.
- Desde `web`: `npm run build`: TypeScript y build Vite aprobados.
- Ejecución aislada adicional de `tests/test_gmail.py`: **14 aprobadas**.
- `openspec validate 007-gmail --strict` y `git diff --check`: aprobados.

La suite usó una base nueva desechable; se eliminó al terminar sin restablecer
el esquema de la base local existente.

## Observaciones

### Críticas

Ninguna encontrada en esta revisión.

### Advertencias

- Falta la prueba con una cuenta Google autorizada. Los mocks no acreditan la
  configuración real del cliente OAuth, el consentimiento ni la ingesta real.
  Antes de dar por validado ese entorno, completar la comprobación manual de
  abajo. No se solicitó, mostró ni modificó una credencial Google.
- La suite emite advertencias de dependencias: deprecación de la integración
  Starlette/httpx y dos avisos Pydantic de metadata `alias` en pruebas ajenas a
  Gmail. No causaron fallos; revisar su compatibilidad en una tarea separada.

### Sugerencias

- `web/src/GmailScreen.tsx:68` muestra cantidades de correos e incidencias, pero no
  inspecciona el endpoint de mensajes. Añadir una vista de evidencia que muestre
  texto y metadatos de forma segura, sin ejecutar HTML del correo, mejoraría la
  revisión humana. La revisión vía API ya está disponible y probada.

## Comprobación manual pendiente con Google

1. Configurar OAuth y la clave persistente siguiendo el README, sin compartir
   secretos en el chat ni registrarlos en logs. Usar una cuenta de prueba y un
   Plan separado: el full sync recopila toda la casilla, incluido spam/papelera.
2. Levantar API, worker y web; conectar Gmail y confirmar que Google solicita
   solo lectura. Verificar retorno al Plan y estado conectado.
3. Esperar el full sync; consultar un correo por el endpoint de mensajes y
   comparar asunto/texto/charset con la muestra esperada. Confirmar que no se
   crean transacciones ni movimientos financieros.
4. Recibir un correo nuevo y esperar un polling; comprobar una sola ingesta.
   Reiniciar el worker y verificar continuidad sin duplicados.
5. Desconectar: verificar que se detiene la ingesta y se conserva la evidencia.
   Reconectar la misma casilla; revocar el permiso desde Google y verificar
   que se solicita reconexión sin bloquear las operaciones financieras.

## Evaluación final

Validación automatizada satisfactoria. No se archivó ni se creó un commit.
La validación del entorno Google real sigue pendiente.
