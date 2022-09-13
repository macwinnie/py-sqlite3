#!/usr/bin/env bash

apt update
apt install -y \
    jq xmlstarlet \
    python3-dev python3-wheel \
    tree

rm -rf "$( pwd )/Pipfile.lock"

pip install --user --upgrade \
    pip\
    pipenv\
    pipfile\
    twine

export PATH="$( cd ~; pwd )/.local/bin:${PATH}"

pipenv install --dev

# export env variables to .env file
export DEBIAN_FRONTEND="noninteractive"
env | grep -E '^((TWINE)|(INC_VERSION)|(WD_PATH)|(DEBIAN_FRONTEND))' > "$(pwd)/.env"

# activate pipenv and build
chmod a+x "$( pwd )/wf_build.sh"
pipenv run bash -c "$( pwd )/wf_build.sh; exit"
# pipenv shell "$( pwd )/wf_build.sh; exit"
