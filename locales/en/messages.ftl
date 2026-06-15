lang-display-name = 🇺🇸 English
trigger-added = Trigger "{ $trigger_key }" added successfully!
trigger-add-error = Error adding trigger.
trigger-deleted = Trigger deleted.
trigger-missing = Trigger not found.
trigger-list-header = 📂 <b>Chat Triggers</b> (Total: { $count })
trigger-list-page = Page { $page } of { $total }
trigger-edit-title = ⚙️ <b>Trigger Settings</b>
trigger-edit-key = 🔑 <b>Key:</b> <code>{ $trigger_key }</code>
trigger-edit-type = 📄 <b>Type:</b> { $type }
trigger-edit-created = 👤 <b>Created by:</b> { $user }
trigger-edit-stats = 📊 <b>Stats:</b> { $count } uses
trigger-edit-case = 🔠 <b>Case:</b> { $value }
trigger-edit-template = 📝 <b>Template:</b> { $value }
trigger-edit-access = 🔒 <b>Access:</b> { $value }
settings-title = ⚙️ <b>Chat Settings</b>

# settings-admins-only = Only admins can add: { $status }


# settings-captcha = 🧩 Captcha on join: { $status }

settings-lang-changed = Language changed to { $lang }.
error-no-rights = You do not have permission.
error-permission-denied = You do not have permission to edit this trigger.
error-unknown = ❌ An unknown error occurred.
confirm-delete = Are you sure you want to delete trigger "{ $trigger_key }"?
confirm-clear = Are you sure you want to delete ALL triggers?
action-yes = ✅ Yes, delete
action-cancel = ❌ Cancel
btn-close = 🗑 Close
btn-back = « Back
btn-case-sensitive = Case: Sensitive
btn-case-insensitive = Case: Insensitive
btn-matchtype-exact = Type: Exact
btn-matchtype-contains = Type: Contains
btn-matchtype-regexp = Type: Regex
btn-access-all = Access: All
btn-access-admins = Access: Admins
btn-access-owner = Access: Owner
btn-template-true = Template: On
btn-template-false = Template: Off
btn-delete = 🗑 Delete
btn-clear-triggers = 🗑 Clear All Triggers
btn-admins-only-true = ✅ Admins Only Add
btn-admins-only-false = ❌ Admins Only Add
lang-select-title = 🌐 <b>Select Language</b>
trigger-list-empty = No triggers found.
delete-usage = Usage: /del &lt;key&gt;
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
val-template-true = Yes
val-template-false = No
moderation-alert =
    🚨 <b>Suspicious Trigger</b>

    Category: { $category } (conf: { $confidence })
    Chat: { $chat_id }
    ID: { $trigger_id }

    Key: { $trigger_key }
    Type: { $content_type }
    Content: { $content_text }
    Reason: { $reasoning }

# moderation-approved =
#     ✅ <b>Trigger Approved</b>
#     
#     Key: { $trigger_key }
#     Type: { $content_type }
#     Content: { $content_text }

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

# mod-settings-punishment = Punishment: { $punishment }


# mod-settings-duration = Duration: { $duration }

anime-searching = 🔎 Searching anime...
anime-found =
    🎬 <b>Anime found!</b>
    
    🇯🇵 <b>Title:</b> { $title_native }
    🇬🇧 <b>English:</b> { $title_english }
    📺 <b>Episode:</b> { $episode }
    ⏱ <b>Timecode:</b> { $timecode }
    📊 <b>Similarity:</b> { $similarity }%
anime-missing = ❌ Anime not found.
anime-error = ❌ An error occurred during search.
anime-error-reply = ❌ Use this command in reply to an image, GIF, or video.
chat-became-trusted = 🛡 Chat became trusted thanks to user { $user }.
args-error = ❌ Error in arguments.
user-missing = ❌ User not found.
user-promoted-mod = ✅ User { $user } promoted to bot moderator.
user-demoted-mod = ℹ️ User { $user } is no longer a bot moderator.
user-trusted = ✅ User { $user } is now trusted.
user-untrusted = ℹ️ User { $user } is no longer trusted.
settings-trusted = 🛡 Chat is trusted
error-private-only = This command is available only in private chat.
btn-captcha-true = ✅ Captcha
btn-captcha-false = ❌ Captcha
settings-timezone = 🌍 Timezone: { $timezone }

# settings-triggers = 🎯 Triggers module: { $status }


