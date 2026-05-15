# SAVH ERP DB Backup

App standalone para crear backups completos de PostgreSQL y subirlos a Google
Drive. Esta carpeta esta pensada para copiarse fuera del repo principal; no
importa Django ni ningun modulo de `savh_erp`.

## Que hace

- Ejecuta `pg_dump -Fc` sobre la base completa.
- Corre lunes, miercoles y viernes a las 23:00 en `America/Santiago`.
- Sube el archivo a Drive con service account o con OAuth de usuario, segun el provider configurado.
- Mantiene retencion local de 14 dias y remota de 90 dias.
- Escribe logs en stdout y en `data/logs/app.log.jsonl`.
- Escribe auditoria append-only en `data/manifests/backups.jsonl`.
- Reporta errores y check-ins a Sentry si configuras `SENTRY_DSN`.

## Estructura interna

El codigo usa `src/` layout y separa responsabilidades por capa:

```text
src/savh_backup/
├── cli.py                    # comandos publicos de la app
├── __main__.py               # permite python -m savh_backup
├── application/              # flujo principal, scheduler, retencion
├── bootstrap/                # armado explicito de dependencias
├── core/                     # helpers puros sin I/O externo
├── infrastructure/           # Postgres, storage, logs, Sentry, estado local
├── scheduling/               # calculos de cron/catch-up
└── settings/                 # carga y validacion de configuracion
```

## Preparacion

1. Copia los ejemplos:

```bash
cp .env.example .env
cp config/config.example.toml config/config.toml
mkdir -p data secrets
```

2. Edita `.env` con `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`,
   `PGPASSWORD`, `PG_MAJOR`, `SENTRY_DSN` y `GOOGLE_APPLICATION_CREDENTIALS`.

   `PG_MAJOR` debe coincidir con el major del servidor PostgreSQL. Por
   ejemplo, para PostgreSQL 18 usa `PG_MAJOR=18`.

3. Crea un service account en Google Cloud, descarga el JSON y dejalo en:

```text
secrets/google-service-account.json
```

4. Comparte la carpeta destino de Drive con el email del service account y
   pega el folder id en `config/config.toml`.

## Google Drive personal con OAuth

Si quieres subir a `Mi unidad` de un Google Drive personal, usa
`provider = "google_drive_oauth"` en vez de service account.

Pasos recomendados:

1. En Google Cloud Console, crea un OAuth Client ID de tipo `Desktop app`.
2. Descarga el JSON y guardalo en:

```text
secrets/google-oauth-client.json
```

3. Copia el ejemplo personal:

```bash
cp config/config.personal-drive.example.toml config/config.personal-drive.toml
```

4. En `.env`, apunta a ese config:

```bash
SAVH_BACKUP_CONFIG=config/config.personal-drive.toml
```

5. Ajusta `storage.drive_folder_id` con la carpeta de tu Drive personal.

6. Ejecuta el login una sola vez:

```bash
poetry run savh-backup google-drive-login
```

Para no abrir el navegador automaticamente:

```bash
poetry run savh-backup --no-browser google-drive-login
```

7. Luego valida y ejecuta el backup:

```bash
poetry run savh-backup validate-config
poetry run savh-backup run-once
```

El token OAuth se guarda por defecto en `secrets/google-oauth-token.json`.
Si lo eliminas o revocas en Google, vuelve a correr `google-drive-login`.

## Uso local con Poetry

Para probar el proyecto sin Docker hay dos niveles distintos:

- Pruebas unitarias: solo necesitan Poetry.
- Smoke test real (`run-once`, `validate-config`, `scheduler`): necesitan
  ademas `pg_dump` y `pg_restore` instalados en tu host, con el mismo major
  que el servidor PostgreSQL.

Pasos recomendados:

1. Instala dependencias Python:

```bash
poetry install
```

2. Prepara configuracion local:

```bash
cp .env.example .env
cp config/config.local.example.toml config/config.local.toml
```

3. Edita `.env` y deja activo:

