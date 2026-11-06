/* Capture only; unlock in open_session after the complete PAM authentication.
 * No setuid entrypoint, password environment variable, or logout lock. */
#define _GNU_SOURCE
#include <security/pam_modules.h>
#include <security/pam_ext.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <unistd.h>
#include <string.h>
#include <stdlib.h>
#include <errno.h>
#include <syslog.h>

struct token { char user[256]; char password[4097]; };
static void cleanup(pam_handle_t *pamh, void *data, int status) {
    (void)pamh; (void)status;
    explicit_bzero(data, sizeof(struct token));
    munmap(data, sizeof(struct token));
}
static int allowed(const char *user, int argc, const char **argv) {
    for (int i = 0; i < argc; i++) if (!strcmp(user, argv[i])) return 1;
    return 0;
}
PAM_EXTERN int pam_sm_authenticate(pam_handle_t *pamh, int flags, int argc, const char **argv) {
    (void)flags;
    const char *user = NULL, *password = NULL;
    /* Clear any token retained from an earlier attempt on this handle. */
    pam_set_data(pamh, "luxnix-storage-token", NULL, NULL);
    if (pam_get_user(pamh, &user, NULL) != PAM_SUCCESS || !allowed(user, argc, argv)) return PAM_IGNORE;
    if (pam_get_authtok(pamh, PAM_AUTHTOK, &password, NULL) != PAM_SUCCESS || !password) return PAM_IGNORE;
    if (strlen(user) >= 256 || strlen(password) > 4096) return PAM_IGNORE;
    struct token *data = mmap(NULL, sizeof(*data), PROT_READ | PROT_WRITE,
                             MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (data == MAP_FAILED) return PAM_IGNORE;
    if (mlock(data, sizeof(*data)) || madvise(data, sizeof(*data), MADV_DONTDUMP)) {
        cleanup(pamh, data, 0); return PAM_IGNORE;
    }
    strcpy(data->user, user); strcpy(data->password, password);
    if (pam_set_data(pamh, "luxnix-storage-token", data, cleanup) != PAM_SUCCESS) cleanup(pamh, data, 0);
    return PAM_IGNORE;
}
PAM_EXTERN int pam_sm_open_session(pam_handle_t *pamh, int flags, int argc, const char **argv) {
    (void)flags;
    const void *saved = NULL;
    const char *user = NULL;
    if (pam_get_data(pamh, "luxnix-storage-token", &saved) != PAM_SUCCESS || !saved) return PAM_IGNORE;
    const struct token *data = saved;
    int result = PAM_SESSION_ERR, sockets[2], status = 0;
    if (geteuid() || pam_get_user(pamh, &user, NULL) != PAM_SUCCESS ||
        strcmp(user, data->user) || !allowed(user, argc, argv)) goto done;
    if (socketpair(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0, sockets)) goto done;
    pid_t child = fork();
    if (child == 0) {
        if (dup2(sockets[1], STDIN_FILENO) < 0) _exit(126);
        close(sockets[0]); close(sockets[1]);
        char *const env[] = { "PATH=/run/current-system/sw/bin", "LANG=C", NULL };
        char *const command[] = { HELPER, "unlock", "--user", (char *)user, "--pam", NULL };
        execve(HELPER, command, env); _exit(127);
    }
    close(sockets[1]);
    if (child < 0) { close(sockets[0]); goto done; }
    size_t length = strlen(data->password), sent = 0;
    while (sent < length) {
        ssize_t n = send(sockets[0], data->password + sent, length - sent, MSG_NOSIGNAL);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) break;
        sent += (size_t)n;
    }
    close(sockets[0]);
    pid_t waited;
    do { waited = waitpid(child, &status, 0); } while (waited < 0 && errno == EINTR);
    if (waited == child && WIFEXITED(status) && WEXITSTATUS(status) == 0) result = PAM_SUCCESS;
done:
    pam_set_data(pamh, "luxnix-storage-token", NULL, NULL);
    if (result != PAM_SUCCESS) pam_syslog(pamh, LOG_ERR, "Storage unlock failed; login remains available for recovery");
    return result;
}
PAM_EXTERN int pam_sm_close_session(pam_handle_t *pamh, int flags, int argc, const char **argv) {
    (void)pamh; (void)flags; (void)argc; (void)argv; return PAM_SUCCESS;
}
PAM_EXTERN int pam_sm_setcred(pam_handle_t *pamh, int flags, int argc, const char **argv) {
    (void)pamh; (void)flags; (void)argc; (void)argv; return PAM_IGNORE;
}
