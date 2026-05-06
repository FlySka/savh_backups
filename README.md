# SAVH ERP DB Backup

App standalone para crear backups completos de PostgreSQL y subirlos a Google
Drive. Esta carpeta esta pensada para copiarse fuera del repo principal; no
importa Django ni ningun modulo de `savh_erp`.

## Que hace

- Ejecuta `pg_dump -Fc` sobre la base completa.
- Corre lunes, miercoles y viernes a las 23:00 en `America/Santiago`.
- Sube el archivo a Drive con service account y upload reanudable.
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
   `PGPASSWORD`, `SENTRY_DSN` y `GOOGLE_APPLICATION_CREDENTIALS`.

3. Crea un service account en Google Cloud, descarga el JSON y dejalo en:

```text
secrets/google-service-account.json
```

4. Comparte la carpeta destino de Drive con el email del service account y
   pega el folder id en `config/config.toml`.

## Windows + Docker Desktop

Activa Docker Desktop para iniciar al iniciar sesion. Luego levanta el servicio:

```bash
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
