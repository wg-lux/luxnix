{
    lib,
    pkgs,
    config,
}
let
    

    pkgs.writeShellScript "setup-endoreg-db-local-user" ''
        set -euo pipefail
        
        # Wait for PostgreSQL to be ready
        echo "Waiting for PostgreSQL to be ready..."
        for i in {1..30}; do
        if ${config.services.postgresql.package}/bin/pg_isready -U postgres -d postgres; then
            echo "PostgreSQL is ready"
            break
        fi
        if [ $i -eq 30 ]; then
            echo "ERROR: PostgreSQL not ready after 30 attempts"
            exit 1
        fi
        echo "Attempt $i: PostgreSQL not ready, waiting 2 seconds..."
        sleep 2
        done
        
        # Create password if it doesn't exist
        if [ ! -f ${maintenancePasswordFile} ]; then
        echo "Generating password for endoregDbLocal user..."
        mkdir -p $(dirname ${maintenancePasswordFile})
        ${pkgs.openssl}/bin/openssl rand -base64 32 > ${maintenancePasswordFile}
        chmod 640 ${maintenancePasswordFile}
        chown root:${config.luxnix.generic-settings.sensitiveServiceGroupName} ${maintenancePasswordFile}
        fi
        
        # Ensure correct permissions on existing file
        chmod 640 ${maintenancePasswordFile}
        chown root:${config.luxnix.generic-settings.sensitiveServiceGroupName} ${maintenancePasswordFile}
        
        # Copy password for PostgreSQL access
        cp ${maintenancePasswordFile} ${endoregDbLocalPasswordFile}
        chown postgres:postgres ${endoregDbLocalPasswordFile}
        chmod 600 ${endoregDbLocalPasswordFile}
        
        # Set the password in PostgreSQL safely using dollar-quoted strings
        # Dollar-quoting prevents SQL injection by treating the content as a literal string
        echo "Setting password for user ${cfg.defaultDbName}..."
        
        PASSWORD=$(cat ${endoregDbLocalPasswordFile})
        
        # Use dollar-quoted strings ($tag$...$tag$) which safely handle any special characters
        # including single quotes, backslashes, and other SQL metacharacters
        ${config.services.postgresql.package}/bin/psql -U postgres -d postgres -c \
        "ALTER USER \"${cfg.defaultDbName}\" WITH PASSWORD \$securepass\$''${PASSWORD}\$securepass\$;"
        
        echo "endoregDbLocal user password configured successfully"
    '';