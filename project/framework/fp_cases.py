"""Published fictional scenarios for travel planning and replanning."""
import hashlib
import json
import random

FP_VERSION = 'travel-2026f-v10'
FP_TIERS = ('basic', 'reactive', 'forecast')
FP_FAMILIES = ('meeting_update', 'budget_update', 'temporary_preference',
               'conditional_waiver', 'quote_expiry', 'confirmation_interruption',
               'transfer_update', 'traveler_scope')
FP_SCORE_VERSION = "travel-score-2026f-v3-100"
FP_GRADING_COST_BASIS = "uncached_token_rates"
FP_OUTCOME_POINTS = dict(arrival=40, requests=20, fee_waiver=10, safety=10, reliability=10)
FP_OUTCOME_MAX = sum(FP_OUTCOME_POINTS.values())
FP_EFFICIENCY_MAX = 10
FP_SCORE_MAX = FP_OUTCOME_MAX + FP_EFFICIENCY_MAX


def fp_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def transfer_text(transfers, city, variant=0):
    f,t,c = (transfers[k] for k in ('flight','train','coach'))
    if variant % 2:
        return (f'Current transfers for {city}: a flight arrival still needs {f} minutes to the client; '
                f'rail passengers should allow {t} minutes after arrival, and coach passengers {c}. '
                'These are additional minutes, not clock times. The archived 20-minute blanket '
                'allowance below is withdrawn. Weekend excursion transfers do not apply to this business trip.')
    return (f'Use these weekday transfers in {city}: flight {f} minutes, train {t} minutes, '
            f'coach {c} minutes. Add the applicable value to terminal arrival. '
            'Last month all transfers were 20 minutes; that guide is obsolete. '
            'The 45-minute hotel shuttle is not the journey to the client.')


def waiver_text(category, code, deadline, city, variant=0):
    if variant % 2:
        return (f'The cancelled reservation in {city} keeps its room. For that booking, attach '
                f'a {category} marked {code}. We need it before virtual minute {deadline}. '
                'An automatic waiver is not available. A disruption-letter marked proof-0000 '
                'was used in an unrelated example; it is not evidence for this claim. '
                'Use the version number of this source, not the example number.')
    return (f'Archive: last year guests submitted type cancel-reference with code proof-0000. '
            f'That procedure is withdrawn. Current {city} booking: submit evidence of type '
            f'{category} with code {code} before virtual minute {deadline}. '
            'Acceptance removes the USD 55 disruption charge while keeping the room. '
            'Claims accepted under an earlier version stay accepted.')


