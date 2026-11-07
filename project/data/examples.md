# Three published scenario examples

These are local simulator observations made without model calls. They show the request, source catalog and available offers; they are not agent performance measurements or completed travel plans.

## travel-7be0e09bbe903f5ab848 — basic

### Initial observation

```json
{
  "case_id": "travel-7be0e09bbe903f5ab848",
  "version": "travel-2026f-v10",
  "virtual_minute": 0,
  "horizon": 36,
  "handoff_minute": 12,
  "revision": 0,
  "tier": "basic",
  "difficulty": "basic",
  "booking_deadline": 12,
  "notices": [
    {
      "at": 0,
      "kind": "initial_request",
      "text": "Repair my cancelled outbound to Port Amber. Prefer flight whenever a suitable flight is affordable. I require step-free travel. Do not use Cedar. All other listed carriers are permitted. Keep the existing hotel and my colleague's return unchanged, and claim the hotel charge waiver. Approval consent-e4dd6ad15c34 covers my outbound and its permitted cancellation, subject to the spending conditions in request-contract. Read arrival-contract for the binding arrival obligation, transport-guide for transfers, and fare-contract for actual cancellation refunds. A first confirmed replacement is required by virtual minute 12. Verify the booking before handing it over at or after minute 12. Clock times and arrival minutes refer to local time after midnight; virtual minutes measure elapsed tool time. Spending authorization is checked when a charged action completes. A later lower allowance does not revoke an earlier authorized payment."
    }
  ],
  "bookings": [
    {
      "id": "original-outbound",
      "status": "cancelled",
      "traveler": "lead",
      "kind": "transport",
      "price": 0
    },
    {
      "id": "hotel",
      "status": "confirmed",
      "traveler": "lead",
      "kind": "hotel",
      "price": 0
    },
    {
      "id": "colleague-return",
      "status": "confirmed",
      "traveler": "colleague",
      "kind": "return",
      "price": 0
    }
  ],
  "holds": [],
  "hotel_fee": 55,
  "net_transport_spend_usd": 0,
  "transport_payments_usd": 0,
  "transport_refunds_usd": 0,
  "retained_cancel_fees_usd": 0,
  "transport_ledger": [],
  "source_catalog": [
    {
      "id": "arrival-contract",
      "title": "Current client arrival obligation",
      "version": 1
    },
    {
      "id": "fare-contract",
      "title": "Cancellation charges and exceptions",
      "version": 1
    },
    {
      "id": "hotel-terms",
      "title": "Existing hotel charge",
      "version": 1
    },
    {
      "id": "request-contract",
      "title": "Current spending approval",
      "version": 1
    },
    {
      "id": "transport-guide",
      "title": "Current client transfer",
      "version": 1
    },
    {
      "id": "traveler-profile",
      "title": "Lead outbound preferences",
      "version": 1
    }
  ],
  "finished": false,
  "operational_contract_revision": "operational-travel-20261106",
  "operational_sources": {
    "budget_limit": {
      "id": "request-contract",
      "version": 1
    },
    "arrival_deadline": {
      "id": "arrival-contract",
      "version": 1
    }
  },
  "uncredited_hold_deposits_usd": 0,
  "retained_hold_fees_usd": 0,
  "total_retained_loss_usd": 0
}
```

### Search result

The search completes at virtual minute 2. No reservation is made.

