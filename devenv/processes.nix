{pkgs, ...}: {
  processes = {
    processes.migrate = {
      enable = true;
      start = ''
        cd endoreg_db
        python manage.py makemigrations
        python manage.py migrate
      '';
    };
  };
}