# numa

## Presupuesto mensual

Desde un Plan, abrí **Budget** para asignar el dinero que ya tenés, consultar
categorías agrupadas y revisar **Assigned / Activity / Available**. La pantalla
tiene navegación entre meses, filtros de metas pendientes/excesos/disponibles y
un detalle de categoría para fijar la asignación total, mover dinero y editar o
financiar metas. En celulares, el detalle se abre como una hoja modal accesible.

El dinero sin asignar y la sobreasignación continúan entre meses. Las asignaciones
futuras reservan dinero actual sin contar ingresos futuros. Los sobrantes por
categoría se acumulan; los excesos se muestran negativos y el exceso de efectivo
reduce el dinero por asignar del mes siguiente una sola vez.

Las tarjetas en la moneda del Plan tienen una categoría protegida de pago:
las compras financiadas reservan dinero automáticamente y los pagos descuentan
esa reserva, sin duplicar gastos. Podés asignar dinero directamente para deuda
anterior. Un saldo a favor se comporta como efectivo hasta agotarse; sólo la
parte que genera deuda necesita reserva. Un ingreso que sólo reduce deuda no
crea efectivo nuevo. Sobrepagos y adelantos en la misma moneda muestran sus
efectos sobre el dinero disponible. Las reservas superiores a la deuda pueden
moverse manualmente a otra categoría o a Ready to Assign.

Las acciones guardan un comprobante inmutable y ajustes de asignación; los
reintentos con el mismo UUID no repiten el movimiento. Mover dinero de presupuesto
no cambia cuentas ni transacciones. La pantalla refuerza los resultados que
devuelve el servidor; no calcula saldos financieros con números JavaScript.

Las monedas distintas siguen separadas y sin conversión automática. Los ajustes
de conciliación conservan su política existente: cambian el saldo de la cuenta,
quedan fuera de la financiación del presupuesto y se muestran por separado.
Las metas disponibles son aporte mensual, saldo objetivo y ahorro para un mes;
no se afirma equivalencia con todas las variantes de recurrencia de YNAB.

La migración aditiva actual es `010_ynab_budget`. Aplicala antes de ejecutar el
código actualizado. Conserva el historial y agrega categorías de pago para las
tarjetas existentes en la moneda del Plan. No reviertas una base con nuevos
comprobantes o asignaciones de pago: el downgrade rechaza perder ese historial.

Referencia de comportamiento: [cambio y verificación](openspec/changes/005a-ynab-budget-parity/verification.md).

## Actividad, registro y correcciones

**All activity** incluye un registro de transacciones con búsqueda, filtro por
cuenta y tipo, y edición en línea. Cada fila muestra fecha, cuenta, payee,
categoría, memo y outflow/inflow; la corrección conserva el asiento original y
su historial. **+ Add transaction** abre una fila al inicio del registro en
escritorio. En celular abre una hoja con el importe en primer plano. También
podés iniciar un gasto desde **Budget** o desde el detalle de una categoría.
La cuenta o categoría de origen se preselecciona. Al elegir un comercio
conocido, el formulario propone su última categoría y ofrece hasta cinco
alternativas de su historial en el mismo Plan y tipo de movimiento.
**Save and add another** abre un nuevo borrador y conserva la cuenta elegida.
La fecha inicial usa la hora local del dispositivo.

Las cuentas del sidebar y las tarjetas de **Accounts** abren el registro
filtrado por cuenta. Los saldos y montos se muestran con formato local
(`Bs 2.625,94`) sin convertir los strings exactos que usa el servidor para
calcular y validar.

## Gmail (fase 007)

La integración recopila correos por Plan con acceso de solo lectura. Conserva
el MIME original y su decodificación; los errores quedan para revisión. Los
parsers financieros y la creación de transacciones corresponden a fases posteriores.

Para habilitarla, configurá en `api/.env` las variables de `api/.env.example`:
`GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REDIRECT_URI`, `GMAIL_TOKEN_KEY`
y `GMAIL_ALLOWED_SENDERS` (array JSON no vacío de direcciones exactas).
Usá un cliente OAuth de tipo aplicación web, habilitá Gmail API y registrá
exactamente la URL de retorno. En desarrollo, con Vite en el puerto 5173:
`http://localhost:5173/gmail/oauth/callback`.