def make_travel_case(seed, family, variant=0, split='dev', numeric_variation=True):
    if family not in FP_FAMILIES:
        raise ValueError('Unknown travel situation.')
    rng = random.Random(seed)
    suffix = str(rng.randrange(10000,99999))
    city = rng.choice(('Luma City','Port Amber','Northbridge'))
    carriers = ('Aster','Birch','Cedar')
    budget = rng.choice((245,265,285)) if numeric_variation else 265
    deadline = 690 if variant%2==0 else 705
    transfers = dict(zip(('flight','train','coach'),rng.choice(((15,25,35),(30,10,25),(10,35,20)))))
    consent = 'consent-'+suffix
    requires_step_free = bool(variant%2)
    avoided = ['Birch'] if variant%2 else []
    preferred = 'flight' if variant%2==0 else 'train'
    options=[]
    for mode,stem in (('flight','air'),('train','rail'),('coach','coach')):
        for j,(arrival,price) in enumerate(((620,95),(565,135),(515,145),(535,145),(525,145))):
            options.append(dict(id=f'{stem}-{suffix}-{j}',mode=mode,
                price=price+(10 if mode=='flight' else -10 if mode=='coach' else 0)+rng.choice((0,5)),
                arrival_minute=arrival+rng.choice((0,3,5)),
                carrier=carriers[j%3],step_free=j in (0,2,3,4),comfort=2+j,
                inventory=2,expires_at=36,connection='terminal'))
    rng.shuffle(options)
    category = 'cancel-reference' if variant%2==0 else 'disruption-letter'
    proof='proof-'+suffix
    event_rng=random.Random(seed ^ 82631)
    waiver_deadline=event_rng.choice((11,18,24))
    final_update_at=event_rng.choice((18,22))
    if variant%2:
        request=(f'My outbound to {city} has been cancelled. Keep our existing hotel and my '
            f"colleague's return ticket. The client needs me by {deadline//60:02d}:{deadline%60:02d}; "
            f'USD {budget} is the ceiling for extra transport plus the USD 55 hotel charge. '
            'Please get that charge waived. I favor rail for this journey. I need step-free '
            'travel from now until handoff, and Birch is excluded for my replacement only. '
            'My colleague is still flying Birch; leave that reservation alone. '
            f'Approval {consent} authorizes my replacement outbound and refundable exchanges.')
    else:
        request=(f'Repair my cancelled outbound to {city}. The client meeting is at 11:30. '
            f'Spend no more than USD {budget} extra including the hotel disruption fee. '
            'Waive that fee, keep the room, and preserve the colleague-return reservation. '
            'I prefer a flight if feasible. Stairs are fine and no carrier is excluded. '
            f'Approval {consent} covers only my replacement outbound and refundable exchanges.')
    request += (' Confirm a first replacement outbound by virtual minute 14; '
                'later approved exchanges remain permitted. Monitor changes through '
                'virtual minute 24, then finish by minute 36. '
                'A budget reduction applies to new commitments; previous approved charges remain valid. '
                'The hotel and colleague booking are never covered by outbound approval.')
    documents={
        'transport-guide':dict(id='transport-guide',title=f'Weekday transfers in {city}',version=1,
            text=transfer_text(transfers,city,variant),related=[]),
        'hotel-terms':dict(id='hotel-terms',title='Existing room and disruption charge',version=1,
            text='Keep the confirmed room. USD 55 is pending. Read hotel-bulletin for the current evidence and deadline. Claims never cancel the room.',related=['hotel-bulletin']),
        'hotel-bulletin':dict(id='hotel-bulletin',title='Current waiver procedure',version=2,
            text=waiver_text(category,proof,waiver_deadline,city,variant),related=[]),
        'traveler-profile':dict(id='traveler-profile',title='Durable preferences and scope',version=1,
            text='Booking platform operators: Aster, Birch, Cedar. Default for later journeys: flight, all carriers allowed, no access requirement. Current-trip notices override this profile only for this trip. Do not overwrite the colleague booking or infer that another traveler shares a new restriction.',related=[])}
    events=[]
    def event(at,kind,text,**changes):events.append(dict(at=at,kind=kind,text=text,changes=changes))
    if family=='meeting_update':
        event(8,'user_update','The client has advanced our meeting to 09:30 today. The hotel check-in stays at 12:00. Exchange any replacement that cannot get me to the client in time.',deadline=570)
    elif family=='budget_update':
        event(8,'user_update','Finance now allows only USD 155 for any new commitment. Already confirmed charges remain approved. Tomorrow’s USD 400 allowance cannot be used today.',budget=155)
    elif family=='temporary_preference':
        mode='train' if preferred=='flight' else 'coach'
        event(8,'user_update',f'For this journey only I now prefer {mode}. Exchange the replacement if a feasible {mode} option exists. Next month I still prefer flying.',preferred=mode)
    elif family=='conditional_waiver':
        replacement='disruption-letter' if category=='cancel-reference' else 'cancel-reference'
        event(6,'document_update','The hotel revised hotel-bulletin. New claims need the current procedure; claims already accepted remain accepted.',waiver=replacement,waiver_version=3,
            document_text=waiver_text(replacement,proof,waiver_deadline,city,1-variant%2))
    elif family=='quote_expiry':
        target=next(o['id'] for o in options if o['mode']==preferred and o['carrier']=='Aster' and 530<=o['arrival_minute']<550)
        event(8,'stock_update',f'A competing buyer will take unheld inventory for {target} at virtual minute 12. A valid hold protects seats.')
        event(12,'sellout',f'Unheld inventory for {target} has sold out.',option_id=target)
    elif family=='confirmation_interruption':
        event(8,'provider_notice','Missing confirmation replies may follow a committed booking. Inspect the request key before booking again.')
    elif family=='transfer_update':
        revised=dict(flight=60,train=35,coach=40)
        event(9,'transport_update','A road closure changed the journey to the client. Re-read transport-guide. Airport and station arrival times themselves have not changed.',transfer=revised,
            document_text=transfer_text(revised,city,1-variant%2))
    else:
        event(8,'user_update','For my replacement outbound only, use step-free access and exclude Aster. These restrictions also apply to your already booked replacement; exchange it if needed. Do not change my colleague’s Aster return.',requires_step_free=True,avoid_carriers=['Aster'])
    # Every case combines an initial scope distinction with a later independent update.
    # The secondary update is announced in the same observable way as the primary one.
    if family not in ('traveler_scope','temporary_preference'):
        allowed='Aster' if family=='quote_expiry' else rng.choice(carriers)
        excluded=[x for x in carriers if x!=allowed]
        text=(f'For this outbound only, do not use {excluded[0]} or {excluded[1]}. '
              f'{allowed} is permitted again if it was previously excluded. The client now needs me by 10:00. '
              'Keep access needs unchanged; the colleague’s existing return is unaffected.')
        if variant%2:
            text=(f'From now on, {allowed} is the only permitted operator for my replacement outbound. '
                  'This replaces every earlier carrier exclusion for my outbound; it does not authorize changing my colleague’s return. '
                  'The client now needs me by 10:00. Keep my access requirements unchanged.')
        event(final_update_at,'user_update',text,avoid_carriers=excluded,deadline=600)
    else:
        event(final_update_at,'user_update','The client changed the appointment to 10:00. The 11:45 lunch is optional and is not the arrival deadline. All other current-trip conditions still apply.',deadline=600)
    for option in options:
        option.update(change_policy='flexible', cancel_fee_usd=0,
                      weather_exposed=False, available_from=0)
    return dict(version=FP_VERSION,case_id=f'{split}-{suffix}',seed=seed,family=family,variant=variant,
        difficulty='reactive',
        city=city,initial_request=request,consent=consent,budget=budget,deadline=deadline,preferred=preferred,
        requires_step_free=requires_step_free,avoid_carriers=avoided,transfer=transfers,
        hold_minutes=9 if family=='quote_expiry' else 14,interrupt_confirmation=family=='confirmation_interruption',
        waiver_type=category,waiver_code=proof,waiver_deadline=waiver_deadline,
        documents=documents,options=options,events=sorted(events,key=lambda e:e['at']),
        booking_deadline=14,handoff_minute=24,horizon=36)


