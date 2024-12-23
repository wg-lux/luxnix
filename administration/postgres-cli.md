# **psql CLI Cheat Sheet: User Management**
(*ChatGPT*)
This cheat sheet provides commonly used `psql` commands for creating and managing users in PostgreSQL.

---

## **1. Connect to PostgreSQL**
### Syntax:
```bash
psql -h <host> -U <username> -d <database>
```

### Example:
```bash
psql -h localhost -U postgres -d postgres
```

---

## **2. User Management Commands**

### **List All Users**
```sql
\du
```

---

### **Create a New User**
```sql
CREATE USER <username> WITH PASSWORD '<password>';
```

#### Example:
```sql
CREATE USER dev_user WITH PASSWORD 'securepassword123';
```

---

### **Grant Privileges to a User**
1. **Grant All Privileges on a Database**:
   ```sql
   GRANT ALL PRIVILEGES ON DATABASE <database_name> TO <username>;
   ```

   **Example**:
   ```sql
   GRANT ALL PRIVILEGES ON DATABASE my_database TO dev_user;
   ```

2. **Grant Usage and Permissions on Schemas**:
   ```sql
   GRANT USAGE ON SCHEMA <schema_name> TO <username>;
   GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA <schema_name> TO <username>;
   ```

---

### **Alter User Properties**
1. **Change User Password**:
   ```sql
   ALTER USER <username> WITH PASSWORD '<new_password>';
   ```

   **Example**:
   ```sql
   ALTER USER dev_user WITH PASSWORD 'newpassword456';
   ```

2. **Grant User Superuser Privileges**:
   ```sql
   ALTER USER <username> WITH SUPERUSER;
   ```

   **Example**:
   ```sql
   ALTER USER dev_user WITH SUPERUSER;
   ```

3. **Set User Resource Limits**:
   ```sql
   ALTER USER <username> WITH CONNECTION LIMIT <limit>;
   ```

   **Example**:
   ```sql
   ALTER USER dev_user WITH CONNECTION LIMIT 5;
   ```

---

### **Drop a User**
```sql
DROP USER <username>;
```

#### Example:
```sql
DROP USER dev_user;
```

---

## **3. Role Management**

### **Create a New Role**
```sql
CREATE ROLE <role_name> WITH LOGIN PASSWORD '<password>';
```

#### Example:
```sql
CREATE ROLE readonly_user WITH LOGIN PASSWORD 'readonly123';
```

---

### **Grant a Role to a User**
```sql
GRANT <role_name> TO <username>;
```

#### Example:
```sql
GRANT readonly_user TO dev_user;
```

---

### **Revoke a Role from a User**
```sql
REVOKE <role_name> FROM <username>;
```

#### Example:
```sql
REVOKE readonly_user FROM dev_user;
```

---

## **4. Miscellaneous Commands**

### **Check Current User**
```sql
SELECT CURRENT_USER;
```

### **Exit the `psql` Shell**
```bash
\q
```

---

## **5. Useful Meta-Commands**
- **List Databases**:
  ```bash
  \l
  ```
- **Connect to a Database**:
  ```bash
  \c <database_name>
  ```
- **List All Roles**:
  ```bash
  \du
  ```
- **Describe Role Privileges**:
  ```bash
  \du <role_name>
  ```

---

## **6. Example Workflow**

### Step 1: Create a User
```sql
CREATE USER app_user WITH PASSWORD 'mypassword';
```

### Step 2: Grant Database Privileges
```sql
GRANT ALL PRIVILEGES ON DATABASE my_database TO app_user;
```

### Step 3: Set Connection Limits
```sql
ALTER USER app_user WITH CONNECTION LIMIT 10;
```

### Step 4: Assign a Role
```sql
CREATE ROLE db_admin;
GRANT db_admin TO app_user;
```

### Step 5: Verify User
```sql
\du
```
