### **Best Practice Guide for YAML Configuration and Management**

This guide outlines a pragmatic approach for creating, validating, and managing YAML configurations. It includes specific instructions and linting configurations.

---

#### **1. YAML Best Practices**
1. **Consistency**:
   - Use spaces for indentation (2 spaces recommended).
   - Always use lowercase for keys.
   - Use consistent naming conventions (e.g., `snake_case` for keys).

2. **Structure**:
   - Use lists for repeated items.
   - Use dictionaries for key-value relationships.
   - Use anchors and aliases for reusable configurations.

3. **Validation**:
   - Use schemas to enforce structure and data types.
   - Validate files with tools like `yamllint` and `jsonschema`.

4. **Templating**:
   - Use Jinja2 for generating YAML configurations dynamically.

---

#### **2. Linting Configuration**

Use `yamllint` for enforcing style and catching errors.

**Install `yamllint`:**
```bash
pip install yamllint
```

**Create `.yamllint` Configuration:**
```yaml
extends: relaxed
rules:
  line-length:
    max: 120
    level: warning
  indentation:
    spaces: 2
  trailing-spaces:
    level: error
  document-start:
    present: true
```

**Run Linting:**
```bash
yamllint config.yaml
```

---

#### **3. Schema Validation**
**Install `jsonschema`:**
```bash
pip install jsonschema
```

**Example Schema for Network Configuration (`network_config.schema.yaml`):**
```yaml
$schema: "http://json-schema.org/draft-07/schema#"
type: "object"
properties:
  systems:
    type: "array"
    items:
      type: "object"
      properties:
        hostname:
          type: "string"
        ip:
          type: "string"
          pattern: "^([0-9]{1,3}\\.){3}[0-9]{1,3}$"
        roles:
          type: "array"
          items:
            type: "string"
        openvpn_ip:
          type: "string"
          pattern: "^([0-9]{1,3}\\.){3}[0-9]{1,3}$"
  users:
    type: "array"
    items:
      type: "object"
      properties:
        username:
          type: "string"
        roles:
          type: "array"
          items:
            type: "string"
        permissions:
          type: "object"
          additionalProperties:
            type: "boolean"
required:
  - systems
  - users
```

**Validate with Python:**
```python
import yaml
from jsonschema import validate, ValidationError

def validate_yaml(file_path, schema_path):
    with open(file_path, 'r') as file:
        config = yaml.safe_load(file)

    with open(schema_path, 'r') as schema_file:
        schema = yaml.safe_load(schema_file)

    try:
        validate(instance=config, schema=schema)
        print("Validation passed!")
    except ValidationError as e:
        print(f"Validation failed: {e.message}")

# Validate your config.yaml
validate_yaml('config.yaml', 'network_config.schema.yaml')
```

---

#### **4. Templating Setup**

**Install Jinja2:**
```bash
pip install jinja2
```

**Template (`network_config_template.yaml`):**
```yaml
systems:
{% for system in systems %}
  - hostname: "{{ system.hostname }}"
    ip: "{{ system.ip }}"
    roles:
    {% for role in system.roles %}
      - "{{ role }}"
    {% endfor %}
    openvpn_ip: "{{ system.openvpn_ip }}"
{% endfor %}
users:
{% for user in users %}
  - username: "{{ user.username }}"
    roles:
    {% for role in user.roles %}
      - "{{ role }}"
    {% endfor %}
    permissions:
    {% for perm, value in user.permissions.items() %}
      {{ perm }}: {{ value | lower }}
    {% endfor %}
{% endfor %}
```

**Render Template with Python:**
```python
from jinja2 import Environment, FileSystemLoader

def render_template(template_file, output_file, context):
    env = Environment(loader=FileSystemLoader('.'))
    template = env.get_template(template_file)
    rendered_content = template.render(context)

    with open(output_file, 'w') as file:
        file.write(rendered_content)

# Example data
context = {
    "systems": [
        {
            "hostname": "server1",
            "ip": "10.0.0.1",
            "roles": ["db", "web"],
            "openvpn_ip": "10.8.0.1"
        },
        {
            "hostname": "server2",
            "ip": "10.0.0.2",
            "roles": ["app"],
            "openvpn_ip": "10.8.0.2"
        }
    ],
    "users": [
        {
            "username": "admin",
            "roles": ["admin", "operator"],
            "permissions": {"read": True, "write": True, "execute": True}
        },
        {
            "username": "user1",
            "roles": ["guest"],
            "permissions": {"read": True, "write": False, "execute": False}
        }
    ]
}

# Render template
render_template('network_config_template.yaml', 'output.yaml', context)
```

**Rendered Output (`output.yaml`):**
```yaml
systems:
  - hostname: "server1"
    ip: "10.0.0.1"
    roles:
      - "db"
      - "web"
    openvpn_ip: "10.8.0.1"
  - hostname: "server2"
    ip: "10.0.0.2"
    roles:
      - "app"
    openvpn_ip: "10.8.0.2"
users:
  - username: "admin"
    roles:
      - "admin"
      - "operator"
    permissions:
      read: true
      write: true
      execute: true
  - username: "user1"
    roles:
      - "guest"
    permissions:
      read: true
      write: false
      execute: false
```

---

### **Putting It All Together**
1. **Linting**: Ensure all configurations are correctly formatted with `yamllint`.
2. **Validation**: Validate configurations against schemas using `jsonschema`.
3. **Templating**: Use Jinja2 for dynamic and reusable YAML file generation.
