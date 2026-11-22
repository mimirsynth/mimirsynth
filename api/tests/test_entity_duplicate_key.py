"""The duplicates tab's name key: spelling variants group, values glued to a name do not, and address-like names are compared."""
from test_control import client  # noqa: F401  (sets the test environment before mimirsynth is imported)

from mimirsynth.graphapi import _entity_key


def test_spelling_variants_group():
    assert _entity_key("VM 201") == _entity_key("VM201") == _entity_key("vm-201") == _entity_key("  Vm_201 ")
    assert _entity_key("Raspberry Pi") == _entity_key("RaspberryPi")


def test_trailing_version_as_a_word_is_ignored():
    assert _entity_key("Web-Vault 2026.4.1") == _entity_key("Web-Vault") == _entity_key("webvault")
    assert _entity_key("Nextcloud v31.0.1") == _entity_key("Nextcloud (31.0.1)") == _entity_key("Nextcloud")


def test_values_glued_to_a_name_are_not_versions():
    assert _entity_key("ups@10.0.100.114") != _entity_key("ups@10.0.100.164")
    assert _entity_key("min_similarity=0.55") != _entity_key("min_similarity=0.65")
    assert _entity_key("backups/app-pre-0.15.0-20261109") != _entity_key("backups/app-pre-0.14.0-20261108")


def test_address_and_bare_version_names_are_compared_whole():
    assert _entity_key("10.0.100.201") == _entity_key(" 10.0.100.201") == "10.0.100.201"
    assert _entity_key("10.0.100.201") != _entity_key("10.0.100.20")
    assert _entity_key("0.14.0") != _entity_key("0.15.0") and _entity_key("0.14.0")
    assert _entity_key("") == "" and _entity_key(None) == ""


def test_different_names_stay_apart():
    assert _entity_key("Debian 12") != _entity_key("Debian 13")
    assert _entity_key("LXC 110") != _entity_key("LXC 111")


def test_four_part_numbers_are_kept_and_suffixes_are_stripped():
    assert _entity_key("AdGuard 10.0.100.101") != _entity_key("AdGuard 10.0.100.102")
    assert _entity_key("App 1.2.3-rc1") == _entity_key("App (v1.2)") == _entity_key("app")


def test_casefold_and_typographic_dashes():
    assert _entity_key("Straße") == _entity_key("STRASSE")
    assert _entity_key("Web–Vault") == _entity_key("Web-Vault")
    assert _entity_key("Ünïcode 1.2") == _entity_key("ünïcode")
    assert _entity_key("U" + chr(0x308) + "ber") == _entity_key(chr(0xDC) + "ber")  # decomposed and composed «Ü»


def test_ignore_marks_saved_in_the_old_key_format_still_match():
    # before this change the key kept single spaces: «Web-Vault» was saved as «web vault»
    assert _entity_key("web vault") == _entity_key("Web-Vault 2026.4.1")