def fare_terms_text():
    return ('Each search result states its fare contract. A locked fare cannot be '
            'cancelled or exchanged after confirmation. A fee fare can be cancelled '
            'with approval: the refund is its paid fare minus cancel_fee_usd. A '
            'flexible fare is fully refundable. Cancel an approved replacement '
            'before confirming another; preserve the hotel and colleague-return. '
            'Nonrefunded amounts count toward extra spending. Search also states '
            'when an offer opens and closes; a held offer can be confirmed only '
            'while the hold remains valid. These terms do not authorize changing '
            'another traveler or the existing room.')


def make_basic_case(seed, variant=0, split='dev'):
    """Stable external circumstances; booking operations still change local state."""
    c = make_travel_case(seed, FP_FAMILIES[variant % len(FP_FAMILIES)], variant, split)
    c.update(family='stable_planning', difficulty='basic', events=[],
             handoff_minute=0, interrupt_confirmation=False, waiver_deadline=36,
             deadline=690, hold_minutes=14)
    c.pop('booking_deadline', None)
    mode = 'rail' if c['preferred'] == 'train' else 'a flight'
    access = ('I need step-free travel. Birch must not carry my replacement outbound; '
              'my colleague may still use Birch.' if c['requires_step_free'] else
              'Stairs are fine and any listed operator is allowed for my outbound.')
    c['initial_request'] = (
        f"Plan my replacement outbound to {c['city']}. The client appointment is at "
        f"11:30 today. Extra spending may not exceed USD {c['budget']}, including "
        'the pending USD 55 hotel charge and any nonrefunded change fee. Keep our '
        "hotel and my colleague's return ticket; please waive the hotel charge. "
        f'I prefer {mode} if feasible. {access} '
        f"Approval {c['consent']} covers my replacement outbound and permitted fare "
        'changes under the published contract. This is a stable scenario: no '
        'external updates are scheduled. Finish as soon as your confirmed booking '
        'and current requirements are verified; the episode horizon is minute 36.')
    c['documents']['hotel-bulletin']['text'] = waiver_text(
        c['waiver_type'], c['waiver_code'], c['waiver_deadline'], c['city'], variant)
    c['documents']['fare-terms'] = dict(id='fare-terms', title='Replacement fare contracts',
                                       version=1, text=fare_terms_text(), related=[])
    for option in c['options']:
        term = ('locked', 'fee', 'flexible')[int(option['id'].rsplit('-', 1)[1]) % 3]
        option.update(change_policy=term, cancel_fee_usd=35 if term == 'fee' else 0)
    return c


def forecast_text(risk, city, variant=0, observed=False, storm=False,
                  mode='flight', delay=120):
    """Current scoped evidence, distinct from an already observed physical delay."""
    label = dict(flight='flight', train='rail', coach='coach')[mode]
    if observed:
        return (f'Operations report for the lead current outbound to {city}: '
                + (f'weather-exposed {mode} services have now acquired {delay} extra '
                   'minutes beyond their original terminal arrivals. ' if storm else
                   f'The predicted {mode} disruption did not materialize; no extra '
                   'arrival minutes were added. ')
                + 'This observed result is already included in current search and '
                'booking arrivals. Do not add it again. Other transport modes are '
                'unaffected by this weather report. There is no further predicted '
                'change: future additional risk is zero percent, additional delay '
                'is zero, and no mode is under a future watch. Check the current '
                'trip restrictions and transfer guide before any permitted repair.')
    if variant % 2:
        return (f'Lead-traveler current outbound watch for {city}: there is a {risk} '
                f'percent chance of the {label} leg acquiring another {delay} minutes '
                'before handoff. This warning applies only to weather_exposed '
                f'{mode} offers for this journey. Other modes are outside this '
                'watch. A companion weekend forecast mentioned 80 percent; ignore '
                'that different traveler and journey. The possible extra duration '
                'is not the appointment clock or an observed delay. Dispatch may '
                'revise the applicable mode and estimate; this is uncertain evidence.')
    return (f'Current forecast for the lead outbound to {city}: {mode} disruption '
            f'probability {risk} percent, with a possible additional {delay}-minute '
            'arrival delay before handoff. Apply this only to weather_exposed '
            f'{mode} options on this journey; the other modes are outside this '
            'watch. The archived 80-percent warning concerns a companion weekend '
            'excursion and does not apply. The percentage is uncertain evidence, '
            'not an observed delay or a promise. A later dispatch update can '
            'replace the estimated risk, duration or applicable mode.')