# settings-moderation = 👮‍♂️ Moderation module: { $status }

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
captcha-missing = ❌ Captcha session not found or expired.
captcha-wrong-user = ❌ This captcha is for a different user.
captcha-already-completed = ✅ You have already completed this captcha.
captcha-expired = ⏱ Time to complete the captcha has expired.
captcha-open-webapp = 👇 Click the button below to complete the verification:
captcha-invalid-link = ❌ Invalid captcha link.
captcha-success = ✅ Verification passed! Welcome.
captcha-timeout-kick = ❌ Time expired. User has been kicked.
captcha-emoji = 🧩 { $user }, find the { $color } { $emoji }
captcha-color-danger = red
captcha-color-success = green
captcha-color-primary = blue
captcha-foreign = ❌ This captcha is not for you.
captcha-retry = ❌ Incorrect! Attempts left: { $attempts }
captcha-fail = ❌ You failed the captcha and have been kicked.
var-set = ✅ Variable <code>{ $name }</code> set.
var-deleted = 🗑 Variable <code>{ $name }</code> deleted.
var-missing = ❌ Variable <code>{ $name }</code> not found.
var-list-empty = ℹ️ Variable list is empty.
var-list-header = 📋 <b>Chat Variables:</b>
var-invalid-key = ❌ Invalid key format. Use only latin letters and <code>_</code>.
var-usage-set = ℹ️ Usage: <code>/setvar &lt;key&gt; &lt;value&gt;</code>
var-usage-delete = ℹ️ Usage: <code>/delvar &lt;key&gt;</code>
welcome-usage =
    ℹ️ Usage:
    <code>/welcome set [timeout]</code> (reply to message)
    <code>/welcome delete</code> - disable
    <code>/welcome test</code> - test
welcome-set-no-reply = ❌ Reply to the message you want to set as welcome.
welcome-invalid-timeout = ❌ Invalid time format. Use seconds (60) or 5m, 1h.
welcome-set-success = ✅ Welcome message set! Auto-delete in { $timeout } sec.
welcome-disabled = ℹ️ Welcome message disabled.
welcome-unset = ❌ Welcome message not set.
settings-captcha-type-emoji = Emoji
settings-captcha-type-webapp = WebApp
gban-user-banned = ⛔️ User { $user } is on the global ban list and has been banned.
gban-user-warning = ⚠️ User { $user } is on the global ban list!

# btn-gban-true = ✅ Global Ban


# btn-gban-false = ❌ Global Ban


# settings-gban = 🌍 Global ban list: { $status }


# moderation-gban-enabled = Global Ban: Enabled


# moderation-gban-disabled = Global Ban: Disabled

moderation-gban-toggle = { $status } Global Ban

# gban-alert-text = 🚨 <b>Global Ban Alert</b>


# gban-ban-button = 🔨 Ban User


# gban-banned-by-admin = User { $user } was banned by admin.

mod-punishment-ban = 🔨 Ban
mod-punishment-mute = 🔇 Mute
mod-punishment-btn = Punishment: { $punishment }
mod-duration-btn = ⏳ Duration: { $duration }
mod-duration-forever = Forever
mod-duration-min = { $count } min.
mod-duration-hour = { $count } h.
mod-duration-day = { $count } d.
mod-duration-week = { $count } w.
mod-duration-tenmin = 10 minutes
mod-duration-onehour = 1 hour
mod-duration-oneday = 1 day
mod-duration-oneweek = 1 week

# mod-duration-select = Select punishment duration:

punishment-ban = Ban
punishment-mute = Mute
warns-none = User has no warnings.
warns-none-user = User { $name } has no warnings.
punishment-duration-select = Select punishment duration:
trigger-validation-error = Template validation error: { $error }
content-type-text = Text
content-type-photo = Photo
content-type-video = Video
content-type-sticker = Sticker
content-type-document = Document
content-type-gif = GIF
content-type-voice = Voice
content-type-audio = Audio
btn-false-alarm = ✅ False Alarm
btn-delete-trigger = 💀 Delete Trigger
btn-ban-chat = ☢️ Ban Chat
btn-moderation-warns = 👮‍♂️ Moderation & Warns
btn-captcha-settings = 🧩 Captcha
btn-triggers-settings = 🎯 Triggers
btn-captcha-timeout = ⏳ Timeout: { $timeout }
settings-captcha-title = 🧩 <b>Captcha Settings</b>
settings-captcha-status = Status: { $status }
settings-captcha-type-label = Type: { $type }
settings-captcha-timeout-label = Timeout: { $timeout }
settings-captcha-timeout-select = ⏳ Select captcha timeout:
settings-triggers-title = 🎯 <b>Trigger Settings</b>
settings-triggers-module = Module: { $status }
settings-triggers-admins = Admins only: { $status }
settings-summary-captcha = 🧩 Captcha: { $status }
settings-summary-moderation = 👮‍♂️ Moderation: { $status }
settings-summary-triggers = 🎯 Triggers: { $status }
captcha-timeout-onemin = 1 minute
captcha-timeout-twomin = 2 minutes
captcha-timeout-fivemin = 5 minutes
captcha-timeout-tenmin = 10 minutes
btn-captcha-attempts = 🎯 Attempts: { $count }
btn-captcha-ban-duration = 🔨 Ban: { $duration }
settings-captcha-attempts-label = Attempts: { $count }
settings-captcha-ban-label = Ban on fail: { $duration }
settings-captcha-ban-select = 🔨 Select ban duration for captcha failure:
captcha-ban-threedays = 3 days