```bash
SAVH_BACKUP_CONFIG=config/config.local.toml
PGHOST=127.0.0.1
PGPORT=5432
PGDATABASE=savh_erp
PGUSER=savh_user
PGPASSWORD=tu_password
PG_MAJOR=18
```

4. Instala los binarios de PostgreSQL en tu host. En Ubuntu/Debian, por
   ejemplo:

```bash
sudo apt-get install postgresql-client-18
```

5. Corre la suite local:

```bash
poetry run pytest
poetry run savh-backup validate-config
poetry run savh-backup google-drive-login
poetry run savh-backup run-once
poetry run savh-backup cleanup
```

El archivo `config/config.local.example.toml` usa storage `filesystem` y rutas
relativas dentro del repo, asi que no necesita Google Drive ni escribir en
`/data`. Ademas, la CLI ahora carga `.env` automaticamente, por lo que no hace
falta exportar variables a mano antes de usar `poetry run`.

### Checklist exacto para `run-once` local

Usa esta secuencia cuando quieras probar el backup real contra tu PostgreSQL
local, sin Docker:

1. Verifica que el cliente PostgreSQL local coincida con tu servidor:

```bash
pg_dump --version
pg_restore --version
```

2. Verifica conectividad y credenciales con los valores de `.env`:

```bash
PGPASSWORD="$PGPASSWORD" psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -c "select version();"
```

3. Valida configuracion de la app:

```bash
poetry run savh-backup validate-config
```

4. Ejecuta un backup manual:

```bash
poetry run savh-backup run-once
```

5. Revisa artefactos esperados:

```bash
ls -lah data/local/backups
ls -lah data/local/remote
tail -n 2 data/local/manifests/backups.jsonl
cat data/local/state/state.json
```

6. Verifica que el archivo sea legible por PostgreSQL:

```bash
pg_restore --list data/local/backups/savh_erp_*.pgcustom
```

7. Limpia la retencion manual si quieres probar ese paso por separado:

```bash
poetry run savh-backup cleanup
```

Si `run-once` falla, el error mas comun en local es uno de estos:

- `server version mismatch`: instala `postgresql-client-<major>` del mismo major del servidor.
- `password authentication failed`: revisa `PGHOST`, `PGUSER`, `PGPASSWORD` y permisos del usuario.
- `No such file or directory: pg_dump`: instala `pg_dump` y `pg_restore` en tu host.
- error de Google Drive: para pruebas locales usa `config/config.local.toml` con `provider = "filesystem"`.

## Windows + Docker Desktop

Activa Docker Desktop para iniciar al iniciar sesion. Luego levanta el servicio:

```bash
docker compose up -d
```

Si cambias `PG_MAJOR`, reconstruye la imagen antes de volver a levantar el
servicio:

```bash
docker compose build --no-cache backup
docker compose up -d
```

El contenedor usa `restart: unless-stopped`, asi que Docker lo reinicia si cae
y lo levanta de nuevo cuando Docker Desktop arranca.

## Comandos utiles

```bash
docker compose logs -f backup
docker compose run --rm backup validate-config
docker compose run --rm backup run-once
docker compose run --rm backup cleanup
```

Para usar el backend local de pruebas, cambia en `config/config.toml`:

```toml
[storage]
provider = "filesystem"
filesystem_dir = "/data/remote"
```

## Restore rapido

El archivo generado es un archivo custom de PostgreSQL. Para inspeccionarlo:

```bash
pg_restore --list data/backups/savh_erp_YYYYmmdd_HHMMSS_America-Santiago.pgcustom
```

Para restaurarlo, crea la base destino y usa `pg_restore` con el usuario que
tenga permisos suficientes.

## Nota de seguridad

La v1 no cifra el backup antes de subirlo. La configuracion incluye
`[encryption] enabled = false` y el codigo tiene el punto de extension para
agregar cifrado luego. Por ahora la seguridad depende del acceso al service
account, permisos de la carpeta y cifrado de Google Drive.
