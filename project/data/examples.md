# Three published scenario examples

These are actual local simulator observations, generated without model calls. They show inputs and changing information, not a solution or measured agent performance. The read-only walkthrough deliberately makes no bookings and earns no task score.

## public-81988 — basic

Offline tool inspection. Zero model calls; no performance score.

### Initial request

Plan my replacement outbound to Northbridge. The client appointment is at 11:30 today. Extra spending may not exceed USD 245, including the pending USD 55 hotel charge and any nonrefunded change fee. Keep our hotel and my colleague's return ticket; please waive the hotel charge. I prefer a flight if feasible. Stairs are fine and any listed operator is allowed for my outbound. Approval consent-81988 covers my replacement outbound and permitted fare changes under the published contract. This is a stable scenario: no external updates are scheduled. Finish as soon as your confirmed booking and current requirements are verified; the episode horizon is minute 36.

### Sources returned by read tools

#### hotel-terms (version 1)

Read completed at virtual minute 2.

Keep the confirmed room. USD 55 is pending. Read hotel-bulletin for the current evidence and deadline. Claims never cancel the room.

#### transport-guide (version 1)

Read completed at virtual minute 2.

Use these weekday transfers in Northbridge: flight 30 minutes, train 10 minutes, coach 25 minutes. Add the applicable value to terminal arrival. Last month all transfers were 20 minutes; that guide is obsolete. The 45-minute hotel shuttle is not the journey to the client.

#### traveler-profile (version 1)

Read completed at virtual minute 2.

Booking platform operators: Aster, Birch, Cedar. Default for later journeys: flight, all carriers allowed, no access requirement. Current-trip notices override this profile only for this trip. Do not overwrite the colleague booking or infer that another traveler shares a new restriction.

#### hotel-bulletin (version 2)

Read completed at virtual minute 4.

Archive: last year guests submitted type cancel-reference with code proof-0000. That procedure is withdrawn. Current Northbridge booking: submit evidence of type cancel-reference with code proof-81988 before virtual minute 36. Acceptance removes the USD 55 disruption charge while keeping the room. Claims accepted under an earlier version stay accepted.

#### fare-terms (version 1)

Read completed at virtual minute 4.

Each search result states its fare contract. A locked fare cannot be cancelled or exchanged after confirmation. A fee fare can be cancelled with approval: the refund is its paid fare minus cancel_fee_usd. A flexible fare is fully refundable. Cancel an approved replacement before confirming another; preserve the hotel and colleague-return. Nonrefunded amounts count toward extra spending. Search also states when an offer opens and closes; a held offer can be confirmed only while the hold remains valid. These terms do not authorize changing another traveler or the existing room.

### Available offers

Search completed at virtual minute 4.

| ID | Mode | Carrier | USD | Terminal arrival | Step-free | Fare rule | Cancellation fee |
|---|---|---|---:|---|---|---|---:|
| coach-81988-2 | coach | Cedar | 135 | 08:38 | True | flexible | 0 |
| rail-81988-2 | train | Cedar | 150 | 08:35 | True | flexible | 0 |
| air-81988-1 | flight | Birch | 150 | 09:28 | False | fee | 35 |
| air-81988-3 | flight | Aster | 160 | 08:58 | True | locked | 0 |
| coach-81988-4 | coach | Birch | 140 | 08:45 | True | fee | 35 |
| rail-81988-0 | train | Aster | 95 | 10:25 | True | locked | 0 |
| rail-81988-3 | train | Aster | 145 | 08:55 | True | locked | 0 |
| air-81988-4 | flight | Birch | 160 | 08:50 | True | fee | 35 |
| air-81988-0 | flight | Aster | 105 | 10:25 | True | locked | 0 |
| air-81988-2 | flight | Cedar | 155 | 08:35 | True | flexible | 0 |
| coach-81988-3 | coach | Aster | 140 | 09:00 | True | locked | 0 |
| rail-81988-1 | train | Birch | 140 | 09:30 | False | fee | 35 |
| coach-81988-1 | coach | Birch | 125 | 09:30 | False | fee | 35 |
| coach-81988-0 | coach | Aster | 85 | 10:20 | True | locked | 0 |
| rail-81988-4 | train | Birch | 150 | 08:48 | True | fee | 35 |

### Current observation after inspection

