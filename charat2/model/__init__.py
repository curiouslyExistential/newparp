import datetime
import json
import os
import time

from sqlalchemy import create_engine
from sqlalchemy.schema import Index
from sqlalchemy.orm import (
    relation,
    scoped_session,
    sessionmaker,
    with_polymorphic,
)
# Sorry SQLiters, this just ain't gonna work.
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import (
    func,
    Column,
    ForeignKey,
    Boolean,
    DateTime,
    Enum,
    Integer,
    String,
    Unicode,
    UnicodeText,
    UniqueConstraint,
)

engine = create_engine(
    os.environ['POSTGRES_URL'],
    convert_unicode=True,
    pool_recycle=3600,echo=True,
)

sm = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

base_session = scoped_session(sm)

Base = declarative_base()
Base.query = base_session.query_property()

def now():
    return datetime.datetime.now()

case_options = {
    u"alt-lines": "ALTERNATING lines",
    u"alternating": "AlTeRnAtInG",
    u"inverted": "iNVERTED",
    u"lower": u"lower case",
    u"normal": u"Normal",
    u"title": u"Title Case",
    u"upper": u"UPPER CASE",
}

case_options_enum = Enum(*case_options.keys(), name=u"case")


class User(Base):

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)

    # Username must be alphanumeric.
    username = Column(String(50))

    # Bcrypt hash.
    password = Column(String(60), nullable=False)

    group = Column(Enum(
        u"guest",
        u"active",
        u"admin",
        u"banned",
        name=u"users_group",
    ), nullable=False, default=u"guest")

    created = Column(DateTime(), nullable=False, default=now)
    last_online = Column(DateTime(), nullable=False, default=now)

    default_character_id = Column(Integer, ForeignKey(
        "user_characters.id",
        name="users_default_character_fkey",
        use_alter=True,
    ))

    search_tags = Column(ARRAY(String(100)), nullable=False, default=lambda: [])
    search_exclude_tags = Column(ARRAY(String(100)), nullable=False, default=lambda: [])

    confirm_disconnect = Column(Boolean, nullable=False, default=False)
    show_system_messages = Column(Boolean, nullable=False, default=True)
    show_description = Column(Boolean, nullable=False, default=True)
    show_bbcode = Column(Boolean, nullable=False, default=True)
    desktop_notifications = Column(Boolean, nullable=False, default=False)


class UserCharacter(Base):

    __tablename__ = "user_characters"

    id = Column(Integer, primary_key=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(Unicode(50), nullable=False)

    name = Column(Unicode(50), nullable=False, default=u"Anonymous")
    acronym = Column(Unicode(15), nullable=False, default=u"??")

    # Must be a hex code.
    color = Column(Unicode(6), nullable=False, default=u"000000")

    quirk_prefix = Column(Unicode(50), nullable=False, default=u"")
    quirk_suffix = Column(Unicode(50), nullable=False, default=u"")

    case = Column(case_options_enum, nullable=False, default=u"normal")

    replacements = Column(UnicodeText, nullable=False, default=u"[]")
    regexes = Column(UnicodeText, nullable=False, default=u"[]")

    def to_dict(self, include_options=False):
        ucd = {
            "id": self.id,
            "title": self.title,
            "name": self.name,
            "acronym": self.acronym,
            "color": self.color,
        }
        if include_options:
            ucd["quirk_prefix"] = self.quirk_prefix
            ucd["quirk_suffix"] = self.quirk_suffix
            ucd["case"] = self.case
            ucd["replacements"] = json.loads(self.replacements)
            ucd["regexes"] = json.loads(self.regexes)
        return ucd


class Chat(Base):

    __tablename__ = "chats"
    __mapper_args__ = { "polymorphic_on": "type" }

    id = Column(Integer, primary_key=True)

    # URL must be alphanumeric. It must normally be capped to 50 characters,
    # but sub-chats are prefixed with the parent URL and a slash, so we need
    # 101 characters to fit 50 characters in each half.
    url = Column(String(101), unique=True)

    # Group chats allow people to enter in accordance with the publicity
    # options in the group_chats table, and can have any URL.
    # PM chats only allow two people to enter and have urls of the form
    # `pm/<user id 1>/<user id 2>`, with the 2 user IDs in alphabetical
    # order.
    # Searched chats allow anyone to enter and have randomly generated URLs.
    type = Column(Enum(
        u"group",
        u"pm",
        u"searched",
        name=u"chats_type",
    ), nullable=False, default=u"group")

    created = Column(DateTime(), nullable=False, default=now)

    # Last message time should only update when users send messages, not system
    # messages.
    last_message = Column(DateTime(), nullable=False, default=now)

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.type,
        }


