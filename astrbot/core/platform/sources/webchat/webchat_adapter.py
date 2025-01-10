import time
import asyncio
import uuid
import os
from typing import Awaitable, Any
from astrbot.api.platform import Platform, AstrBotMessage, MessageMember, MessageType, PlatformMetadata
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain, Image  # noqa: F403
from astrbot.api import logger
from astrbot.core import web_chat_queue, web_chat_back_queue
from .webchat_event import WebChatMessageEvent
from astrbot.core.platform.astr_message_event import MessageSesion
from ...register import register_platform_adapter

class QueueListener:
    def __init__(self, queue: asyncio.Queue, callback: callable) -> None:
        self.queue = queue
        self.callback = callback
        
    async def run(self):
        while True:
            data = await self.queue.get()
            await self.callback(data)

@register_platform_adapter("webchat", "webchat")
class WebChatAdapter(Platform):
    def __init__(self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue) -> None:
        super().__init__(event_queue)
        
        self.config = platform_config
        self.settings = platform_settings
        self.unique_session = platform_settings['unique_session']
        self.imgs_dir = "data/webchat/imgs"

        self.metadata = PlatformMetadata(
            "webchat",
            "webchat",
        )
        
    async def send_by_session(self, session: MessageSesion, message_chain: MessageChain):
        plain = ""
        for comp in message_chain.chain:
            if isinstance(comp, Plain):
                plain += comp.text
        web_chat_back_queue.put_nowait(plain)
        
        await super().send_by_session(session, message_chain)
        
    async def convert_message(self, data: tuple) -> AstrBotMessage:
        username, cid, payload = data
        
        
        abm = AstrBotMessage()
        abm.self_id = "webchat"
        abm.tag = "webchat"
        abm.sender = MessageMember(username, username)        

        abm.type = MessageType.FRIEND_MESSAGE
        
        abm.session_id = f"webchat!{username}!{cid}"
        
        abm.message_id = str(uuid.uuid4())
        abm.message = []
        
        if payload['message']:
            abm.message.append(Plain(payload['message']))
        if payload['image_url']:
            if isinstance(payload['image_url'], list):
                for img in payload['image_url']:
                    abm.message.append(Image.fromFileSystem(os.path.join(self.imgs_dir, img)))
            else:
                abm.message.append(Image.fromFileSystem(os.path.join(self.imgs_dir, payload['image_url'])))
            
        logger.debug(f"WebChatAdapter: {abm.message}")
        
        message_str = payload['message']
        abm.timestamp = int(time.time())
        abm.message_str = message_str
        abm.raw_message = data
        return abm
    
    def run(self) -> Awaitable[Any]:
        async def callback(data: tuple):
            abm = await self.convert_message(data)
            await self.handle_msg(abm)
            
        bot = QueueListener(web_chat_queue, callback)
        return bot.run()
    
    def meta(self) -> PlatformMetadata:
        return self.metadata

    async def handle_msg(self, message: AstrBotMessage):
        
        message_event = WebChatMessageEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id
        )
        
        self.commit_event(message_event)