```json
{
  "case_id": "public-81988",
  "version": "travel-2026f-v9",
  "virtual_minute": 4,
  "horizon": 36,
  "handoff_minute": 0,
  "revision": 0,
  "tier": "basic",
  "difficulty": "basic",
  "booking_deadline": null,
  "notices": [
    {
      "at": 0,
      "kind": "initial_request",
      "text": "Plan my replacement outbound to Northbridge. The client appointment is at 11:30 today. Extra spending may not exceed USD 245, including the pending USD 55 hotel charge and any nonrefunded change fee. Keep our hotel and my colleague's return ticket; please waive the hotel charge. I prefer a flight if feasible. Stairs are fine and any listed operator is allowed for my outbound. Approval consent-81988 covers my replacement outbound and permitted fare changes under the published contract. This is a stable scenario: no external updates are scheduled. Finish as soon as your confirmed booking and current requirements are verified; the episode horizon is minute 36."
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
      "id": "transport-guide",
      "title": "Weekday transfers in Northbridge",
      "version": 1
    },
    {
      "id": "hotel-terms",
      "title": "Existing room and disruption charge",
      "version": 1
    },
    {
      "id": "hotel-bulletin",
      "title": "Current waiver procedure",
      "version": 2
    },
    {
      "id": "traveler-profile",
      "title": "Durable preferences and scope",
      "version": 1
    },
    {
      "id": "fare-terms",
      "title": "Replacement fare contracts",
      "version": 1
    }
  ],
  "finished": false
}
```

This preview contains only actual observations and tool replies. Inspection actions advance virtual time. Run the solver in a fresh world.


## public-14921 — reactive

Offline tool inspection. Zero model calls; no performance score.

### Initial request

Repair my cancelled outbound to Northbridge for the 11:30 client appointment. Extra spending may not exceed USD 240, including the hotel charge and retained cancellation fees. For this trip I prefer flight when feasible. Stairs are currently fine. All listed operators are currently permitted. Waive the USD 55 hotel charge while preserving the room and companion return. Approval consent-14921 covers my replacement and permitted fare changes. Confirm a first outbound by virtual minute 14; monitor through minute 24 and finish by minute 36. Later spending limits apply to new commitments; previously approved charges remain approved. Further replacement offers remain available through minute 36.

### Sources returned by read tools

#### hotel-terms (version 1)

Read completed at virtual minute 2.

Keep the room. A USD 55 charge is pending. Read hotel-bulletin for the evidence and cutoff.

#### transport-guide (version 1)

Read completed at virtual minute 2.

Terminal-to-client travel in Northbridge: flight 20 minutes, train 25 minutes, coach 30 minutes. Add the relevant transfer to the terminal arrival time.

#### traveler-profile (version 1)

Read completed at virtual minute 2.

Booking platform operators: Aster, Birch, Cedar. The hotel and companion return must stay unchanged.

#### hotel-bulletin (version 2)

Read completed at virtual minute 4.

The room stays reserved. Waive the USD 55 charge by submitting evidence type cancel-reference, code proof-14921, and this source version before virtual minute 18. An accepted claim remains valid after a bulletin revision.

#### fare-terms (version 1)

Read completed at virtual minute 4.

Each search result states its fare contract. A locked fare cannot be cancelled or exchanged after confirmation. A fee fare can be cancelled with approval: the refund is its paid fare minus cancel_fee_usd. A flexible fare is fully refundable. Cancel an approved replacement before confirming another; preserve the hotel and colleague-return. Nonrefunded amounts count toward extra spending. Search also states when an offer opens and closes; a held offer can be confirmed only while the hold remains valid. These terms do not authorize changing another traveler or the existing room.

### Available offers

Search completed at virtual minute 4.

| ID | Mode | Carrier | USD | Terminal arrival | Step-free | Fare rule | Cancellation fee |
|---|---|---|---:|---|---|---|---:|
| offer-14921-4 | train | Aster | 180 | 08:40 | True | flexible | 0 |
| offer-14921-12 | flight | Cedar | 160 | 10:42 | True | flexible | 0 |
| offer-14921-2 | flight | Aster | 150 | 10:40 | False | flexible | 0 |
| offer-14921-9 | train | Birch | 185 | 08:43 | True | flexible | 0 |
| offer-14921-13 | flight | Cedar | 180 | 08:46 | True | flexible | 0 |
| offer-14921-11 | flight | Cedar | 130 | 10:42 | True | fee | 25 |
| offer-14921-10 | flight | Cedar | 100 | 10:42 | True | locked | 0 |
| offer-14921-7 | flight | Birch | 155 | 10:41 | True | flexible | 0 |
| offer-14921-8 | flight | Birch | 185 | 08:43 | True | flexible | 0 |
| offer-14921-6 | flight | Birch | 120 | 10:41 | True | fee | 10 |
| offer-14921-5 | flight | Birch | 95 | 10:41 | True | locked | 0 |
| offer-14921-1 | flight | Aster | 110 | 10:40 | False | fee | 35 |
| offer-14921-0 | flight | Aster | 90 | 10:40 | False | locked | 0 |
| offer-14921-14 | train | Cedar | 180 | 08:46 | True | flexible | 0 |
| offer-14921-3 | flight | Aster | 180 | 08:40 | True | flexible | 0 |