```json
{
  "ok": true,
  "options": [
    {
      "arrival_minute": 621,
      "available_from": 0,
      "cancel_fee_usd": 55,
      "carrier": "Birch",
      "change_policy": "fee",
      "comfort": 3,
      "connection": "direct",
      "expires_at": 36,
      "hold_fee_usd": 0,
      "id": "trip-4b5059bcb43",
      "mode": "flight",
      "price": 113,
      "step_free": true,
      "weather_exposed": false,
      "refund_contract_source": {
        "id": "fare-contract",
        "version": 1
      },
      "fare_fields_scope": "base terms; the linked conditional refund contract takes precedence"
    },
    {
      "arrival_minute": 600,
      "available_from": 0,
      "cancel_fee_usd": 55,
      "carrier": "Birch",
      "change_policy": "fee",
      "comfort": 3,
      "connection": "direct",
      "expires_at": 36,
      "hold_fee_usd": 0,
      "id": "trip-ce49d7ac73a",
      "mode": "flight",
      "price": 140,
      "step_free": true,
      "weather_exposed": false,
      "refund_contract_source": {
        "id": "fare-contract",
        "version": 1
      },
      "fare_fields_scope": "base terms; the linked conditional refund contract takes precedence"
    },
    {
      "arrival_minute": 670,
      "available_from": 0,
      "cancel_fee_usd": 55,
      "carrier": "Birch",
      "change_policy": "fee",
      "comfort": 3,
      "connection": "direct",
      "expires_at": 36,
      "hold_fee_usd": 0,
      "id": "trip-8f593c994f4",
      "mode": "coach",
      "price": 95,
      "step_free": true,
      "weather_exposed": false,
      "refund_contract_source": {
        "id": "fare-contract",
        "version": 1
      },
      "fare_fields_scope": "base terms; the linked conditional refund contract takes precedence"
    },
    {
      "arrival_minute": 620,
      "available_from": 0,
      "cancel_fee_usd": 55,
      "carrier": "Cedar",
      "change_policy": "fee",
      "comfort": 3,
      "connection": "direct",
      "expires_at": 36,
      "hold_fee_usd": 0,
      "id": "trip-b5b9ac42d1f",
      "mode": "flight",
      "price": 110,
      "step_free": true,
      "weather_exposed": false,
      "refund_contract_source": {
        "id": "fare-contract",
        "version": 1
      },
      "fare_fields_scope": "base terms; the linked conditional refund contract takes precedence"
    },
    {
      "arrival_minute": 610,
      "available_from": 0,
      "cancel_fee_usd": 55,
      "carrier": "Birch",
      "change_policy": "fee",
      "comfort": 3,
      "connection": "direct",
      "expires_at": 36,
      "hold_fee_usd": 0,
      "id": "trip-063741aa5be",
      "mode": "flight",
      "price": 90,
      "step_free": false,
      "weather_exposed": false,
      "refund_contract_source": {
        "id": "fare-contract",
        "version": 1
      },
      "fare_fields_scope": "base terms; the linked conditional refund contract takes precedence"
    },
    {
      "arrival_minute": 610,
      "available_from": 0,
      "cancel_fee_usd": 55,
      "carrier": "Birch",
      "change_policy": "fee",
      "comfort": 3,
      "connection": "direct",
      "expires_at": 36,
      "hold_fee_usd": 0,
      "id": "trip-aaefab5e354",
      "mode": "train",
      "price": 180,
      "step_free": true,
      "weather_exposed": false,
      "refund_contract_source": {
        "id": "fare-contract",
        "version": 1
      },
      "fare_fields_scope": "base terms; the linked conditional refund contract takes precedence"
    }
  ],
  "observed_at": 2,
  "note": "Terminal arrival is not always meeting arrival. Read transport-guide. Search is not a reservation."
}
```

## travel-7b1558c214cd1bd41e92 — reactive

### Initial observation

