"""Controller-only approval: never send displayed credentials to callbacks."""

from ansible.plugins.action import ActionBase

from lx_administration.models.vault.admin_rotation import confirm_on_terminal


class ActionModule(ActionBase):
    TRANSFERS_FILES = False
    _supports_check_mode = False

    def run(self, tmp=None, task_vars=None):
        result = {"changed": False, "_ansible_no_log": True}
        if self._task.check_mode:
            return dict(
                result, failed=True, msg="Rotation requires interactive approval"
            )
        try:
            approved = confirm_on_terminal(
                self._task.args["host"], self._task.args["credential"]
            )
        except (Exception, KeyboardInterrupt) as error:
            return dict(
                result,
                failed=True,
                msg=(
                    f"Rotation approval unavailable ({type(error).__name__}); "
                    "no password activated"
                ),
            )
        if not approved:
            return dict(
                result, failed=True, msg="Rotation cancelled; no password activated"
            )
        return dict(result, approved=True)
