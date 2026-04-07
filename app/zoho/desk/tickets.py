import validators

from app.apparel_magic.client import ApparelMagicClient
from app.logger import setup_logging, get_logger
from app.zoho.desk.client import ZohoDeskClient
from app.zoho.desk.intent_classifier import IntentClassifier

logger = get_logger(__name__)


def get_tickets():
    from pprint import pprint
    shopify_mailer_email = 'mailer@shopify.com'
    client = ZohoDeskClient()
    am_client = ApparelMagicClient()
    intent_classifier = IntentClassifier()
    logger.debug("Fetching tickets")
    tickets = client.list_tickets()
    for ticket in tickets:
        likely_client_name = None
        likely_client_email = None
        likely_client_phone = None
        if ticket.isArchived or ticket.isSpam:
            logger.debug(f"Ticket is archive or spam, skipping: {ticket.subject}")
            continue
        if not ticket.status == 'Open':
            logger.debug(f"Ticket status is {ticket.status}, skipping: {ticket.subject}")
            continue
        is_shopify = (ticket.email and ticket.email == shopify_mailer_email)
        if not ticket.email == shopify_mailer_email:
            logger.debug(f"Likely email found: {ticket.email}")
            likely_client_email = ticket.email
        logger.debug(f"Fetching conversations")
        conversations = client.list_conversations(ticket.id)
        for conversation in conversations:
            if conversation.direction and not conversation.direction == 'in':
                logger.debug(f"Skipping because conversation direction is out: {ticket.subject}")
                continue
            if conversation.author:
                if not conversation.author.email == shopify_mailer_email:
                    likely_client_email = conversation.author.email
                    fist_name = conversation.author.firstName or ""
                    last_name = conversation.author.lastName or ""
                    likely_client_name = f"{fist_name} {last_name}".strip()
            logger.debug(f"Fetching thread: {ticket.subject}")
            thread = client.get_thread(ticket.id, conversation.id)
            if not thread.content:
                logger.debug(f"Skipping because thread content is empty: {ticket.subject}")
                continue
            if thread.replyTo and validators.email(thread.replyTo):
                likely_client_email = thread.replyTo
            logger.debug(f"Fetching ticket intent: {ticket.subject}")
            intent = intent_classifier.classify(ticket.subject, thread.content)
            logger.debug(f"Ticket intent fetched: {intent}")
            if intent.name:
                likely_client_name = intent.name
            if intent.email:
                likely_client_email = intent.email
            if intent.phone:
                likely_client_phone = intent.phone

            if not likely_client_email:
                logger.debug(f"Likely client email not found: {ticket.subject}")
                continue

            # Search for AM customer
            am_customer = am_client.get_customer_by_email(likely_client_email)
            if am_customer:
                logger.info(f"AM customer found: {likely_client_email}")
            else:
                logger.debug(f"AM customer not found, skipping: {likely_client_email}")
                continue

            # Handle order status queries
            if intent.intent == 'order_status':
                order = None
                logger.info(f"Ticket is an order status query: {ticket.subject}")
                if intent.order_id:
                    order = am_client.get_order_by_id(intent.order_id)
                    if not order:
                        logger.warn(f"Order {intent.order_id} not found for customer {likely_client_email}")
                        continue
                else:
                    order = am_client.get_orders_by_customer_id(am_customer.customer_id)
                    if not order:
                        logger.warn(f"No orders found for customer {likely_client_email}")
                        continue
                if order:


            print("-------------------------------------------------")
            print(f"Likely client email: {likely_client_email}")
            print(f"Likely client name: {likely_client_name}")
            print(f"Likely client phone: {likely_client_phone}")
            print(f"Intent: {intent.intent}")
            print(f"Order ID: {intent.order_id}")
            print("Ticket: \n")
            pprint(ticket.model_dump())
            print("\nConversation: \n")
            pprint(conversation.model_dump())
            print("\nThread: \n")
            pprint(thread.model_dump())
            print("-------------------------------------------------")


if __name__ == '__main__':
    setup_logging()
    get_tickets()
