#!/usr/bin/env bash

set -e

# retrieve build config
curPath="$( pwd )"
configFile="${curPath}/buildconfig.json"
tmpCFile="/tmp/bc.json"
docPath="docs/mods"

# retrieve publishing version
# using semantic versioning – see https://semver.org
publishVersion="$( cat "${configFile}" | jq -r ".version" )"
if [ "${INC_VERSION:-false}" = "true" ]; then
    # increase patch part of version
    publishVersion="$( echo ${publishVersion} | awk -F. -v OFS=. '{$NF += 1 ; print}' )"
    # write new version into buildconfig.json
    cat "${configFile}" | jq --arg newVer "${publishVersion}" '.version = $newVer' 1> "${tmpCFile}"
    mv "${tmpCFile}" "${configFile}"
fi

# delete old documentation files
rm -rf "${docPath}" || true
mkdir -p "${docPath}"

# write out documentation for all python classes in src folder
FILES="$( pwd )/src/macwinnie_sqlite3/*.py"
for f in ${FILES}; do
    if [ "$( basename -- "${f}" )" != "__init__.py" ]; then
        pdoc --html "${f}" --output-dir "${docPath}" --force
    fi
done

#  update index page of documentation
cd "${curPath}/${docPath}/.."
## write out update date
xmlstarlet ed -O --inplace -u '//*/span[@id="update_date"]' -v "$( date )" index.html
## remove old list of documentation files
xmlstarlet ed -O --inplace -u '//*/ul[@id="doc_list"]'      -v ""          index.html
## add current list of documentation files
FILES="${curPath}/${docPath}/*.html"
filePrefix="$( pwd )/"
lastLiXPath='//*/ul[@id="doc_list"]/li[last()]/a'
for f in ${FILES}; do
    xmlstarlet ed -O --inplace --subnode '//*/ul[@id="doc_list"]' --type elem -n li \
        --subnode '//*/ul[@id="doc_list"]/li[last()]' --type elem -n a -v "$( basename -- "${f}" )" index.html
    xmlstarlet ed -O --inplace --insert "${lastLiXPath}" --type attr -n target -v '_blank' \
        --insert "${lastLiXPath}" --type attr -n href -v "${f#"$filePrefix"}" index.html
done

cd "${curPath}"

# run tests
FILES="$( pwd )/tests/*.py"
for f in ${FILES}; do
    python "${f}"
done

# build python library
python3 -m build

# upload to PyPI
twine upload dist/*

exit 0
