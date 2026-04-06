from app.zoho.desk.client import ZohoDeskClient


def get_tickets():
    client = ZohoDeskClient()
    tickets = client.list_tickets()
    for ticket in tickets:
        conversations = client.list_conversations(ticket.id)
        for conversation in conversations:
            thread = client.get_thread(ticket.id, conversation.id)
            print(thread)


if __name__ == '__main__':
    get_tickets()
