from typing import Optional, Literal

from pydantic import BaseModel, Field

from app.agent.base import BaseAgent
from app.constants import SupportedModels

Intent = Literal['order_status', 'support']


class TicketIntent(BaseModel):
    email: Optional[str] = Field(default=None)
    phone: Optional[str] = Field(default=None)
    name: Optional[str] = Field(default=None)
    intent: Intent
    order_id: Optional[str] = Field(default=None)


instructions = (
    """
    You will help classify incoming Zoho Desk support tickets for a website called Gameday Social. 
    
    About Gameday Social: 
    
    "Gameday Social offers elevated collegiate and lifestyle apparel, expertly designed by women for women. 
    The brand provides a diverse range of clothing options, including tops, outerwear, and bottoms. 
    The collection features team logos and custom branded apparel for various organizations, with wholesale purchasing available."
    
    You will receive some context about the ticket, any associated contact info like email or phone, the subject and ticket content.
    
    You will then categorize the ticket according to intent:
        -order_status: the customer wants to know the status of their order, you need to respond with the order ID
        -support: any other tickets should go to a support agent
    
    Note the order Id is required for order_status tickets, otherwise it is ignored. 
    
    You will also find any additional contact info that might be in the ticket body like name, email or phone, if there are any. 
    """
)


class IntentClassifier(BaseAgent):
    def __init__(self):
        super().__init__(instructions, SupportedModels.GPT_5_MINI, TicketIntent)

    def classify(self, subject: str, content: str) -> TicketIntent:
        prompt = f"Subject: {subject}\n\nContent:\n{content}"
        return self.parse([prompt])