def make_forecast_case(seed, variant=0, split='dev'):
    """Four integrated situations, each paired with disruption and false alarm.

    Event tapes are author data. A solver sees only notices and sources that have
    actually arrived; observing an uncertain forecast does not reveal realization.
    """
    c = make_travel_case(seed, 'meeting_update', variant, split)
    suffix = c['case_id'].rsplit('-', 1)[1]
    family, storm = (variant % 8)//2, variant % 2 == 0
    # Scenario mechanics may share a family; the later operator instruction is
    # drawn separately, rather than being a function of the spending ceiling.
    allowed = random.Random(seed ^ 20261011).choice(('Aster', 'Birch', 'Cedar'))
    excluded = [name for name in ('Aster', 'Birch', 'Cedar') if name != allowed]
    # Pair ancillary initial wording/waiver facts across weather outcomes. Their
    # evidence category, cutoff or prose style must not reveal realized weather.
    style = family % 2
    preferred = ('flight', 'train', 'coach', 'flight')[family]
    budgets = (225, 185, 200, 205)
    prices = ((105, 125, 160), (100, 120, 220), (95, 110, 145), (100, 125, 240))[family]
    fee = (20, 15, 10, 20)[family]
    initial_risk = (15, 75, 10, 75)[family]
    current_risk = (75, 20, 70, 15)[family]
    initial_mode = ('flight', 'train', 'coach', 'train')[family]
    current_mode = ('flight', 'train', 'coach', 'flight')[family]
    current_delay = (120, 120, 90, 90)[family]
    forecast_at = (8, 9, 7, 10)[family]
    weather_at = ((16, 16), (18, 20), (16, 18), (20, 18))[family][variant % 2]
    recovery_open = (14, 16, 14, 18)[family]
    recovery_close = (24, 28, 26, 28)[family]
    recovery_price = (175, 150, 180, 165)[family]
    transfer = dict(flight=20, train=20, coach=20)
    c.update(family='weather_planning', difficulty='forecast',
             advanced_situation=('flight_watch_and_access', 'rail_watch_and_carrier',
                                 'coach_watch_and_transfer', 'changed_watch_and_trip_scope')[family],
             budget=budgets[family], deadline=620, preferred=preferred,
             requires_step_free=family == 2, avoid_carriers=[], transfer=transfer,
             booking_deadline=12, hold_minutes=5, interrupt_confirmation=False,
             waiver_type='cancel-reference' if style == 0 else 'disruption-letter',
             waiver_deadline=(11, 18, 11, 18)[family], handoff_minute=24, horizon=36)
    preference = dict(flight='a flight', train='rail', coach='a coach')[preferred]
    access = ('I need step-free access.' if c['requires_step_free'] else
              'Stairs are currently fine.')
    c['initial_request'] = (
        f"Plan my replacement outbound to {c['city']}; the client needs me by 10:20 "
        f"today. The additional-spending ceiling is USD {c['budget']}, including "
        'the USD 55 hotel charge and all nonrefunded fare changes. Please waive '
        'that charge and preserve our room and the colleague-return booking. '
        f'I prefer {preference} when feasible; all listed operators are currently '
        f"allowed. {access} Approval {c['consent']} covers my outbound and permitted "
        'fare changes, including their stated penalties. A first outbound must be '
        'confirmed by virtual minute 12; later approved repairs may use new offers. '
        'Read weather-forecast before choosing a fare; dispatch can revise its '
        'risk, possible delay and applicable mode, and forecasts can be wrong. '
        f'Current initial offers close at minute 12. Recovery offers open at minute '
        f'{recovery_open} and close at minute {recovery_close}; a valid hold protects '
        'its quoted fare until the hold deadline. Stay responsive to traveler and '
        'source updates through minute 24, then finish by minute 36. A new spending limit '
        'applies to new commitments; previously approved charges remain valid. '
        'Hotel check-in at 13:00 is unrelated to the client arrival deadline.')
    c['documents']['transport-guide']['text'] = transfer_text(transfer, c['city'], style)
    c['documents']['hotel-bulletin']['text'] = waiver_text(
        c['waiver_type'], c['waiver_code'], c['waiver_deadline'], c['city'], style)
    c['documents']['fare-terms'] = dict(id='fare-terms', title='Replacement fare contracts',
                                       version=1, text=fare_terms_text(), related=[])
    c['documents']['weather-forecast'] = dict(id='weather-forecast',
        title=f'Lead outbound weather watch in {c["city"]}', version=1,
        text=forecast_text(initial_risk, c['city'], style, mode=initial_mode, delay=60), related=[])
    options = []
    stem = dict(flight='air', train='rail', coach='coach')[preferred]
    for carrier_index, carrier in enumerate(('Aster', 'Birch', 'Cedar')):
        for term, price in zip(('locked', 'fee', 'flexible'), prices):
            step_free = ((carrier == 'Cedar') if family == 0 else
                         (carrier == 'Birch') if family == 1 else
                         (term != 'flexible' and carrier != 'Aster') if family == 2 else
                         carrier != 'Aster')
            options.append(dict(id=f'{stem}-{suffix}-{carrier_index}-{term}', mode=preferred,
                price=price, arrival_minute=(545 if family == 2 else 540)+carrier_index,
                carrier=carrier, step_free=step_free, comfort=3, inventory=2,
                expires_at=12, available_from=0, connection='terminal',
                change_policy=term, cancel_fee_usd=fee if term == 'fee' else 0,
                weather_exposed=True))
        for mode in ('flight', 'train', 'coach'):
            if mode == preferred:
                continue
            arrival = ({'train': 540, 'coach': 550} if family == 0 else
                       {'flight': 545, 'coach': 550} if family == 1 else
                       {'flight': 570, 'train': 540} if family == 2 else
                       {'train': 550, 'coach': 555})[mode]
            options.append(dict(id=f'{mode}-{suffix}-{carrier_index}-recovery', mode=mode,
                price=recovery_price, arrival_minute=arrival+carrier_index,
                carrier=carrier, step_free=True, comfort=3, inventory=2,
                expires_at=recovery_close, available_from=recovery_open,
                connection='terminal', change_policy='flexible', cancel_fee_usd=0,
                weather_exposed=False))
    random.Random(seed ^ 49163).shuffle(options)
    c['options'] = options
    events = [dict(at=forecast_at, kind='forecast_update',
        text='Dispatch replaced the current lead-outbound weather watch. Read weather-forecast; its estimate or applicable mode has changed, not merely its wording.',
        changes=dict(document_text=forecast_text(current_risk, c['city'], 1-style,
                     mode=current_mode, delay=current_delay)))]
    if family == 0:
        events.append(dict(at=14, kind='user_update',
            text=f'The client now needs me by 09:40 today. I now need step-free access for my replacement outbound, including any ticket already booked. {allowed} is the only permitted operator for my outbound; this replaces every earlier carrier restriction. Leave my colleague’s return and the room alone.',
            changes=dict(deadline=580, requires_step_free=True, avoid_carriers=excluded)))
    elif family == 1:
        events.append(dict(at=14, kind='user_update',
            text=f'For my current outbound, the client now needs me by 09:50 and I require step-free access. {allowed} is the only permitted operator; it is permitted again even if an earlier request excluded it. These current-trip rules apply to a confirmed replacement too. Do not change my colleague’s return.',
            changes=dict(deadline=590, requires_step_free=True, avoid_carriers=excluded)))
    elif family == 2:
        events.extend([
            dict(at=12, kind='user_update',
                text=f'The client appointment is now 09:40 for this journey. {allowed} is now the only permitted operator for my outbound, replacing prior exclusions. Keep my step-free requirement and leave my colleague’s return alone.',
                changes=dict(deadline=580, avoid_carriers=excluded)),
            dict(at=14, kind='transport_update',
                text='A road closure changed onward transfers, not terminal arrival clocks. Read the current transport-guide before selecting or retaining a replacement.',
                changes=dict(transfer=dict(flight=0, train=55, coach=15),
                    document_text=transfer_text(dict(flight=0, train=55, coach=15), c['city'], 1-style)))])
    else:
        events.append(dict(at=16, kind='user_update',
            text=f'For this outbound only, I now prefer rail when feasible and need step-free access. {allowed} is the only permitted operator, replacing the earlier carrier list. The client appointment is now 10:00. Finance allows USD 195 for new commitments including retained change fees; already confirmed charges stay approved. Future journeys still use my flight default; leave the companion return alone.',
            changes=dict(preferred='train', requires_step_free=True, avoid_carriers=excluded, deadline=600, budget=195)))
    events.append(dict(at=weather_at, kind='weather_update',
        text='Dispatch resolved the current lead-outbound weather watch. Read the current report before handoff and inspect booked arrivals; current trip restrictions and recovery closing times still apply.',
        changes=dict(weather_delays={current_mode: current_delay if storm else 0},
                     forecast_text=forecast_text(current_risk, c['city'], observed=True,
                                    storm=storm, mode=current_mode, delay=current_delay))))
    c['events'] = sorted(events, key=lambda event: event['at'])
    return c


