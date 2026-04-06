from datetime import datetime
from typing import Optional

from pydantic import Field, BaseModel


class Ticket(BaseModel):
    id: str
    ticketNumber: str
    subject: str
    email: Optional[str] = Field(default=None)
    contactId: str
    channel: str
    isSpam: bool
    isArchived: bool
    status: str
    createdTime: datetime


class Author(BaseModel):
    id: str
    email: Optional[str] = Field(default=None)
    firstName: Optional[str] = Field(default=None)
    lastName: Optional[str] = Field(default=None)


class ConversationSource(BaseModel):
    appName: Optional[str] = Field(default=None)
    type: str


class Conversation(BaseModel):
    id: str
    author: Optional[Author] = Field(default=None)
    channel: Optional[str] = Field(default=None)
    direction: Optional[str] = Field(default=None)
    to: Optional[str] = Field(default=None)
    fromEmailAddress: Optional[str] = Field(default=None)
    source: Optional[ConversationSource] = Field(default=None)


class Thread(BaseModel):
    id: str
    content: str
    channel: Optional[str] = Field(default=None)
    canReply: Optional[bool] = Field(default=None)
    replyTo: Optional[str] = Field(default=None)
    direction: Optional[str] = Field(default=None)