class GroupChat(Chat):

    __tablename__ = "group_chats"

    id = Column(Integer, ForeignKey("chats.id"), primary_key=True)

    __mapper_args__ = {
        "polymorphic_identity": "group",
        "inherit_condition": id==Chat.id,
    }

    title = Column(Unicode(50), nullable=False, default=u"")
    topic = Column(UnicodeText, nullable=False, default=u"")

    autosilence = Column(Boolean, nullable=False, default=False)
    nsfw = Column(Boolean, nullable=False, default=False)

    publicity = Column(Enum(
        u"listed",
        u"unlisted",
        name=u"group_chats_publicity",
    ), nullable=False, default=u"unlisted")

    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("chats.id"))

    def to_dict(self):
        return {
            "id": self.id,
            "url": self.url,
            "type": self.type,
            "title": self.title,
            "topic": self.topic,
            "autosilence": self.autosilence,
            "nsfw": self.nsfw,
            "publicity": self.publicity,
        }


class PMChat(Chat):
    __mapper_args__ = { "polymorphic_identity": "pm" }


class SearchedChat(Chat):

    __mapper_args__ = { "polymorphic_identity": "searched" }

    def to_dict(self):
        return {
            "id": self.id,
            "url": self.url,
            "type": self.type,
        }


AnyChat = with_polymorphic(Chat, [GroupChat, PMChat, SearchedChat])


class ChatUser(Base):

    __tablename__ = "chat_users"

    chat_id = Column(Integer, ForeignKey("chats.id"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)

    last_online = Column(DateTime(), nullable=False, default=now)

    # Ignored if the user is an admin or the chat's creator.
    group = Column(Enum(
        u"mod",
        u"mod2",
        u"mod3",
        u"silent",
        u"user",
        name=u"chat_users_group",
    ), nullable=False, default=u"user")

    name = Column(Unicode(50), nullable=False, default=u"Anonymous")
    acronym = Column(Unicode(15), nullable=False, default=u"??")

    # Must be a hex code.
    color = Column(Unicode(6), nullable=False, default=u"000000")

    quirk_prefix = Column(Unicode(50), nullable=False, default=u"")
    quirk_suffix = Column(Unicode(50), nullable=False, default=u"")

    case = Column(case_options_enum, nullable=False, default=u"normal")

    replacements = Column(UnicodeText, nullable=False, default=u"[]")
    regexes = Column(UnicodeText, nullable=False, default=u"[]")

    confirm_disconnect = Column(Boolean, nullable=False, default=False)
    show_system_messages = Column(Boolean, nullable=False, default=True)
    show_description = Column(Boolean, nullable=False, default=True)
    show_bbcode = Column(Boolean, nullable=False, default=True)
    desktop_notifications = Column(Boolean, nullable=False, default=False)

    @classmethod
    def from_character(cls, character, **kwargs):
        # Create a ChatUser using a Character and their user to determine the
        # default values.
        return cls(
            user_id=character.user.id,
            name=character.name,
            acronym=character.acronym,
            color=character.color,
            quirk_prefix=character.quirk_prefix,
            quirk_suffix=character.quirk_suffix,
            case=character.case,
            replacements=character.replacements,
            regexes=character.regexes,
            confirm_disconnect=character.user.confirm_disconnect,
            show_system_messages=character.user.show_system_messages,
            show_description=character.user.show_description,
            show_bbcode=character.user.show_bbcode,
            desktop_notifications=character.user.desktop_notifications,
            **kwargs
        )

    @classmethod
    def from_user(cls, user, **kwargs):
        # Create a ChatUser using a User and their default character to
        # determine the default values.
        if user.default_character is None:
            return cls(
                user_id=user.id,
                confirm_disconnect=user.confirm_disconnect,
                show_system_messages=user.show_system_messages,
                show_description=user.show_description,
                show_bbcode=user.show_bbcode,
                desktop_notifications=user.desktop_notifications,
                **kwargs
            )
        dc = user.default_character
        return cls(
            user_id=user.id,
            name=dc.name,
            acronym=dc.acronym,
            color=dc.color,
            quirk_prefix=dc.quirk_prefix,
            quirk_suffix=dc.quirk_suffix,
            case=dc.case,
            replacements=dc.replacements,
            regexes=dc.regexes,
            confirm_disconnect=user.confirm_disconnect,
            show_system_messages=user.show_system_messages,
            show_description=user.show_description,
            show_bbcode=user.show_bbcode,
            desktop_notifications=user.desktop_notifications,
            **kwargs
        )

    # Group changes and user actions can only be performed on people of the
    # same group as yourself and lower. To make this easier to check, we store
    # a numeric value for each rank so we can do a simple less-than-or-equal-to
    # comparison.
    group_ranks = {
        "admin": float("inf"),
        "creator": float("inf"),
        "mod": 3,
        "mod2": 2,
        "mod3": 1,
        "user": 0,
        "silent": -1,
    }

    # Minimum ranks for actions.
    action_ranks = {
        "ban": 3,
        "kick": 2,
        # XXX different ranks for each flag?
        "set_flag": 1,
        "set_group": 1,
        "set_topic": 1,
    }

    @property
    def computed_group(self):
        # Group is overridden by chat creator and user status.
        # Needs joinedload whenever we're getting these.
        if self.user.group == "admin":
            return "admin"
        if self.chat.type=="group" and self.chat.creator==self.user:
            return "creator"
        return self.group

    @property
    def computed_rank(self):
        return self.group_ranks[self.computed_group]

    def can(self, action):
        return self.group_ranks[self.computed_group] >= self.action_ranks[action]

    def to_dict(self, include_user=True, include_options=False):
        ucd = {
            "character": {
                "name": self.name,
                "acronym": self.acronym,
                "color": self.color,
            },
            "meta": {
                # Group is overridden by chat creator and user status.
                # Needs joinedload whenever we're getting these.
                "group": self.computed_group,
            },
        }
        if include_options:
            ucd["character"]["quirk_prefix"] = self.quirk_prefix
            ucd["character"]["quirk_suffix"] = self.quirk_suffix
            ucd["character"]["case"] = self.case
            ucd["character"]["replacements"] = json.loads(self.replacements)
            ucd["character"]["regexes"] = json.loads(self.regexes)
            ucd["meta"]["confirm_disconnect"] = self.confirm_disconnect
            ucd["meta"]["show_system_messages"] = self.show_system_messages
            ucd["meta"]["show_description"] = self.show_description
            ucd["meta"]["show_bbcode"] = self.show_bbcode
            ucd["meta"]["desktop_notifications"] = self.desktop_notifications
        if include_user:
            ucd["meta"]["user_id"] = self.user.id
            ucd["meta"]["username"] = self.user.username
        return ucd


class Message(Base):

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)

    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=False)

    # Can be null because system messages aren't associated with a user.
    user_id = Column(Integer, ForeignKey("users.id"))

    posted = Column(DateTime(), nullable=False, default=now)

    # XXX CONSIDER SPLITTING SYSTEM INTO USER_CHANGE, META_CHANGE ETC.
    type = Column(Enum(
        u"ic",
        u"ooc",
        u"me",
        u"join",
        u"disconnect",
        u"timeout",
        u"user_info",
        u"user_group",
        u"user_action",
        u"chat_meta",
        u"search_info",
        name=u"messages_type",
    ), nullable=False, default=u"ic")

    # Must be a hex code.
    color = Column(Unicode(6), nullable=False, default=u"000000")

    acronym = Column(Unicode(15), nullable=False, default=u"")

    name = Column(Unicode(50), nullable=False, default=u"")

    text = Column(UnicodeText, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "user": {
                "id": self.user.id,
                "username": self.user.username,
            } if self.user is not None else None,
            "posted": time.mktime(self.posted.timetuple()),
            "type": self.type,
            "color": self.color,
            "acronym": self.acronym,
            "name": self.name,
            "text": self.text,
        }