"""Integrated replanning scenarios using the published tools and score."""


def _short_transfer(values, city, style=0):
    if style % 2:
        return (f'Client transfers in {city}: add {values["flight"]} minutes after an air arrival, '
                f'{values["train"]} after a rail arrival, and {values["coach"]} after a coach arrival. '
                'These are onward durations; ticket arrival times do not include them.')
    return (f'Terminal-to-client travel in {city}: flight {values["flight"]} minutes, '
            f'train {values["train"]} minutes, coach {values["coach"]} minutes. '
            'Add the relevant transfer to the terminal arrival time.')


def _short_waiver(category, code, cutoff, style=0):
    if style % 2:
        return (f'For this existing room, send {code} as evidence type {category} before virtual minute {cutoff}. '
                'Use this bulletin version. Acceptance removes USD 55 and keeps the room. '
                'A claim accepted earlier remains accepted.')
    return (f'The room stays reserved. Waive the USD 55 charge by submitting evidence type '
            f'{category}, code {code}, and this source version before virtual minute {cutoff}. '
            'An accepted claim remains valid after a bulletin revision.')


def _short_watch(risk, mode, delay, observed=False, storm=False, style=0):
    if observed:
        return ((f'The {mode} disruption occurred: weather-exposed services gained {delay} minutes. '
                 if storm else f'The {mode} warning cleared without a delay. ')
                + 'Current search and booking arrivals already include the actual result. '
                'There is no further predicted delay: future risk is zero percent and no mode is under a watch.')
    if style % 2:
        return (f'For the lead outbound, the chance of a further {delay}-minute delay to weather-exposed '
                f'{mode} services is {risk} percent. Other modes and protected services are outside this watch. '
                'This is a forecast, not a delay already included in ticket arrivals.')
    return (f'Lead outbound forecast: {mode} risk {risk} percent, possible additional delay {delay} minutes. '
            f'Only weather_exposed {mode} services are affected; other modes are unaffected. '
            'Do not add this forecast to observed arrivals as if it had already happened.')


