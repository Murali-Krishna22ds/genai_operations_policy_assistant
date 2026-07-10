"""
Live case context (part of Objectives 3 & 4): looks up a ticket/order/customer
and follows the documented joins:
  customers.csv <-(customer_id)-> orders.csv <-(order_id)-> returns.csv
  support_tickets.csv references customer_id and (optionally) order_id

Returns a flat dict merged from whichever records are found, plus the routed
policy department derived from the ticket's category (Objective 4).
"""
from functools import lru_cache
from typing import Optional
import pandas as pd

from app import config


@lru_cache(maxsize=1)
def _load_tables():
    customers = pd.read_csv(config.CUSTOMERS_CSV, dtype=str)
    orders = pd.read_csv(config.ORDERS_CSV, dtype=str)
    returns = pd.read_csv(config.RETURNS_CSV, dtype=str)
    tickets = pd.read_csv(config.TICKETS_CSV, dtype=str)
    return customers, orders, returns, tickets


def get_case_context(ticket_id: Optional[str] = None,
                      order_id: Optional[str] = None,
                      customer_id: Optional[str] = None) -> dict:
    customers, orders, returns, tickets = _load_tables()
    context = {}
    routed_department = None

    if ticket_id:
        row = tickets[tickets["ticket_id"] == ticket_id]
        if not row.empty:
            ticket = row.iloc[0].to_dict()
            context["ticket"] = ticket
            order_id = order_id or (ticket.get("order_id") or None)
            customer_id = customer_id or ticket.get("customer_id")
            routed_department = config.TICKET_TO_POLICY_CATEGORY.get(
                ticket.get("category", ""), ticket.get("category")
            )

    if order_id:
        row = orders[orders["order_id"] == order_id]
        if not row.empty:
            order = row.iloc[0].to_dict()
            context["order"] = order
            customer_id = customer_id or order.get("customer_id")
            ret_row = returns[returns["order_id"] == order_id]
            if not ret_row.empty:
                context["return"] = ret_row.iloc[0].to_dict()

    if customer_id:
        row = customers[customers["customer_id"] == customer_id]
        if not row.empty:
            context["customer"] = row.iloc[0].to_dict()

    context["routed_policy_department"] = routed_department
    return context
