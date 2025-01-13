rm -rf ./ansible/cmdb
rm -rf ./docs/hostinfo/

mkdir -p ./ansible/cmdb
mkdir -p ./docs/hostinfo/html

ansible -m setup --tree ansible/cmdb/ all
ansible-cmdb -t markdown ansible/cmdb/ > docs/luxnix-hostinfo.md

ansible-cmdb -t html_fancy_split ansible/cmdb/
ansible-cmdb -t json ansible/cmdb/ > conf/hostinfo.json
# mv ./ansible/cmdb/*.html ./docs/hostinfo/html

cd .."