### Current observation after inspection

```json
{
  "case_id": "public-14921",
  "version": "travel-2026f-v9",
  "virtual_minute": 4,
  "horizon": 36,
  "handoff_minute": 24,
  "revision": 0,
  "tier": "reactive",
  "difficulty": "reactive",
  "booking_deadline": 14,
  "notices": [
    {
      "at": 0,
      "kind": "initial_request",
      "text": "Repair my cancelled outbound to Northbridge for the 11:30 client appointment. Extra spending may not exceed USD 240, including the hotel charge and retained cancellation fees. For this trip I prefer flight when feasible. Stairs are currently fine. All listed operators are currently permitted. Waive the USD 55 hotel charge while preserving the room and companion return. Approval consent-14921 covers my replacement and permitted fare changes. Confirm a first outbound by virtual minute 14; monitor through minute 24 and finish by minute 36. Later spending limits apply to new commitments; previously approved charges remain approved. Further replacement offers remain available through minute 36. "
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
      "id": "transport-guide",
      "title": "Current client transfers",
      "version": 1
    },
    {
      "id": "hotel-terms",
      "title": "Existing room and fee",
      "version": 1
    },
    {
      "id": "hotel-bulletin",
      "title": "Current fee-waiver instructions",
      "version": 2
    },
    {
      "id": "traveler-profile",
      "title": "Traveler and trip approval",
      "version": 1
    },
    {
      "id": "fare-terms",
      "title": "Fare and hold terms",
      "version": 1
    }
  ],
  "finished": false
}
```

This preview contains only actual observations and tool replies. Inspection actions advance virtual time. Run the solver in a fresh world.


### Later observations from a separate read-only walkthrough

**Notice delivered at virtual minute 10:** The client appointment is now 09:40. Retain my other conditions.

**Notice delivered at virtual minute 19:** For my outbound, only Cedar is permitted from now on. This replaces the previous carrier list.

## public-15977 — forecast

Offline tool inspection. Zero model calls; no performance score.

### Initial request

Please replace my cancelled outbound to Port Amber; reach the client by 10:00. Extra spending may not exceed USD 215, including the hotel charge and retained cancellation fees. For this trip I prefer rail when feasible. Stairs are currently fine. All listed operators are currently permitted. Keep the room and companion return and remove the room charge. Approval consent-54079 covers my replacement and permitted fare changes. Confirm a first outbound by virtual minute 12; monitor through minute 24 and finish by minute 36. Later spending limits apply to new commitments; previously approved charges remain approved. Backup inventory opens at virtual minute 13 and closes at minute 19; the weather report resolves at minute 23. Alternative-mode backup fares start at USD 175; later preferred-mode services have their own fares and arrival margins. A hold lasts 14 minutes from creation and can be confirmed after inventory closes while the hold remains valid. A forecast may be a false alarm: keep the preferred service when it remains suitable. Read the current weather watch before deciding which service needs a backup.

### Sources returned by read tools

#### hotel-terms (version 1)

Read completed at virtual minute 2.

Keep the room. A USD 55 charge is pending. Read hotel-bulletin for the evidence and cutoff.

#### transport-guide (version 1)

Read completed at virtual minute 2.

Client transfers in Port Amber: add 20 minutes after an air arrival, 20 after a rail arrival, and 20 after a coach arrival. These are onward durations; ticket arrival times do not include them.

#### traveler-profile (version 1)

Read completed at virtual minute 2.

Booking platform operators: Aster, Birch, Cedar. The hotel and companion return must stay unchanged.

#### hotel-bulletin (version 2)

Read completed at virtual minute 4.

For this existing room, send proof-54079 as evidence type disruption-letter before virtual minute 11. Use this bulletin version. Acceptance removes USD 55 and keeps the room. A claim accepted earlier remains accepted.

#### fare-terms (version 1)

Read completed at virtual minute 4.

Each search result states its fare contract. A locked fare cannot be cancelled or exchanged after confirmation. A fee fare can be cancelled with approval: the refund is its paid fare minus cancel_fee_usd. A flexible fare is fully refundable. Cancel an approved replacement before confirming another; preserve the hotel and colleague-return. Nonrefunded amounts count toward extra spending. Search also states when an offer opens and closes; a held offer can be confirmed only while the hold remains valid. These terms do not authorize changing another traveler or the existing room.

