OPTIONAL_PRIVMSG_TAGS = [
        "bits", "reply_parent_msg_id", "reply_parent_user_login",
        "reply_parent_display_name", "reply_parent_msg_body", "vip"]


class TwitchPrivateMessage:
    def __init__(
            self,
            badge_info: dict,           # 'Badge' : 'badge info' pairs
            badges: dict,               # Also 'badge' : 'badge info' pairs
            color: Optional[str],       # User-set name color, if they did
            display_name: str,          # Username including capitalization
            emotes: str,   # FIX THIS   # Character range : image name pairs
            first_msg: bool,            # Is this a first-time chatter?
            message_id: str,            # No clue how this is used
            mod: bool,                  # Is a moderator (not broadcaster)?
            returning_chatter: bool,    # Is this a second-time chatter?
            room_id: int,               # No clue how this is used
            subscriber: bool,           # Is user a channel subscriber?
            tmi_sent_ts: int, #FIX THIS # Message timestamp
            turbo: bool,                # Is user paying for Twitch Turbo?
            user_id: int,               # Backend ID for sender
            user_type: str,             # "", "admin", "global_mod", "staff"
            vip: bool,                  # Is user a VIP in this channel?
            channel: str,               # Twitch chat message was sent to
            message_body: str,          # The body text of the message
            bits: int = None,           # The amount of bits cheered w/ msg
            reply_parent_msg_id: str = None, # The message replied to
            reply_parent_user_login: str = None, # Login username of replied
            reply_parent_display_name: str = None, # Shown name of replied
            reply_parent_msg_body: str = None # Message text replied to
            ) -> None:
        self.badge_info = badge_info
        self.badges = badges
        self.color = color
        self.display_name = display_name
        self.emotes = emotes
        self.first_msg = first_msg
        self.message_id = message_id
        self.mod = mod
        self.returning_chatter = returning_chatter
        self.room_id = room_id
        self.subscriber = subscriber
        self.tmi_sent_ts = tmi_sent_ts
        self.turbo = turbo
        self.user_id = user_id
        self.user_type = user_type
        self.vip = vip
        self.channel = channel
        self.message_body = message_body
        self.bits = bits
        self.reply_parent_msg_id = reply_parent_msg_id
        self.reply_parent_user_login = reply_parent_user_login
        self.reply_parent_display_name = reply_parent_display_name
        self.reply_parent_msg_body = reply_parent_msg_body


def create_private_message_object_from(
        twitch_irc_message: TwitchIRCMessage) -> PrivateMessageEvent:
    tags = twitch_irc_message.tags
    for optional_tag in OPTIONAL_PRIVMSG_TAGS:
        if optional_tag not in tags:
            tags[optional_tag] = None
    badge_info = irc_badge_pairs_to_dict(tags["badge-info"])
    badges = irc_badge_pairs_to_dict(tags["badges"])
    color = tags["color"] if tags["color"] else None
    display_name = tags["display-name"]
    emotes = tags["emotes"]
    first_msg = bool(int(tags["first-msg"]))
    message_id = tags["id"]
    mod = bool(int(tags["mod"]))
    returning_chatter = bool(int(tags["returning-chatter"]))
    room_id = int(tags["room-id"])
    subscriber = bool(int(tags["subscriber"]))
    # CONVERT THIS TO DATETIME
    tmi_sent_ts = int(tags["tmi-sent-ts"])
    turbo = bool(int(tags["turbo"]))
    user_id = int(tags["user-id"])
    user_type = tags["user-type"]
    channel = twitch_irc_message.parameters[0][1:]
    message_body = twitch_irc_message.parameters[1]
    bits = int(tags["bits"]) if tags["bits"] is not None else None
    reply_parent_msg_id = tags["reply_parent_msg_id"]
    reply_parent_user_login = tags["reply_parent_user_login"]
    reply_parent_display_name = tags["reply_parent_display_name"]
    reply_parent_msg_body = tags["reply_parent_msg_body"]
    vip = bool(int(tags["vip"])) if tags["vip"] is not None else None
    return PrivateMessage(
            badge_info, badges, color, display_name, emotes, first_msg,
            message_id, mod, returning_chatter, room_id, subscriber,
            tmi_sent_ts, turbo, user_id, user_type, vip, channel,
            message_body, bits, reply_parent_msg_id,
            reply_parent_user_login, reply_parent_display_name,
            reply_parent_msg_body)


def irc_badge_pairs_to_dict(raw_badge_str: str) -> dict:
    badge_pair_strings = raw_badge_str.split(",")
    badges = {}
    for pair_str in badge_pair_strings:
        pair = pair_str.split("/")
        if pair[0]:
            badges[pair[0]] = pair[1]
    return badges
