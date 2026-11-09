#!/bin/sh
# Respaldo automático dentro de un contenedor (servicio «backup» de compose.prod.yml).
#
#   respaldo.sh loop          espera la hora BACKUP_TIME (HH:MM, hora del servidor) y respalda cada día
#   respaldo.sh now           un respaldo inmediato
#   respaldo.sh restore-test  restaura el último respaldo en una base temporal y verifica sus tablas
#
# Cada respaldo queda en /backups/<AAAA-MM-DD_HHMMSS>/: trazo.dump (pg_dump -Fc), ortofotos.tar.gz y SHA256SUMS.
# Se conservan BACKUP_RETENTION_DAYS días (14 por defecto). Las imágenes Docker y el código se reconstruyen desde
# git; el respaldo manual completo (con imágenes) sigue siendo `make backup`.
set -eu
umask 077

DEST_ROOT=/backups
export PGHOST="${DB_HOST:-db}" PGUSER="$POSTGRES_USER" PGPASSWORD="$POSTGRES_PASSWORD"
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') respaldo: $*"; }

backup_now() {
	stamp=$(date +%Y-%m-%d_%H%M%S)
	dir="$DEST_ROOT/$stamp"
	mkdir -p "$dir.tmp"
	pg_dump -Fc -d "$POSTGRES_DB" -f "$dir.tmp/trazo.dump"
	pg_restore --list "$dir.tmp/trazo.dump" | grep -q "TABLE DATA public project " || { log "ERROR: el dump no contiene la tabla project"; exit 1; }
	tar -C /data/ortho -czf "$dir.tmp/ortofotos.tar.gz" .
	(cd "$dir.tmp" && sha256sum trazo.dump ortofotos.tar.gz > SHA256SUMS)
	mv "$dir.tmp" "$dir"
	log "listo $dir ($(du -sh "$dir" | cut -f1))"
	find "$DEST_ROOT" -mindepth 1 -maxdepth 1 -type d -name '20*' -mtime "+${BACKUP_RETENTION_DAYS:-14}" -print -exec rm -rf {} + \
		| sed 's/^/  eliminado por retención: /'
}

restore_test() {
	last=""
	for d in "$DEST_ROOT"/20*; do
		case "$d" in *.tmp) ;; *) [ -d "$d" ] && last="$d" ;; esac
	done
	[ -n "$last" ] || { log "no hay respaldos en $DEST_ROOT"; exit 1; }
	(cd "$last" && sha256sum -c SHA256SUMS >/dev/null) || { log "ERROR: sumas SHA-256 no coinciden en $last"; exit 1; }
	db=trazo_restore_test
	dropdb --if-exists "$db"
	createdb "$db"
	pg_restore --no-owner --exit-on-error -d "$db" "$last/trazo.dump"
	projects=$(psql -tA -d "$db" -c "SELECT count(*) FROM project")
	versions=$(psql -tA -d "$db" -c "SELECT count(*) FROM project_version")
	users=$(psql -tA -d "$db" -c "SELECT count(*) FROM app_user")
	tar -tzf "$last/ortofotos.tar.gz" >/dev/null
	dropdb "$db"
	log "restauración verificada desde $last: $projects proyectos, $versions versiones, $users usuarios; ortofotos legibles."
}

case "${1:-loop}" in
	now) backup_now ;;
	restore-test) restore_test ;;
	loop)
		log "programado a las ${BACKUP_TIME:-03:30} (retención ${BACKUP_RETENTION_DAYS:-14} días)"
		while :; do
			target=$(date -d "today ${BACKUP_TIME:-03:30}" +%s)
			now=$(date +%s)
			[ "$target" -gt "$now" ] || target=$(date -d "tomorrow ${BACKUP_TIME:-03:30}" +%s)
			sleep $((target - now))
			backup_now || log "ERROR: el respaldo falló"
		done ;;
	*) echo "uso: respaldo.sh loop|now|restore-test" >&2; exit 2 ;;
esac
