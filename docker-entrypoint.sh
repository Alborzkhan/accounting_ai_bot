#!/bin/sh
set -e

mkdir -p /app/data/logs /app/data/voice_temp /app/data/voice_files

if [ ! -e /app/accounting.db ]; then
    ln -s /app/data/accounting.db /app/accounting.db
fi
if [ ! -e /app/logs ]; then
    ln -s /app/data/logs /app/logs
fi
if [ ! -e /app/voice_temp ]; then
    ln -s /app/data/voice_temp /app/voice_temp
fi
if [ ! -e /app/voice_files ]; then
    ln -s /app/data/voice_files /app/voice_files
fi

exec "$@"
