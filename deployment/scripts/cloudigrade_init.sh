#!/bin/sh

#
# Cloudigrade-api Initialization as invoked in the Clowder initContainer.
#
export LOGPREFIX="Clowder Init:"
echo "${LOGPREFIX}"

export CLOWDER_ENV_FILE="/tmp/clowder_env.sh"

# This is so ansible can run with a random {u,g}id in OpenShift
echo "ansible:x:$(id -u):$(id -g):,,,:${HOME}:/bin/bash" >> /etc/passwd
echo "ansible:x:$(id -G | cut -d' ' -f 2)" >> /etc/group
id

function check_svc_status() {
  local SVC_NAME=$1 SVC_PORT=$2

  [[ $# -lt 2 ]] && echo "Error: Usage: check_svc_status svc_name svc_port" && exit 1

  while true; do
    echo "${LOGPREFIX} Checking ${SVC_NAME}:$SVC_PORT status ..."
    ncat ${SVC_NAME} ${SVC_PORT} < /dev/null && break
    sleep 5
  done
  echo "${LOGPREFIX} ${SVC_NAME}:${SVC_PORT} - accepting connections"
}

if [[ -z "${ACG_CONFIG}" ]]; then
  echo "${LOGPREFIX} Not running in a clowder environment"
else
  echo "${LOGPREFIX} Running in a clowder environment"

  if [[ ! -f "${CLOWDER_ENV_FILE}" ]]; then
    python3 /opt/cloudigrade/scripts/json_to_env.py --prefix "CLOWDER_" --export "${ACG_CONFIG}" > "${CLOWDER_ENV_FILE}"
  fi
  source "${CLOWDER_ENV_FILE}"

  export DATABASE_HOST="${CLOWDER_DATABASE_HOSTNAME}"
  export DATABASE_PORT="${CLOWDER_DATABASE_PORT}"

  # Wait for the database to be ready
  echo "${LOGPREFIX} Waiting for database readiness ..."
  check_svc_status $DATABASE_HOST $DATABASE_PORT

  # If postigrade is deployed in Clowder, let's also make sure sure that it is ready
  export PG_SVC="`env | egrep '^CLOWDER_ENDPOINTS_\d+_APP=postigrade'"

  if [[ -n "${PG_SVC}" ]]; then
    num_str=${PG_SVC##CLOWDER_ENDPOINTS_}
    EP_NUM="${num_str%_*}"
    DH_VAR="CLOWDER_ENDPOINTS_${EP_NUM}_HOSTNAME"; DATABASE_HOST="${!DH_VAR}"
    DP_VAR="CLOWDER_ENDPOINTS_${EP_NUM}_PORT";     DATABASE_PORT="${!DP_VAR}"

    echo "${LOGPREFIX} Waiting for postigrade readiness ..."
    check_svc_status $DATABASE_HOST $DATABASE_PORT
  fi
fi

ANSIBLE_CONFIG=/opt/cloudigrade/playbooks/ansible.cfg ansible-playbook -e env=${CLOUDIGRADE_ENVIRONMENT} playbooks/manage-cloudigrade.yml | tee /tmp/slack-payload

if [[ -z "${SLACK_TOKEN}" ]]; then
  echo "Cloudigrade Init: SLACK_TOKEN is not defined, not uploading the slack payload"
else
  slack_payload=`cat /tmp/slack-payload | tail -n 3`
  slack_payload="${CLOUDIGRADE_ENVIRONMENT}-${IMAGE_TAG} -- $slack_payload"
  curl -X POST --data-urlencode "payload={\"channel\": \"#cloudmeter-deployments\", \"text\": \"$slack_payload\"}" ${SLACK_TOKEN}
fi

python3 ./manage.py configurequeues
python3 ./manage.py syncbucketlifecycle
python3 ./manage.py migrate