```json
{
  "case_id": "travel-7b1558c214cd1bd41e92",
  "version": "travel-2026f-v10",
  "virtual_minute": 0,
  "horizon": 36,
  "handoff_minute": 28,
  "revision": 0,
  "tier": "reactive",
  "difficulty": "reactive",
  "booking_deadline": 12,
  "notices": [
    {
      "at": 0,
      "kind": "initial_request",
      "text": "Repair my cancelled outbound to Port Amber. Prefer flight whenever a suitable flight is affordable. I require step-free travel. All listed carriers are permitted. Keep the existing hotel and my colleague's return unchanged, and claim the hotel charge waiver. Approval consent-dd66fc4550e7 covers my outbound and its permitted cancellation, subject to the spending conditions in request-contract. Read arrival-contract for the binding arrival obligation, transport-guide for transfers, and fare-contract for actual cancellation refunds. A first confirmed replacement is required by virtual minute 12. I may send partial changes later. Keep checking current notices through minute 28 and finish by minute 36. Clock times and arrival minutes refer to local time after midnight; virtual minutes measure elapsed tool time. Spending authorization is checked when a charged action completes. A later lower allowance does not revoke an earlier authorized payment."
    }
  ],
  "bookings": [
    {
      "id": "original-outbound",
      "status": "cancelled",
      "traveler": "lead",
      "kind": "transport",
      "price": 0
    },
    {
      "id": "hotel",
      "status": "confirmed",
      "traveler": "lead",
      "kind": "hotel",
      "price": 0
    },
    {
      "id": "colleague-return",
      "status": "confirmed",
      "traveler": "colleague",
      "kind": "return",
      "price": 0
    }
  ],
  "holds": [],
  "hotel_fee": 55,
  "net_transport_spend_usd": 0,
  "transport_payments_usd": 0,
  "transport_refunds_usd": 0,
  "retained_cancel_fees_usd": 0,
  "transport_ledger": [],
  "source_catalog": [
    {
      "id": "arrival-contract",
      "title": "Current client arrival obligation",
      "version": 1
    },
    {
      "id": "fare-contract",
      "title": "Cancellation charges and exceptions",
      "version": 1
    },
    {
      "id": "hotel-terms",
      "title": "Existing hotel charge",
      "version": 1
    },
    {
      "id": "request-contract",
      "title": "Current spending approval",
      "version": 1
    },
    {
      "id": "transport-guide",
      "title": "Current client transfer",
      "version": 1
    },
    {
      "id": "traveler-profile",
      "title": "Lead outbound preferences",
      "version": 1
    }
  ],
  "finished": false,
  "operational_contract_revision": "operational-travel-20261106",
  "operational_sources": {
    "budget_limit": {
      "id": "request-contract",
      "version": 1
    },
    "arrival_deadline": {
      "id": "arrival-contract",
      "version": 1
    }
  },
  "uncredited_hold_deposits_usd": 0,
  "retained_hold_fees_usd": 0,
  "total_retained_loss_usd": 0
}
```

### Search result

The search completes at virtual minute 2. No reservation is made.

```json
{
  "ok": true,
  "options": [
    {
      "arrival_minute": 650,
      "available_from": 0,
      "cancel_fee_usd": 55,
      "carrier": "Aster",
      "change_policy": "fee",
      "comfort": 3,
      "connection": "direct",
      "expires_at": 36,
      "hold_fee_usd": 0,
      "id": "trip-eb98af1cff2",
      "mode": "flight",
      "price": 141,
      "step_free": true,
      "weather_exposed": false,
      "refund_contract_source": {
        "id": "fare-contract",
        "version": 1
      },
      "fare_fields_scope": "base terms; the linked conditional refund contract takes precedence"
    },
    {
      "arrival_minute": 660,
      "available_from": 0,
      "cancel_fee_usd": 55,
      "carrier": "Aster",
      "change_policy": "fee",
      "comfort": 3,
      "connection": "direct",
      "expires_at": 36,
      "hold_fee_usd": 0,
      "id": "trip-e587b8aef56",
      "mode": "flight",
      "price": 115,
      "step_free": true,
      "weather_exposed": false,
      "refund_contract_source": {
        "id": "fare-contract",
        "version": 1
      },
      "fare_fields_scope": "base terms; the linked conditional refund contract takes precedence"
    },
    {
      "arrival_minute": 660,
      "available_from": 0,
      "cancel_fee_usd": 55,
      "carrier": "Birch",
      "change_policy": "fee",
      "comfort": 3,
      "connection": "direct",
      "expires_at": 36,
      "hold_fee_usd": 0,
      "id": "trip-c7cbf449e0d",
      "mode": "train",
      "price": 145,
      "step_free": true,
      "weather_exposed": false,
      "refund_contract_source": {
        "id": "fare-contract",
        "version": 1
      },
      "fare_fields_scope": "base terms; the linked conditional refund contract takes precedence"
    }
  ],
  "observed_at": 2,
  "note": "Terminal arrival is not always meeting arrival. Read transport-guide. Search is not a reservation."
}
```