def _fresh_documents(c, style=0):
    c['documents'] = {
        'transport-guide': dict(id='transport-guide', title='Current client transfers', version=1,
            text=_short_transfer(c['transfer'], c['city'], style), related=[]),
        'hotel-terms': dict(id='hotel-terms', title='Existing room and fee', version=1,
            text='Keep the room. A USD 55 charge is pending. Read hotel-bulletin for the evidence and cutoff.',
            related=['hotel-bulletin']),
        'hotel-bulletin': dict(id='hotel-bulletin', title='Current fee-waiver instructions', version=2,
            text=_short_waiver(c['waiver_type'], c['waiver_code'], c['waiver_deadline'], style), related=[]),
        'traveler-profile': dict(id='traveler-profile', title='Traveler and trip approval', version=1,
            text='Booking platform operators: Aster, Birch, Cedar. The hotel and companion return must stay unchanged.',
            related=[]),
        'fare-terms': dict(id='fare-terms', title='Fare and hold terms', version=1,
            text=fare_terms_text(), related=[]),
    }


def _release_request(c, extra, style=0, profile_fields=False):
    clock = f"{c['deadline']//60:02d}:{c['deadline']%60:02d}"
    mode = {'flight': 'flight', 'train': 'rail', 'coach': 'coach'}[c['preferred']]
    finances = (f'Extra spending may not exceed USD {c["budget"]}, including the hotel charge and retained cancellation fees. '
                f'For this trip I prefer {mode} when feasible. ')
    if profile_fields:
        c['documents']['traveler-profile']['text'] += ' Current lead outbound: ' + finances
        finances = 'Read traveler-profile for the current spending approval and mode preference. '
    access = 'I need step-free access. ' if c['requires_step_free'] else 'Stairs are currently fine. '
    carrier = (f'Do not use {", ".join(c["avoid_carriers"])} for my replacement. '
               if c['avoid_carriers'] else 'All listed operators are currently permitted. ')
    if style % 2:
        opening = (f'Please replace my cancelled outbound to {c["city"]}; reach the client by {clock}. '
                   f'{finances}{access}{carrier}Keep the room and companion return and remove the room charge. ')
    else:
        opening = (f'Repair my cancelled outbound to {c["city"]} for the {clock} client appointment. '
                   f'{finances}{access}{carrier}Waive the USD 55 hotel charge while preserving the room and companion return. ')
    c['initial_request'] = (opening + f'Approval {c["consent"]} covers my replacement and permitted fare changes. '
        f'Confirm a first outbound by virtual minute {c["booking_deadline"]}; monitor through minute 24 and finish by minute 36. '
        'Later spending limits apply to new commitments; previously approved charges remain approved. ' + extra)


def _offer(c, number, mode, price, arrival, carrier, term='flexible', fee=0,
           opening=0, closing=36, access=True, exposed=False):
    suffix = c['consent'].split('-', 1)[1]
    return dict(id=f'offer-{suffix}-{number}', mode=mode, price=price,
                arrival_minute=arrival, carrier=carrier, step_free=access,
                comfort=3, inventory=2, expires_at=closing, available_from=opening,
                connection='terminal', change_policy=term, cancel_fee_usd=fee,
                weather_exposed=exposed)


