rm -rf ./ansible/cmdb
rm -rf ./docs/hostinfo/

mkdir -p ./ansible/cmdb
mkdir -p ./docs/hostinfo/html

ansible -m setup --tree ansible/cmdb/ all
# ansible-cmdb -t markdown ansible/cmdb/ > docs/luxnix-hostinfo.md

# Rename all files in the cmdb directory to have the .json extension
for f in ./ansible/cmdb/*; do
    mv -- "$f" "${f%}.json"
done

for f in ./ansible/cmdb/*.json; do
    ansible-lint "$f"
    jq '.' "$f" > tmp.$$.json && mv tmp.$$.json "$f"
done