#### weather-forecast (version 1)

Read completed at virtual minute 4.

For the lead outbound, the chance of a further 100-minute delay to weather-exposed train services is 45 percent. Other modes and protected services are outside this watch. This is a forecast, not a delay already included in ticket arrivals.

### Available offers

Search completed at virtual minute 6.

| ID | Mode | Carrier | USD | Terminal arrival | Step-free | Fare rule | Cancellation fee |
|---|---|---|---:|---|---|---|---:|
| offer-54079-8 | train | Birch | 265 | 09:02 | True | flexible | 0 |
| offer-54079-1 | train | Aster | 105 | 09:00 | True | fee | 30 |
| offer-54079-6 | train | Birch | 90 | 09:02 | True | locked | 0 |
| offer-54079-13 | train | Cedar | 135 | 09:04 | True | fee | 20 |
| offer-54079-12 | train | Cedar | 95 | 09:04 | True | locked | 0 |
| offer-54079-0 | train | Aster | 85 | 09:00 | True | locked | 0 |
| offer-54079-7 | train | Birch | 120 | 09:02 | True | fee | 10 |
| offer-54079-14 | train | Cedar | 270 | 09:04 | True | flexible | 0 |
| offer-54079-2 | train | Aster | 260 | 09:00 | True | flexible | 0 |

### Current observation after inspection

```json
{
  "case_id": "public-15977",
  "version": "travel-2026f-v9",
  "virtual_minute": 6,
  "horizon": 36,
  "handoff_minute": 24,
  "revision": 0,
  "tier": "forecast",
  "difficulty": "forecast",
  "booking_deadline": 12,
  "notices": [
    {
      "at": 0,
      "kind": "initial_request",
      "text": "Please replace my cancelled outbound to Port Amber; reach the client by 10:00. Extra spending may not exceed USD 215, including the hotel charge and retained cancellation fees. For this trip I prefer rail when feasible. Stairs are currently fine. All listed operators are currently permitted. Keep the room and companion return and remove the room charge. Approval consent-54079 covers my replacement and permitted fare changes. Confirm a first outbound by virtual minute 12; monitor through minute 24 and finish by minute 36. Later spending limits apply to new commitments; previously approved charges remain approved. Backup inventory opens at virtual minute 13 and closes at minute 19; the weather report resolves at minute 23. Alternative-mode backup fares start at USD 175; later preferred-mode services have their own fares and arrival margins. A hold lasts 14 minutes from creation and can be confirmed after inventory closes while the hold remains valid. A forecast may be a false alarm: keep the preferred service when it remains suitable. Read the current weather watch before deciding which service needs a backup. "
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
      "id": "transport-guide",
      "title": "Current client transfers",
      "version": 1
    },
    {
      "id": "hotel-terms",
      "title": "Existing room and fee",
      "version": 1
    },
    {
      "id": "hotel-bulletin",
      "title": "Current fee-waiver instructions",
      "version": 2
    },
    {
      "id": "traveler-profile",
      "title": "Traveler and trip approval",
      "version": 1
    },
    {
      "id": "fare-terms",
      "title": "Fare and hold terms",
      "version": 1
    },
    {
      "id": "weather-forecast",
      "title": "Current outbound weather watch",
      "version": 1
    }
  ],
  "finished": false
}
```

This preview contains only actual observations and tool replies. Inspection actions advance virtual time. Run the solver in a fresh world.


### Later observations from a separate read-only walkthrough

**Notice delivered at virtual minute 8:** Dispatch replaced the lead-outbound weather watch. Read the current source; its mode or likelihood may have changed.

**Read weather-forecast, version 2, completed at minute 10:**

Lead outbound forecast: train risk 70 percent, possible additional delay 100 minutes. Only weather_exposed train services are affected; other modes are unaffected. Do not add this forecast to observed arrivals as if it had already happened.

**Notice delivered at virtual minute 10:** A road closure changed the onward journey. Refresh transport-guide before choosing a backup.

**Read transport-guide, version 2, completed at minute 18:**

Client transfers in Port Amber: add 25 minutes after an air arrival, 20 after a rail arrival, and 70 after a coach arrival. These are onward durations; ticket arrival times do not include them.

**Notice delivered at virtual minute 23:** The current weather watch has resolved. Inspect current booking arrivals; they include the actual delay. A previously held backup may still be usable.

**Read weather-forecast, version 3, completed at minute 26:**

The train disruption occurred: weather-exposed services gained 100 minutes. Current search and booking arrivals already include the actual result. There is no further predicted delay: future risk is zero percent and no mode is under a watch.
