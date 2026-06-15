"""Проверка что все используемые wizard'ом i18n-ключи определены в обоих локалях."""
from pathlib import Path

import pytest

LOCALES_DIR = Path(__file__).resolve().parents[2] / "locales"

REQUIRED_KEYS = [
    "new-trigger-group-entry-body",
    "new-trigger-group-entry-button",
    "new-trigger-lobby-title",
    "new-trigger-lobby-empty",
    "new-trigger-lobby-page-indicator",
    "new-trigger-content-prompt",
    "new-trigger-content-saved",
    "new-trigger-content-command-warning",
    "new-trigger-key-prompt",
    "new-trigger-key-empty",
    "new-trigger-key-too-long",
    "new-trigger-flags-title",
    "new-trigger-flags-match-exact",
    "new-trigger-flags-match-contains",
    "new-trigger-flags-match-regex",
    "new-trigger-flags-case-on",
    "new-trigger-flags-access-all",
    "new-trigger-flags-access-admins",
    "new-trigger-flags-access-owner",
    "new-trigger-flags-template",
    "new-trigger-flags-regex-invalid",
    "new-trigger-flags-template-invalid",
    "new-trigger-confirm-summary",
    "new-trigger-confirm-created",
    "new-trigger-confirm-moderation-pending",
    "new-trigger-conflict-body",
    "new-trigger-conflict-keep",
    "new-trigger-permission-denied",
    "new-trigger-permission-lost",
    "new-trigger-cancel-done",
    "new-trigger-send-copy-failed",
    "new-trigger-send-copy-retry-after",
    "new-trigger-session-expired",
    "new-trigger-save-busy",
    "new-trigger-preview-entities-warning",
    "new-trigger-content-wrong-type",
    "new-trigger-key-wrong-type",
    "new-trigger-flags-wrong-input",
    "new-trigger-create-failed",
    "new-trigger-conflict-body-foreign",
    "new-trigger-btn-use-this",
    "new-trigger-btn-send-another",
    "new-trigger-btn-cancel",
    "new-trigger-btn-next",
    "new-trigger-btn-save",
    "new-trigger-btn-again",
    "new-trigger-btn-finish",
    "new-trigger-btn-back-to-chat",
    "new-trigger-btn-back-to-key",
    "new-trigger-btn-back-to-flags",
    "new-trigger-btn-restart",
    "new-trigger-btn-keep",
]


@pytest.mark.parametrize("locale", ["ru", "en"])
def test_all_new_trigger_keys_present(locale):
    ftl = (LOCALES_DIR / locale / "messages.ftl").read_text(encoding="utf-8")
    missing = [k for k in REQUIRED_KEYS if f"{k} =" not in ftl]
    assert not missing, f"Missing keys in {locale}: {missing}"
