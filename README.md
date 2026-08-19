# numa

## PostgreSQL local para tests

Configura una vez `cp .env.numa-test.example .env.numa-test` y usa una contraseña local.

```sh
docker compose -f docker-compose.numa-test.yml up -d
docker compose -f docker-compose.numa-test.yml ps
docker compose -f docker-compose.numa-test.yml exec -T postgres sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Desde `api`, carga la URL sin imprimirla y ejecuta los tests:

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