## travel-9f7c83790326d2761f54 — forecast

### Initial observation

```json
{
  "case_id": "travel-9f7c83790326d2761f54",
  "version": "travel-2026f-v10",
  "virtual_minute": 0,
  "horizon": 36,
  "handoff_minute": 28,
  "revision": 0,
  "tier": "forecast",
  "difficulty": "forecast",
  "booking_deadline": 12,
  "notices": [
    {
      "at": 0,
      "kind": "initial_request",
      "text": "Repair my cancelled outbound to Port Amber. Prefer flight whenever a suitable flight is affordable. I require step-free travel. All listed carriers are permitted. Keep the existing hotel and my colleague's return unchanged, and claim the hotel charge waiver. Approval consent-877ebd33faf1 covers my outbound and its permitted cancellation, subject to the spending conditions in request-contract. Read arrival-contract for the binding arrival obligation, transport-guide for transfers, and fare-contract for actual cancellation refunds. A first confirmed replacement is required by virtual minute 12. I may send partial changes later. Keep checking current notices through minute 28 and finish by minute 36. Read weather-forecast before the recovery sales close. The announced risk is uncertain; a later operating notice will report what actually happened. Clock times and arrival minutes refer to local time after midnight; virtual minutes measure elapsed tool time. Spending authorization is checked when a charged action completes. A later lower allowance does not revoke an earlier authorized payment."
    }
  ],
  "bookings": [
    {
      "id": "original-outbound",
      "status": "cancelled",
      "traveler": "lead",
      "kind": "transport",
      "price": 0
    },
    {
      "id": "hotel",
      "status": "confirmed",
      "traveler": "lead",
      "kind": "hotel",
      "price": 0
    },
    {
      "id": "colleague-return",
      "status": "confirmed",
      "traveler": "colleague",
      "kind": "return",
      "price": 0
    }
  ],
  "holds": [],
  "hotel_fee": 55,
  "net_transport_spend_usd": 0,
  "transport_payments_usd": 0,
  "transport_refunds_usd": 0,
  "retained_cancel_fees_usd": 0,
  "transport_ledger": [],
  "source_catalog": [
    {
      "id": "arrival-contract",
      "title": "Current client arrival obligation",
      "version": 1
    },
    {
      "id": "fare-contract",
      "title": "Cancellation charges and exceptions",
      "version": 1
    },
    {
      "id": "hotel-terms",
      "title": "Existing hotel charge",
      "version": 1
    },
    {
      "id": "request-contract",
      "title": "Current spending approval",
      "version": 1
    },
    {
      "id": "transport-guide",
      "title": "Current client transfer",
      "version": 1
    },
    {
      "id": "traveler-profile",
      "title": "Lead outbound preferences",
      "version": 1
    },
    {
      "id": "weather-forecast",
      "title": "Current disruption outlook",
      "version": 1
    }
  ],
  "finished": false,
  "operational_contract_revision": "operational-travel-20261106",
  "operational_sources": {
    "budget_limit": {
      "id": "request-contract",
      "version": 1
    },
    "arrival_deadline": {
      "id": "arrival-contract",
      "version": 1
    }
  },
  "uncredited_hold_deposits_usd": 0,
  "retained_hold_fees_usd": 0,
  "total_retained_loss_usd": 0
}
```

