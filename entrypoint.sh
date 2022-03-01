#!/bin/bash

if [[ -z "${CONF_FILE}" ]] ; then
  echo "Missing or empty CONF_FILE environment variable"
  exit 1
fi

if [[ ! -f "${CONF_FILE}" ]] ; then
  echo "Missing configfile ${CONF_FILE}"
  exit 1
fi

echo "Starting private repo patcher"
cat ${CONF_FILE}
echo ""

exec patcher.py --configfile=${CONF_FILE}