# Reputation & Tags
reputation-group-only = This command only works in group chats.
reputation-disabled = Tag system is not enabled in this chat.
reputation-no-data = No activity data found yet.
reputation-status =
    🏷 <b>Chat Status</b>
    {""}
    Level: <b>{ $level_name }</b> (Lv.{ $level })
    Score: <b>{ $score }</b>
    { $next_info }
    Position: #{ $rank } of { $total }
    {""}
    { $progress_bar } { $progress_pct }%
reputation-next-level = Until next level: { $remaining }
reputation-max-level = Maximum level reached!
tag-usage = Usage: reply to a user's message with /tag &lt;tag text&gt;
tag-invalid = ❌ Tag can only contain letters, digits, spaces, and hyphens.
tag-reply-required = Reply to a user's message to set a tag.
tag-set = ✅ Tag for { $user } set: <b>{ $tag }</b>
tag-cleared = ℹ️ Manual tag for { $user } removed. Automatic tag restored.
btn-tags-true = ✅ Tags
btn-tags-false = ❌ Tags
settings-summary-tags = 🏷 Tags: { $status }
tags-bot-no-admin = Bot must be an administrator to manage tags.
tags-bot-no-permission = Bot doesn't have the "Manage Tags" (can_manage_tags) permission. Grant it in chat settings.
settings-open-webapp = ⚙️ Open Settings
settings-webapp-sent = Press the button below to open chat settings.
settings-no-admin = You are not an administrator of this chat.
settings-chat-missing = Chat not found.
new-trigger-group-entry-body = Trigger creation is done in a private chat with the bot so that the content is not visible to chat members before it fires.
new-trigger-group-entry-button = Create in private messages
new-trigger-lobby-title = Which chat are we creating a trigger for?
new-trigger-lobby-empty = You have no chats where the bot is installed and you are allowed to create triggers.
new-trigger-lobby-page-indicator = { $page }/{ $total }
new-trigger-content-prompt = Chat: { $title }

    Send a message that the bot should reply with when the trigger fires. Any type is supported: text, photo, video, animation, sticker, document, voice.
new-trigger-content-saved = Message saved.
new-trigger-content-command-warning = This looks like a command. Use it as trigger content?
new-trigger-key-prompt = Specify the text the trigger should match on.

    Exact match: «hello»
    Regex: «^(hello|hi)\b»
new-trigger-key-empty = The key cannot be empty.
new-trigger-key-too-long = The key is too long (maximum { $limit } characters).
new-trigger-flags-title = Key: «{ $phrase }»
new-trigger-flags-match-exact = Exact
new-trigger-flags-match-contains = Contains
new-trigger-flags-match-regex = Regex
new-trigger-flags-case-on = Case-sensitive
new-trigger-flags-access-all = All members
new-trigger-flags-access-admins = Admins only
new-trigger-flags-access-owner = Owner only
new-trigger-flags-template = Template ({ "{" }{ "{" } variables { "}" }{ "}" })
new-trigger-flags-regex-invalid = Invalid regex: { $error }
new-trigger-flags-template-invalid = Template error: { $error }
new-trigger-confirm-summary = Trigger response preview.

    Key: «{ $phrase }»
    Type: { $match_type }, { $case_mode }
    Access: { $access }
    Template: { $template }
    Chat: { $chat_title }
new-trigger-confirm-created = Trigger created.
new-trigger-confirm-moderation-pending = The trigger is sent for moderation and will start working after the check.
new-trigger-conflict-body = An unfinished process will be reset. Continue?
new-trigger-conflict-keep = Return to current
new-trigger-permission-denied = You don't have permission to create triggers in this chat.
new-trigger-permission-lost = Your permissions in the chat have changed. Creation cancelled.
new-trigger-cancel-done = Trigger creation cancelled.
new-trigger-send-copy-failed = Failed to send the preview. The file may no longer be available. Please send the content again.
new-trigger-send-copy-retry-after = Telegram asked to wait { $seconds } sec. Please try again.
new-trigger-session-expired = Session expired. Start /newtrigger again.
new-trigger-save-busy = Save is already in progress.
new-trigger-preview-entities-warning = Failed to parse content formatting. Premium emoji and fonts may not display.
new-trigger-content-wrong-type = Expected a content message. Send text, photo, video, GIF, sticker, document or voice.
new-trigger-key-wrong-type = Expected key text. Send a text message.
new-trigger-flags-wrong-input = Use the buttons on this step. Send /cancel to abort.
new-trigger-create-failed = Failed to save the trigger: { $error }. Please try again.
new-trigger-conflict-body-foreign = You have an unfinished action. Reset?
new-trigger-btn-use-this = Use this
new-trigger-btn-send-another = Send another
new-trigger-btn-cancel = ✕ Cancel
new-trigger-btn-next = Next: preview ›
new-trigger-btn-save = ✓ Save
new-trigger-btn-again = Create another in this chat
new-trigger-btn-finish = Finish
new-trigger-btn-back-to-chat = ‹ Change chat
new-trigger-btn-back-to-key = ‹ Edit key
new-trigger-btn-back-to-flags = ‹ Edit parameters
new-trigger-btn-restart = Reset and start over
new-trigger-btn-keep = Return to current
