#!/bin/sh
# Nightly mysqldump into the media volume, 14 kept. The volume itself is
# snapshotted by AWS Data Lifecycle Manager, so one snapshot restores both
# the files and the rows that describe them.
set -eu
DIR=/mnt/media/backups
mkdir -p "$DIR"
STAMP=$(date +%Y%m%d)
mysqldump --single-transaction -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" | gzip > "$DIR/livs-$STAMP.sql.gz.part"
mv "$DIR/livs-$STAMP.sql.gz.part" "$DIR/livs-$STAMP.sql.gz"
ls -1t "$DIR"/livs-*.sql.gz | tail -n +15 | xargs -r rm --