Generá una clave Fernet una sola vez y guardala como `GMAIL_TOKEN_KEY` en el
servidor; API y worker deben usar la misma clave. No la regeneres al reiniciar.
Podés generarla desde `api` con
`.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`.
La contraseña de Gmail nunca se solicita. La configuración y autorización
siguen el [flujo oficial de Google](https://developers.google.com/identity/protocols/oauth2/web-server).

### Alcance de la recopilación (007a)

El permiso readonly de Google sigue siendo para toda la casilla; **el filtro es
local**, no una restricción del permiso OAuth ni una verificación de autenticidad
del remitente. Numa consulta solo cabeceras From y etiquetas de los candidatos
antes de descargar MIME. Descarta otros remitentes, cabeceras ambiguas, spam y
papelera sin guardar sus cuerpos. Puede incluir avisos no financieros de las
direcciones permitidas; aún no crea transacciones.

Configuración acordada para esta instalación, en `api/.env`:

```dotenv
GMAIL_ALLOWED_SENDERS=["do-not-reply@ses.binance.com","notificaciones@bg.com.bo"]
```

La lista vacía bloquea nuevas autorizaciones, nunca habilita toda la casilla.
Cada conexión guarda su propia lista; cambiar defaults no altera conexiones
existentes. Usá **Reconnect** para adoptar una lista nueva y resincronizar sin
duplicados. Conexiones anteriores sin filtro requieren reconectar. No se eliminan
correos ya almacenados al cambiar el filtro. En modo Testing de Google los refresh
tokens para Gmail caducan a los 7 días, por lo que habrá que reconectar.

## Entorno local de desarrollo aislado

PostgreSQL **39747**, API **39748**, web **5173**. No utiliza la DB de tests de
29746. Antes de iniciar, comprobá puertos con `lsof -nP -iTCP:39747 -iTCP:39748
-iTCP:5173 -sTCP:LISTEN`; si alguno está ocupado, no detengas servicios de otros
proyectos. Elegí otro puerto alto para DB/API, y actualizá el proxy si cambia API.
No cambies silenciosamente el puerto web: exige modificar el callback en Google.

```sh
cp .env.numa-dev.example .env.numa-dev
# Elegí una contraseña local única en .env.numa-dev; no uses el placeholder.
chmod 600 .env.numa-dev
docker compose --env-file .env.numa-dev -f docker-compose.numa-dev.yml up -d --wait
```

Configurá `DATABASE_URL=postgresql+psycopg://numa_dev:<password>@127.0.0.1:39747/numa_dev`
en `api/.env`, codificando caracteres especiales del password para URL; preservá
OAuth/Fernet y restringí el archivo con `chmod 600 api/.env`. No uses una base
de desarrollo con `TEST_DATABASE_URL`: las pruebas truncan tablas.
`NUMA_DEV_POSTGRES_PORT` permite cambiar el puerto de Compose.

Desde `api`, instalá las dependencias, aplicá las migraciones y ejecutá API y
worker en terminales separadas con el entorno configurado:

```sh
uv pip install --python .venv/bin/python -e '.[test]'
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 39748 --no-access-log
```

```sh
.venv/bin/numa-worker
```

Desde `web`, ejecutá `npm install` y `npm run dev -- --port 5173 --strictPort`.
El target del proxy por defecto es `http://127.0.0.1:39748`. Para cambiarlo,
usá `NUMA_API_TARGET=http://127.0.0.1:<puerto> npm run dev` (no es un secreto).
Abrí `http://localhost:5173`, elegí un Plan y entrá en **Gmail connections**.
El proxy de Vite distingue las navegaciones HTML de las peticiones a `/plans`
y envía `/gmail/oauth/callback` a la API. En despliegues, mantené web y API bajo
el mismo origen y evitá registrar los parámetros del callback en el proxy:
contienen códigos OAuth temporales.

Verificá `http://127.0.0.1:39748/health/ready` y
`http://localhost:5173/health/ready` antes de conectar Gmail. El inicio no autoriza
Google automáticamente. Para detener, Ctrl+C en API/worker/web y, desde la raíz:

```sh
docker compose --env-file .env.numa-dev -f docker-compose.numa-dev.yml stop
# También se puede hacer down sin -v: conserva el volumen de desarrollo.
```

No uses `down -v` como parte del arranque o parada: destruiría los datos locales.

La sincronización inicial recorre páginas de 25 elementos. Luego consulta
History cada `GMAIL_POLL_SECONDS` (300 por defecto); un 404 del cursor programa
una resincronización completa. Los checkpoints y trabajos sobreviven reinicios;
los reintentos no duplican correos. Una autorización revocada requiere reconectar.
La reconexión debe usar la misma cuenta Google; para otra cuenta, creá otra conexión.
Sin configuración o ante una caída de Gmail, las operaciones financieras siguen
disponibles. Véase la [sincronización de Gmail](https://developers.google.com/workspace/gmail/api/guides/sync).

La pantalla muestra conexión, progreso y cantidades. La evidencia decodificada
se consulta con `GET /plans/{plan_id}/gmail/{source_id}/messages`, paginada por
`after` y `limit` (máximo 100). El endpoint entrega texto y metadatos; cualquier
consumidor debe tratar el HTML del correo como contenido no confiable.
Desconectar elimina la credencial local y detiene la ingesta, conservando los
correos ya recopilados. El permiso también puede revocarse desde Google.

Las pruebas de Gmail simulan Google mediante un transporte HTTP controlado y
usan PostgreSQL real para OAuth, migraciones, checkpoints, concurrencia y
evidencia. No sustituyen una prueba con una cuenta Google autorizada.

## Binance Card: revisión sin movimientos (fase 008)

En **Gmail → Binance Card review** se muestran compras candidatas del formato
USD validado y avisos que necesitan inspección. Los importes se conservan como
texto decimal exacto, con comercio, hora del asunto en UTC y referencia al correo
original. La fecha de notificación se conserva por separado.

**Nada de esta fase modifica balances:** no hay aprobación, asignación de cuenta,
liquidación, cotización ni registro de movimientos. USD no se convierte en USDT,
aunque exista una cuenta USDT. Las operaciones fallidas no son compras.

La migración `008_binance_review` agrega una tabla de evidencia de revisión;
ejecutá `.venv/bin/alembic upgrade head` desde `api` antes de reiniciar API/worker.
El worker procesa el historial ya guardado en lotes de 100 mensajes y la nueva
ingesta registra el resultado en la misma transacción que el correo. Reintentos
y trabajadores concurrentes no repiten el registro de un mismo mensaje.
Desconectar Gmail no borra los candidatos ni requiere volver a descargar correos.

El endpoint de solo lectura es
`GET /plans/{plan_id}/gmail/binance-card-reviews?after=0&limit=25` (máximo 100).
Incluye contadores globales del Plan y `next_after`, pero no devuelve HTML crudo,
cuerpos de correo ni credenciales. La UI ofrece **Load more notices**.

La identidad usada es el mensaje de Gmail dentro de su conexión. `Message-ID`
se conserva como evidencia alternativa, no como autorización para fusionar
mensajes de distintas cuentas. El remitente no prueba autenticidad. Reembolsos,
reversas, otras monedas, variantes de plantilla y liquidación siguen pendientes
de muestras reales y trabajo autorizado; los casos no compatibles quedan
señalados sin inventar importes.

## Base de reglas y reejecuciones (fase 009, parcial)

El módulo `api/app/watchers` define etapas ordenadas, reglas tipadas de
clasificación y evidencia de reglas aplicadas/omitidas. Los conflictos se señalan
sin elegir un resultado silenciosamente; se respetan las pistas protegidas
manualmente. Las reglas no pueden asignar importes, moneda, cuentas, glosa,
tiempos de evento ni liquidación.

La migración aditiva `009_watcher_runs` conserva resultados y configuración por
versión, referencias al correo original y linaje de reejecución. Los reintentos
de un mismo contrato no crean duplicados; una reejecución explícita conserva el
resultado anterior. Los errores no guardan textos de excepción con datos privados.

**Todavía no está conectado al procesamiento automático de correos ni expuesto
como editor de reglas/API de reejecución.** Sus contratos bancarios no equivalen
a parsers MIME nuevos ya validados. La IA y la etapa de registro financiero están
desactivadas. Las decisiones humanas de los avisos existentes siguen pendientes.

## PostgreSQL local para tests

Configura una vez `cp .env.numa-test.example .env.numa-test` y usa una contraseña local.

```sh
docker compose -f docker-compose.numa-test.yml up -d
docker compose -f docker-compose.numa-test.yml ps
docker compose -f docker-compose.numa-test.yml exec -T postgres sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Desde `api`, ejecutá las pruebas con el entorno virtual del proyecto:

Preferí esta ejecución aislada para validar toda la suite sin tocar los datos
existentes de `numa_test`:

```sh
.venv/bin/python scripts/run_postgres_tests.py -q
# Solo Gmail:
.venv/bin/python scripts/run_postgres_tests.py -q tests/test_gmail.py
```

El script usa la configuración local de `.env.numa-test` y el servicio en
`127.0.0.1:29746`. Crea una base temporal nueva, ejecuta las pruebas y elimina
solo esa base al terminar; no usa `DATABASE_URL` ni una `TEST_DATABASE_URL`
preexistente. Las pruebas de migraciones también crean y eliminan sus propias
bases temporales. Requiere PostgreSQL 18 y permisos para crear bases, como el
usuario local del contenedor.

La ejecución directa siguiente requiere una `TEST_DATABASE_URL` que apunte a
una base desechable vacía: las pruebas migran el esquema y truncan tablas.

```sh
set -a && source .env && set +a
.venv/bin/pytest -q
```

Para restablecer únicamente el esquema de la base local `numa_test`, usa las
variables ya presentes dentro del contenedor (SCRAM no expone la contraseña):

```sh
docker compose -f ../docker-compose.numa-test.yml exec -T postgres sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"'
```

```sh
docker compose -f docker-compose.numa-test.yml stop
docker compose -f docker-compose.numa-test.yml down
# Opcional: destruye todos los datos de esta DB de tests.
docker compose -f docker-compose.numa-test.yml down -v
```
