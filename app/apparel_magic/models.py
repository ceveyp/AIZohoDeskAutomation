from pydantic import BaseModel, Field
from typing import List, Optional


class Person(BaseModel):
    id: Optional[str] = None
    customer_id: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    position: Optional[str] = None
    phone: Optional[str] = None
    fax: Optional[str] = None
    email: Optional[str] = None
    is_main_contact: Optional[str] = "0"


class Customer(BaseModel):
    # Identity & Basic Info
    customer_id: Optional[str] = None
    account_number: Optional[str] = None
    customer_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    active: Optional[bool] = None
    is_active: Optional[str] = "1"

    # Contact & Address
    address_1: Optional[str] = None
    address_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    phone: Optional[str] = None
    fax: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None

    # Financials & Logistics
    terms_id: Optional[str] = None
    credit_limit: Optional[float] = None
    credit_usage: Optional[str] = "0.00"
    credit_usage_home: Optional[str] = "0.00"
    pct_discount: Optional[float] = None
    currency_id: Optional[str] = None
    currency_name: Optional[str] = None
    tax_id: Optional[str] = None
    tax_resale_cert: Optional[str] = None
    resale_certificate: Optional[str] = None

    # Internal IDs & Syncing
    division_id: Optional[str] = None
    warehouse_id: Optional[str] = None
    ar_acct: Optional[str] = None
    customer_credit_acct: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None

    # External Integrations
    quickbooks_id: Optional[str] = None
    quickbooks_sync_status: Optional[str] = None
    quickbooks_sync_message: Optional[str] = None
    quickbooks_sync_datetime: Optional[str] = None
    xero_id: Optional[str] = None
    xero_synced: Optional[str] = "0"
    shopify_id: Optional[str] = None
    anet_id: Optional[str] = None
    joor_synced: Optional[str] = "0"
    joor_customer_code: Optional[str] = None

    # Shipping
    shipping_info: Optional[str] = None
    shipping_terms_id: Optional[str] = None
    ship_via: Optional[str] = None
    packing_rules_id: Optional[str] = None
    allocation_strategy_id: Optional[str] = None

    # Metadata & Auditing
    priority: Optional[str] = None
    priority_text: Optional[str] = None
    notes: Optional[str] = None
    private_notes: Optional[str] = None
    last_modified_time: Optional[str] = None
    last_modified_command: Optional[str] = None
    last_modified_user_id: Optional[str] = None
    last_modified_user_name: Optional[str] = None
    creation_time: Optional[str] = None
    creation_user_id: Optional[str] = None
    creation_user_name: Optional[str] = None
    ref_table: Optional[str] = "customers"

    # Nested Data (Defaults to empty lists to avoid None errors)
    salespeople: List[dict] = Field(default_factory=list)
    people: List[Person] = Field(default_factory=list)
    locations: List[dict] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    buyer_filters: List[dict] = Field(default_factory=list)

    # Miscellaneous / Catch-all
    buyer_filter: Optional[str] = None
    edi_department: Optional[str] = None
    factor_account_number: Optional[str] = None
    price_group: Optional[str] = None
    price_group_retail: Optional[str] = None
    retailer_code: Optional[str] = None
    clc_channel: Optional[str] = None
    bc_channel: Optional[str] = None
    af_channel: Optional[str] = None
    edi_vendor_number: Optional[str] = None
    send_updates_special_offers: Optional[str] = None
    store_type: Optional[str] = None

    class Config:
        # This allows the model to accept extra fields without crashing
        extra = "ignore"


from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional


class OrderItem(BaseModel):
    id: Optional[str] = None
    row_id: Optional[str] = None
    sku_id: Optional[str] = None
    product_id: Optional[str] = None
    style_number: Optional[str] = None
    description: Optional[str] = None
    size: Optional[str] = None
    attr_2: Optional[str] = None  # Color
    attr_3: Optional[str] = None
    upc: Optional[str] = None
    qty: Optional[str] = "0.00"
    unit_price: Optional[float] = 0.0
    amount: Optional[float] = 0.0
    is_taxable: Optional[str] = "1"
    # Foreign currency fields
    foreign_unit_price: Optional[str] = None
    foreign_amount: Optional[str] = None


class Order(BaseModel):
    # Setup model to ignore extra fields and allow population by name/alias
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    # Identification
    order_id: Optional[str] = None
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    account_number: Optional[str] = None
    customer_po: Optional[str] = None
    warehouse_id: Optional[str] = None
    division_id: Optional[str] = None
    division_name: Optional[str] = None

    # Dates
    date: Optional[str] = None
    date_internal: Optional[str] = None
    date_start: Optional[str] = None
    date_due: Optional[str] = None
    last_modified_time: Optional[str] = None

    # Quantities (Source uses strings for these)
    qty: Optional[str] = "0.00"
    qty_open: Optional[str] = "0.00"
    qty_shipped: Optional[str] = "0.00"
    qty_alloc_status: Optional[str] = "none"

    # Financials (Source uses actual numbers for these)
    amount: Optional[float] = 0.0
    amount_subtotal: Optional[float] = 0.0
    amount_tax_total: Optional[float] = 0.0
    amount_freight: Optional[float] = 0.0
    balance: Optional[float] = 0.0
    currency_id: Optional[str] = None
    currency_name: Optional[str] = None
    tax_rate: Optional[str] = "0"

    # Shipping & Address
    ship_to_id: Optional[str] = None
    address_1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    ship_via: Optional[str] = None
    shipping_terms_id: Optional[str] = None
    fulfillment_status: Optional[str] = None

    # Status & Flags
    credit_status: Optional[str] = None
    wms_status: Optional[str] = None
    is_open: Optional[str] = "1"
    is_quote: Optional[str] = "0"
    priority_text: Optional[str] = "Medium"

    # Nested Data
    order_items: List[OrderItem] = Field(default_factory=list)
    commissions: List[dict] = Field(default_factory=list)
    misc_charges: List[dict] = Field(default_factory=list)

    # Special Fields
    print_url: Optional[str] = None
    # Use an alias if the source field name is awkward
    cancel_date: Optional[str] = Field(default=None, alias="cancel_date_")
    tax_resale_cert: Optional[str] = None