class Ban(Base):

    __tablename__ = "bans"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), primary_key=True)

    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created = Column(DateTime(), nullable=False, default=now)
    expires = Column(DateTime())

    name = Column(Unicode(50), nullable=False)
    acronym = Column(Unicode(15), nullable=False)

    reason = Column(UnicodeText)


# Index to make usernames case insensitively unique.
Index("users_username", func.lower(User.username), unique=True)

# Index for user characters.
Index("user_characters_user_id", UserCharacter.user_id)

# Index to make generating the public chat list easier.
# This is a partial index, a feature only supported by Postgres, so I don't
# know what will happen if you try to run this on anything else.
Index(
    "group_chats_publicity_listed",
    GroupChat.publicity,
    postgresql_where=GroupChat.publicity==u"listed",
)

# Index for your chats list.
Index("chat_users_user_id_chat_id", ChatUser.user_id, ChatUser.chat_id)

# Index to make log rendering easier.
Index("messages_chat_id", Message.chat_id, Message.posted)


User.default_character = relation(
    UserCharacter,
    primaryjoin=User.default_character_id==UserCharacter.id,
)
User.characters = relation(
    UserCharacter,
    primaryjoin=User.id==UserCharacter.user_id,
    backref="user",
)

GroupChat.creator = relation(User, backref='created_chats')
GroupChat.parent = relation(
    Chat,
    backref='children',
    primaryjoin=GroupChat.parent_id==Chat.id,
)

ChatUser.user = relation(User, backref='chats')
ChatUser.chat = relation(Chat, backref='users')

Message.chat = relation(Chat)
Message.user = relation(User)

Ban.user = relation(
    User,
    backref='bans',
    primaryjoin=Ban.user_id==User.id,
)
Ban.chat = relation(Chat, backref='bans')
Ban.creator = relation(
    User,
    backref='bans_created',
    primaryjoin=Ban.creator_id==User.id,
)

