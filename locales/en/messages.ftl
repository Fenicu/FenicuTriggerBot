trigger-added = Trigger "{ $trigger_key }" added successfully!
trigger-add-error = Error adding trigger.
trigger-deleted = Trigger deleted.
trigger-not-found = Trigger not found.
trigger-list-header = 📂 <b>Chat Triggers</b> (Total: { $count })
trigger-list-page = Page { $page } of { $total }
trigger-edit-title = ⚙️ <b>Trigger Settings</b>
trigger-edit-key = 🔑 <b>Key:</b> <code>{ $trigger_key }</code>
trigger-edit-type = 📄 <b>Type:</b> { $type }
trigger-edit-created = 👤 <b>Created by:</b> { $user }
trigger-edit-stats = 📊 <b>Stats:</b> { $count } uses
trigger-edit-case = 🔠 <b>Case:</b> { $value }
trigger-edit-access = 🔒 <b>Access:</b> { $value }
settings-title = ⚙️ <b>Chat Settings</b>
settings-admins-only = Only admins can add: { $status }
settings-lang-changed = Language changed to { $lang }.
error-no-rights = You do not have permission.
error-permission-denied = You do not have permission to edit this trigger.
confirm-delete = Are you sure you want to delete trigger "{ $trigger_key }"?
confirm-clear = Are you sure you want to delete ALL triggers?
action-yes = ✅ Yes, delete
action-cancel = ❌ Cancel
btn-close = 🗑 Close
btn-back = « Back

btn-case-sensitive = Case: Sensitive
btn-case-insensitive = Case: Insensitive
btn-match-exact = Type: Exact
btn-match-contains = Type: Contains
btn-match-regexp = Type: Regex
btn-access-all = Access: All
btn-access-admins = Access: Admins
btn-access-owner = Access: Owner
btn-delete = 🗑 Delete
btn-clear-triggers = 🗑 Clear All Triggers
btn-admins-only-true = ✅ Admins Only Add
btn-admins-only-false = ❌ Admins Only Add
lang-select-title = 🌐 <b>Select Language</b>
btn-lang-ru = 🇷🇺 Русский
btn-lang-en = 🇺🇸 English

trigger-list-empty = No triggers found.
del-usage = Usage: /del <key>
trigger-delete-error = Failed to delete trigger.
settings-updated = Settings updated.
triggers-cleared = Deleted { $count } triggers.
triggers-cleared-text = ✅ Deleted { $count } triggers.
add-usage = Usage: /add <key> [flags]

val-case-sensitive = Sensitive
val-case-insensitive = Insensitive
val-access-all = All
val-access-admins = Admins
val-access-owner = Owner

moderation-alert =
    🚨 <b>Suspicious Trigger</b>

    Category: { $category } (conf: { $confidence })
    Chat: { $chat_id }
    ID: { $trigger_id }

    Key: { $trigger_key }
    Type: { $content_type }
    Content: { $content_text }
    Reason: { $reasoning }

moderation-approved =
    ✅ <b>Trigger Approved</b>

    Key: { $trigger_key }
    Type: { $content_type }
    Content: { $content_text }

moderation-declined =
    ❌ <b>Trigger Declined</b>

    Key: { $trigger_key }
    Type: { $content_type }
    Content: { $content_text }
    Reason: { $reason }

start-message =
    👋 <b>Hello!</b>

    I am a trigger bot, but I only work in group chats.
    Add me to a chat to start using me!

    📚 <b>Commands:</b>
    /add key - create trigger
    /del key - delete trigger
    /triggers - list triggers
    /settings - settings
    /lang - change language
    /ban - ban user
    /mute - mute user
    /warn - warn user
    /warns - list warnings
    /unban - unban user
    /unmute - unmute user

    🤖 <b>Version:</b> { $version }

mod-user-banned = User { $user } has been banned. Expires: { DATETIME($date) }. Reason: { $reason }
mod-user-muted = User { $user } has been muted. Expires: { DATETIME($date) }. Reason: { $reason }
mod-user-unbanned = User { $user } unbanned.
mod-user-unmuted = User { $user } unmuted.
mod-user-kicked = User { $user } has been kicked.
mod-warn-added = { $user } received a warning [{ $cur }/{ $max }]. Reason: { $reason }
mod-warn-removed = Warning removed. Current count: { $cur }/{ $max }.
mod-warn-reset = Warning limit exceeded. { $user } receives punishment: { $punishment }.
mod-warns-list =
    Warnings for user { $user } ({ $cur }/{ $max }):
    { $list }
mod-error-no-rights = Bot does not have enough rights to perform this operation.
mod-error-admin = I cannot punish an administrator.
mod-settings-title = 👮‍♂️ Warn System Settings
mod-settings-limit = Warn limit: { $limit }
mod-settings-punishment = Punishment: { $punishment }
mod-settings-duration = Duration: { $duration }
