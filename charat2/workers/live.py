import json

from datetime import datetime
from redis import StrictRedis
from sqlalchemy import and_, func
from sqlalchemy.orm.exc import NoResultFound
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.web import Application
from tornado.websocket import WebSocketHandler
from uuid import uuid4

from charat2.helpers.chat import disconnect, join, KickedException, send_quit_message
from charat2.model import sm, AnyChat, Ban, ChatUser, Message, User
from charat2.model.connections import redis_pool

redis = StrictRedis(connection_pool=redis_pool)


class ChatHandler(WebSocketHandler):

    def get_chat_user(self):
        return self.db.query(
            ChatUser, User, AnyChat,
        ).join(
            User, ChatUser.user_id == User.id,
        ).join(
            AnyChat, ChatUser.chat_id == AnyChat.id,
        ).filter(and_(
            ChatUser.user_id == self.user_id,
            ChatUser.chat_id == self.chat_id,
        )).one()

    def prepare(self):
        self.id = str(uuid4())
        self.joined = False
        try:
            self.session_id = self.cookies["session"].value
            self.chat_id = int(self.path_args[0])
            self.user_id = int(redis.get("session:%s" % self.session_id))
        except (KeyError, TypeError, ValueError):
            self.send_error(400)
            return
        self.db = sm()
        if self.db.query(func.count('*')).select_from(Ban).filter(and_(
            Ban.chat_id == self.chat_id,
            Ban.user_id == self.user_id,
        )).scalar() != 0:
            self.send_error(403)
            return
        try:
            self.chat_user, self.user, self.chat = self.get_chat_user()
        except NoResultFound:
            self.send_error(404)
            return
        self.user.last_online = datetime.now()
        self.user.last_ip = self.request.headers["X-Forwarded-For"]
        if self.user.group == "banned":
            self.send_error(403)
            return

    def open(self, chat_id):
        print "socket opened:", self.id, self.chat.url, self.user.username
        try:
            join(redis, self.db, self)
            self.joined = True
        except KickedException:
            self.send(json.dumps({"exit": "kick"}))
            self.close()
            return
        self.db.commit()

    def on_message(self, message):
        print "message:", message

    def on_close(self):
        if self.joined:
            if disconnect(redis, self.chat_id, self.id):
                try:
                    send_quit_message(self.db, redis, *self.get_chat_user())
                except NoResultFound:
                    send_userlist(self.db, redis, self.chat)
                self.db.commit()
        print "socket closed:", self.id

    def finish(self, *args, **kwargs):
        if hasattr(self, "db"):
            self.db.close()
            del self.db
        super(ChatHandler, self).finish(*args, **kwargs)

if __name__ == "__main__":
    application = Application([(r"/(\d+)", ChatHandler)])
    http_server = HTTPServer(application)
    http_server.listen(8000)
    IOLoop.instance().start()