def make_integrated_reactive(seed, family, variant=0, split='dev', style=0):
    """Known windows, independent revisions and recoverable fare decisions."""
    c = make_travel_case(seed, family, variant, split)
    index = FP_FAMILIES.index(family)
    shifts = (0, 1, -1)[style % 3]
    mode = ('flight', 'train', 'coach')[index % 3]
    alternate = next(m for m in ('flight', 'train', 'coach') if m != mode)
    opening, closing = ((0,36), (13,24), (12,22), (0,36),
                        (11,17), (0,36), (10,16), (15,24))[index]
    if opening:
        opening += shifts
        closing += shifts
    c.update(budget=(240,195,225,230,230,240,215,225)[index], deadline=690,
             preferred=mode, requires_step_free=False, avoid_carriers=[],
             transfer=dict(flight=20,train=25,coach=30), hold_minutes=14,
             waiver_deadline=(18,11,18,11,18,18,18,18)[index],
             interrupt_confirmation=index==5, events=[])
    _fresh_documents(c, style)
    options=[]
    for i, carrier in enumerate(('Aster','Birch','Cedar')):
        for j, term in enumerate(('locked','fee','flexible')):
            price = (90+i*5, 110+i*10, 260 if index in (1,6) else 150+i*5)[j]
            fee = (35,10,25)[i] if term=='fee' else 0
            options.append(_offer(c,len(options),mode,price,640+i,carrier,term,fee,
                                 closing=14 if opening else 36,access=i!=0))
        for travel_mode in (mode,alternate):
            price = (180 if index in (0,3,5) else 170) + (i%2)*5
            options.append(_offer(c,len(options),travel_mode,price,520+i*3,carrier,
                                 opening=opening,closing=closing))
    c['options']=options
    event = lambda at, kind, text, **changes: dict(at=at,kind=kind,text=text,changes=changes)
    window = (f'Replacement inventory opens at virtual minute {opening} and closes at minute {closing}. '
              'Search in that window. A hold remains valid for 14 minutes after it is made, even if inventory closes. '
              if opening else 'Further replacement offers remain available through minute 36. ')
    extra = window
    if index==0:
        c['events']=[event(10,'user_update','The client appointment is now 09:40. Retain my other conditions.',deadline=580),
                     event(19,'user_update','For my outbound, only Cedar is permitted from now on. This replaces the previous carrier list.',avoid_carriers=['Aster','Birch'])]
    elif index==1:
        extra += ('The later recovery fares are expected to start at USD 170. Choose an initial contract that leaves an affordable exchange if the client time changes. ')
        c['events']=[event(9,'user_update','Finance reduces the ceiling for new commitments to USD 185, including all retained fees. Earlier approved charges stand.',budget=185),
                     event(17,'user_update','The current client appointment is now 09:40. Keep the other requirements.',deadline=580)]
    elif index==2:
        c['events']=[event(12,'user_update',f'For this journey I now prefer {alternate} and require step-free access. The preference for future trips is unchanged.',preferred=alternate,requires_step_free=True),
                     event(18,'user_update','The client now needs me by 09:40. Other requirements continue.',deadline=580)]
    elif index==3:
        replacement='disruption-letter' if c['waiver_type']=='cancel-reference' else 'cancel-reference'
        c['documents']['hotel-bulletin']['text'] += ' A previous claim using proof-0000 belonged to another room.'
        c['events']=[event(6,'document_update','The hotel replaced hotel-bulletin. Pending claims need the new procedure; accepted claims stand.',waiver=replacement,waiver_version=3,
                          document_text=_short_waiver(replacement,c['waiver_code'],11,1-style%2)),
                     event(17,'user_update','The client appointment moves to 09:40 and I now need step-free access. Keep the other conditions.',deadline=580,requires_step_free=True)]
    elif index==4:
        extra += ('The client will confirm a possibly earlier appointment at minute 18. A 09:30 arrival would cover the earliest proposed time. '
                  'Keep a usable ticket while arranging any replacement. ')
        c['events']=[event(18,'user_update','The client confirms 09:30 for this outbound. All other current requirements remain.',deadline=570)]
    elif index==5:
        c['events']=[event(8,'provider_notice','A lost confirmation reply may still mean the booking succeeded. Inspect the same request key before another commitment.'),
                     event(18,'user_update','The client now needs me by 09:40 and only Birch is permitted for this outbound. This replaces the earlier carrier list.',deadline=580,avoid_carriers=['Aster','Cedar'])]
    elif index==6:
        extra += ('Roadworks start at minute 18: onward transfers can then require up to 65 minutes. The client is considering a 10:00 appointment and will confirm it at minute 20. A terminal arrival by 08:55 covers that possible appointment even with the longest announced transfer. ')
        values=dict(flight=65,train=60,coach=55)
        c['events']=[event(18,'transport_update','Roadworks began. Read the revised client transfer guide; ticket arrival clocks did not change.',transfer=values,document_text=_short_transfer(values,c['city'],style)),
                     event(20,'user_update','The client appointment is now 10:00. Keep all other conditions.',deadline=600)]
    else:
        c['events']=[event(13,'user_update','For my current outbound, stairs are no longer possible and only Aster is permitted. This replaces the earlier operator list.',requires_step_free=True,avoid_carriers=['Birch','Cedar']),
                     event(20,'user_update','The client appointment is now 09:40. My access and carrier requirements remain in force.',deadline=580)]
    _release_request(c,extra,style,profile_fields=index in (1,7))
    random.Random(seed ^ 0x5931).shuffle(c['options'])
    c['events'].sort(key=lambda e:e['at'])
    return c


