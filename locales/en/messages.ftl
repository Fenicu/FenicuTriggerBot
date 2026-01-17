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
settings-captcha = 🧩 Captcha on join: { $status }
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
del-usage = Usage: /del &lt;key&gt;
trigger-delete-error = Failed to delete trigger.
settings-updated = Settings updated.
triggers-cleared = Deleted { $count } triggers.
triggers-cleared-text = ✅ Deleted { $count } triggers.
add-usage = Usage: /add &lt;key&gt; [flags]

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

anime-searching = 🔎 Searching anime...
anime-found =
    🎬 <b>Anime found!</b>

    🇯🇵 <b>Title:</b> { $title_native }
    🇬🇧 <b>English:</b> { $title_english }
    📺 <b>Episode:</b> { $episode }
    ⏱ <b>Timecode:</b> { $timecode }
    📊 <b>Similarity:</b> { $similarity }%
anime-not-found = ❌ Anime not found.
anime-error = ❌ An error occurred during search.
anime-error-reply = ❌ Use this command in reply to an image, GIF, or video.

chat-became-trusted = 🛡 Chat became trusted thanks to user { $user }.
args-error = ❌ Error in arguments.
user-not-found = ❌ User not found.
user-promoted-mod = ✅ User { $user } promoted to bot moderator.
user-demoted-mod = ℹ️ User { $user } is no longer a bot moderator.
user-trusted = ✅ User { $user } is now trusted.
user-untrusted = ℹ️ User { $user } is no longer trusted.
settings-trusted = 🛡 Chat is trusted
error-private-only = This command is available only in private chat.

btn-captcha-true = ✅ Captcha
btn-captcha-false = ❌ Captcha
settings-timezone = 🌍 Timezone: { $timezone }
settings-triggers = 🎯 Triggers module: { $status }
settings-moderation = 👮‍♂️ Moderation module: { $status }
btn-triggers-true = ✅ Triggers
btn-triggers-false = ❌ Triggers
btn-moderation-true = ✅ Moderation
btn-moderation-false = ❌ Moderation
settings-select-timezone = 🌍 Select timezone or enter timezone name (e.g., Europe/Moscow)
btn-custom-timezone = ✏️ Enter manually
settings-enter-timezone = 🌍 Enter timezone name (e.g., Europe/Moscow) and send as message.
settings-timezone-updated = ✅ Timezone changed to { $timezone }
error-invalid-timezone = ❌ Invalid timezone. Please try again.
captcha-verify = 👋 { $user }, please complete the verification. Click the button below.
btn-verify = 🔐 Verify
captcha-not-found = ❌ Captcha session not found or expired.
captcha-wrong-user = ❌ This captcha is for a different user.
captcha-already-completed = ✅ You have already completed this captcha.
captcha-expired = ⏱ Time to complete the captcha has expired.
captcha-open-webapp = 👇 Click the button below to complete the verification:
captcha-invalid-link = ❌ Invalid captcha link.
captcha-success = ✅ Verification passed! Welcome.
captcha-timeout-kick = ❌ Time expired. User has been kicked.

var-set = ✅ Variable <code>{ $key }</code> set.
var-deleted = 🗑 Variable <code>{ $key }</code> deleted.
var-not-found = ❌ Variable <code>{ $key }</code> not found.
var-list-empty = ℹ️ Variable list is empty.
var-list-header = 📋 <b>Chat Variables:</b>
var-invalid-key = ❌ Invalid key format. Use only latin letters and <code>_</code>.
var-usage-set = ℹ️ Usage: <code>/setvar &lt;key&gt; &lt;value&gt;</code>
var-usage-del = ℹ️ Usage: <code>/delvar &lt;key&gt;</code>