### Search result

The search completes at virtual minute 2. No reservation is made.

```json
{
  "ok": true,
  "options": [
    {
      "arrival_minute": 620,
      "available_from": 0,
      "cancel_fee_usd": 55,
      "carrier": "Birch",
      "change_policy": "fee",
      "comfort": 3,
      "connection": "direct",
      "expires_at": 36,
      "hold_fee_usd": 0,
      "id": "trip-68d71324bd6",
      "mode": "flight",
      "price": 115,
      "step_free": true,
      "weather_exposed": true,
      "refund_contract_source": {
        "id": "fare-contract",
        "version": 1
      },
      "fare_fields_scope": "base terms; the linked conditional refund contract takes precedence"
    },
    {
      "arrival_minute": 610,
      "available_from": 0,
      "cancel_fee_usd": 55,
      "carrier": "Birch",
      "change_policy": "fee",
      "comfort": 3,
      "connection": "direct",
      "expires_at": 14,
      "hold_fee_usd": 15,
      "id": "trip-cb04709b960",
      "mode": "flight",
      "price": 180,
      "step_free": true,
      "weather_exposed": false,
      "refund_contract_source": {
        "id": "fare-contract",
        "version": 1
      },
      "fare_fields_scope": "base terms; the linked conditional refund contract takes precedence"
    },
    {
      "arrival_minute": 660,
      "available_from": 0,
      "cancel_fee_usd": 55,
      "carrier": "Birch",
      "change_policy": "fee",
      "comfort": 3,
      "connection": "direct",
      "expires_at": 36,
      "hold_fee_usd": 0,
      "id": "trip-1e20b5ac3a5",
      "mode": "coach",
      "price": 145,
      "step_free": true,
      "weather_exposed": false,
      "refund_contract_source": {
        "id": "fare-contract",
        "version": 1
      },
      "fare_fields_scope": "base terms; the linked conditional refund contract takes precedence"
    },
    {
      "arrival_minute": 630,
      "available_from": 0,
      "cancel_fee_usd": 55,
      "carrier": "Birch",
      "change_policy": "fee",
      "comfort": 3,
      "connection": "direct",
      "expires_at": 36,
      "hold_fee_usd": 0,
      "id": "trip-bd23a7ac090",
      "mode": "flight",
      "price": 145,
      "step_free": true,
      "weather_exposed": true,
      "refund_contract_source": {
        "id": "fare-contract",
        "version": 1
      },
      "fare_fields_scope": "base terms; the linked conditional refund contract takes precedence"
    },
    {
      "arrival_minute": 600,
      "available_from": 0,
      "cancel_fee_usd": 55,
      "carrier": "Birch",
      "change_policy": "fee",
      "comfort": 3,
      "connection": "direct",
      "expires_at": 14,
      "hold_fee_usd": 20,
      "id": "trip-13413b91c3f",
      "mode": "flight",
      "price": 230,
      "step_free": true,
      "weather_exposed": false,
      "refund_contract_source": {
        "id": "fare-contract",
        "version": 1
      },
      "fare_fields_scope": "base terms; the linked conditional refund contract takes precedence"
    },
    {
      "arrival_minute": 660,
      "available_from": 0,
      "cancel_fee_usd": 55,
      "carrier": "Birch",
      "change_policy": "fee",
      "comfort": 3,
      "connection": "direct",
      "expires_at": 36,
      "hold_fee_usd": 0,
      "id": "trip-fb1ec55fd52",
      "mode": "train",
      "price": 115,
      "step_free": true,
      "weather_exposed": false,
      "refund_contract_source": {
        "id": "fare-contract",
        "version": 1
      },
      "fare_fields_scope": "base terms; the linked conditional refund contract takes precedence"
    }
  ],
  "observed_at": 2,
  "note": "Terminal arrival is not always meeting arrival. Read transport-guide. Search is not a reservation."
}
```
