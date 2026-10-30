import pytest

from lx_administration.models.vault import SecretTemplate
from lx_administration.models.vault.manager import _template_applies_to_host


@pytest.mark.parametrize(
    ("owner_type", "template_name", "expected"),
    [
        ("roles", "web", True),
        ("roles", "worker", False),
        ("groups", "production", True),
        ("groups", "staging", False),
        ("local", "admin@client-01", True),
        ("local", "admin@client-02", False),
        ("clients", "deploy@client-01", True),
        ("clients", "deploy@client-02", False),
    ],
)
def test_template_applies_to_host(owner_type, template_name, expected):
    template = SecretTemplate(name=template_name, owner_type=owner_type)

    assert (
        _template_applies_to_host(
            template,
            hostname="client-01",
            role_names={"web"},
            group_names={"production"},
        )
        is expected
    )


@pytest.mark.parametrize("owner_type", ["services", "luxnix"])
def test_non_host_owner_type_cannot_be_matched(owner_type):
    template = SecretTemplate(name="global", owner_type=owner_type)

    with pytest.raises(
        ValueError, match=f"Cannot match owner_type '{owner_type}' to a host"
    ):
        _template_applies_to_host(
            template,
            hostname="client-01",
            role_names=set(),
            group_names=set(),
        )