def make_contingent_forecast(seed, variant=0, split='dev', style=0):
    """A held backup can survive a window and be exercised after resolution.

    Both members of a pair have the same initial observable evidence. A policy
    can retain its preferred ticket on a false alarm and use a still-valid hold
    after a real delay, without knowing the event tape in advance.
    """
    family=(variant%8)//2
    storm=variant%2==0
    pair_seed=seed-(variant%2)
    c=make_travel_case(pair_seed,'meeting_update',family,split)
    display_suffix=str(random.Random(seed ^ 7489).randrange(10000,99999))
    c['case_id']=f'{split}-{display_suffix}'
    c['seed']=seed
    c['variant']=variant
    mode=('flight','train','coach','train')[family]
    watched=('flight','train','flight','train')[family]
    first_risk=(35,30,65,45)[family]
    current_risk=(75,70,80,70)[family]
    delay=(120,110,100,100)[family]
    offset=(0,1,-1)[style%3]
    opening=(12,13,11,12)[family]+offset
    closing=(18,19,17,18)[family]+offset
    resolved=(22,23,21,22)[family]+offset
    recovery_price=(175,170,165,175)[family]
    c.update(family='weather_planning',difficulty='forecast',
        advanced_situation=('held_backup','repair_budget','revised_watch','transfer_and_backup')[family],
        budget=(215,150,150,215)[family],deadline=620 if family!=3 else 600,
        preferred=mode,requires_step_free=family==2,avoid_carriers=[],
        transfer=dict(flight=20,train=20,coach=20),booking_deadline=12,
        hold_minutes=14,interrupt_confirmation=False,waiver_deadline=11,
        waiver_type='cancel-reference' if family%2==0 else 'disruption-letter')
    _fresh_documents(c,style)
    c['documents']['weather-forecast']=dict(id='weather-forecast',title='Current outbound weather watch',version=1,
        text=_short_watch(first_risk,watched,delay,style=style),related=[])
    c['options']=[]
    for i,carrier in enumerate(('Aster','Birch','Cedar')):
        for term in ('locked','fee','flexible'):
            price={'locked':85+5*i,'fee':105+15*i,'flexible':260+5*i}[term]
            fee=((45,10,30)[i] if family==1 else (30,10,20)[i]) if term=='fee' else 0
            c['options'].append(_offer(c,len(c['options']),mode,price,540+i*2,carrier,term,fee,
                                      closing=closing,access=True,exposed=True))
        for fallback in ('flight','train','coach'):
            if fallback==mode: continue
            arrival=540+i*2 if family!=3 else (535+i*2 if fallback=='flight' else 550+i*2)
            c['options'].append(_offer(c,len(c['options']),fallback,recovery_price+i*2,arrival,carrier,
                                      opening=opening,closing=closing,access=True))
        # Later services in the preferred mode have different delay headroom.
        # The earliest can absorb the watch, but is not always within budget.
        same_price=((190,160,145),(225,155,145),(225,155,145),(190,160,145))[family][i]
        same_arrival=(470,515,545)[i] if family!=3 else (465,510,540)[i]
        c['options'].append(_offer(c,len(c['options']),mode,same_price,same_arrival,carrier,
                                  opening=opening,closing=closing,access=True,exposed=True))
    extra=(f'Backup inventory opens at virtual minute {opening} and closes at minute {closing}; '
           f'the weather report resolves at minute {resolved}. Alternative-mode backup fares start at USD {recovery_price}; later preferred-mode services have their own fares and arrival margins. '
           'A hold lasts 14 minutes from creation and can be confirmed after inventory closes while the hold remains valid. '
           'A forecast may be a false alarm: keep the preferred service when it remains suitable. '
           'Read the current weather watch before deciding which service needs a backup. ')
    emergency_ceiling={1:190,2:205}.get(family)
    if emergency_ceiling:
        extra += (f'If the weather report confirms an actual disruption of my preferred service, finance will raise the total ceiling to USD {emergency_ceiling}. '
                  'This replaces the ordinary ceiling; it is not extra money and is not active until a confirmation notice arrives. '
                  'You may hold a backup before that decision, but do not pay beyond the current ceiling. ')
    _release_request(c,extra,style,profile_fields=family==1)
    c['events']=[dict(at=8,kind='forecast_update',
        text='Dispatch replaced the lead-outbound weather watch. Read the current source; its mode or likelihood may have changed.',
        changes=dict(document_text=_short_watch(current_risk,mode,delay,style=1-style%2)))]
    if family==3:
        transfer=dict(flight=25,train=20,coach=70)
        c['events'].append(dict(at=10,kind='transport_update',
            text='A road closure changed the onward journey. Refresh transport-guide before choosing a backup.',
            changes=dict(transfer=transfer,document_text=_short_transfer(transfer,c['city'],style))))
    if family==2:
        c['events'].append(dict(at=6,kind='user_update',
            text='Only Cedar is now permitted for my outbound. This replaces the earlier carrier list; retain my step-free requirement and other trip rules.',
            changes=dict(avoid_carriers=['Aster','Birch'])) )
    c['events'].append(dict(at=resolved,kind='weather_update',
        text='The current weather watch has resolved. Inspect current booking arrivals; they include the actual delay. A previously held backup may still be usable.',
        changes=dict(weather_delays={mode:delay if storm else 0},
            forecast_text=_short_watch(current_risk,mode,delay,observed=True,storm=storm,style=style))))
    if emergency_ceiling:
        c['events'].append(dict(at=resolved,kind='user_update',
            text=(f'The disruption is confirmed. Finance now authorizes a total ceiling of USD {emergency_ceiling} for new commitments, including retained cancellation fees. All other trip conditions remain.'
                  if storm else 'The weather warning cleared. The ordinary USD 150 ceiling remains in force; no emergency allowance was activated.'),
            changes=dict(budget=emergency_ceiling if storm else 150)))
    c['events'].sort(key=lambda e:e['at'])
    random.Random(pair_seed ^ 0x5912).shuffle(c['options'])
    return c


FP_DEV_CASES = ([make_basic_case(18100+i,i,'dev') for i in range(3)]
    + [make_integrated_reactive(8100+i,f,i%2,'dev',i%2)
       for i,f in enumerate(('meeting_update','budget_update','quote_expiry'))]
    + [make_contingent_forecast(28100,0,'dev'),
       make_contingent_forecast(28101,1,'dev'),
       make_contingent_forecast(28102,2,'dev')])
FP_PUBLIC_CASES = ([make_basic_case(19100+i,i,'public') for i in range(8)]
    + [make_integrated_reactive(9100+i,f,i%2,'public',i%2) for i,f in enumerate(FP_FAMILIES)]
    + [make_contingent_forecast(29100+i,i,'public',((i//2)%2)) for i in range(8)])
FP_FINAL_CASES=FP_PUBLIC_CASES


def public_case_list(cases):
    return [dict(case_id=c['case_id'],request=c['initial_request']) for c in cases]


def travel_case_fingerprints(cases):
    return [fp_hash(c) for c in cases]


# The versioned JSON files are the complete current development and Public banks.
from pathlib import Path as _Path
_data = _Path(__file__).resolve().parents[1] / "data"
FP_DEV_CASES = json.loads((_data / "dev.json").read_text())
FP_PUBLIC_CASES = json.loads((_data / "public.json").read_text())
FP_FINAL_CASES = FP_PUBLIC_CASES
