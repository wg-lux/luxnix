```doc
Usage: ansible-cmdb [option] <dir> > output.html

Options:
  --version             show program's version number and exit
  -h, --help            show this help message and exit
  -t TEMPLATE, --template=TEMPLATE
                        Template to use. Default is 'html_fancy'
  -i INVENTORY, --inventory=INVENTORY
                        Inventory to read extra info from
  -f, --fact-cache      <dir> contains fact-cache files
  -p PARAMS, --params=PARAMS
                        Params to send to template
  -d, --debug           Show debug output
  -q, --quiet           Don't report warnings
  -c COLUMNS, --columns=COLUMNS
                        Show only given columns
  -C CUST_COLS, --cust-cols=CUST_COLS
                        Path to a custom columns definition file
  -l LIMIT, --limit=LIMIT
                        Limit hosts to pattern
  --exclude-cols=EXCLUDE_COLUMNS
                        Exclude cols from output

```

; Patterns:
; webservers:dbservers -> all hosts in the webservers or the dbserver group
; webservers:&dbservers -> all hosts in both the webservers and the dbserver group
; webservers:!dbservers -> all hosts in the webservers group that are not in the dbserver group
; webservers:dbservers:&staging:!phoenix -> all machines in the groups ‘webservers’ and ‘dbservers’ are to be managed if they are in the group ‘staging’ also, but the machines are not to be managed if they are in the group ‘phoenix’
; in host lists the : can be interchanged with ,

cd ~/luxnix/ansible
ansible -m setup --tree cmdb/ all
ansible-cmdb cmdb/ > overview.html

---

Source: https://github.com/fboender/ansible-cmdb

Getting started

Links to the full documentation can be found below, but here's a rough indication of how Ansible-cmdb works to give you an idea:

    Install Ansible-cmdb from source, a release package or through pip: pip install ansible-cmdb.

    Fetch your host's facts through ansible:

     $ mkdir out
     $ ansible -m setup --tree out/ all

Generate the CMDB HTML with Ansible-cmdb:

$ ansible-cmdb out/ > overview.html

    Open overview.html in your browser.

That's it! Please do read the full documentation on usage, as there are some caveats to how you can use the generated HTML.
Documentation

All documentation can be viewed at readthedocs.io.

    Full documentation
    Requirements and installation
    Usage
    Contributing and development

License

Ansible-cmdb is licensed under the GPLv3:

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.

For the full license, see the LICENSE file.
