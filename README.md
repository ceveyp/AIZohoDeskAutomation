# AI Support Automation for Zoho Desk (FastAPI and LLM Agents)

FastAPI service that receives Zoho Desk ticket webhooks and processes each ticket in the background using agents. LangChain agents apply tags and classify intent (order status, product inquiry, or general support), then specialized agents pull live data from Apparel Magic, Shopify, and an internal product-search API to post public replies on the ticket when possible. Ambiguous tickets are handed-off to human support reps. 
