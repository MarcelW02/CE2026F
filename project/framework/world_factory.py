"""Validated selection of the common legacy and operational travel worlds."""
import json
import math

from .fp_cases import FP_VERSION, FP_TIERS
from .fp_world import TravelWorld

MAX_CASE_BYTES = 100000
MAX_OFFERS = 24
MAX_DOCUMENTS = 16
MAX_EVENTS = 8
MAX_DOCUMENT_CHARACTERS = 6000
MAX_TOTAL_TEXT_CHARACTERS = 30000
MODES = frozenset(('flight', 'train', 'coach'))
BASE_FIELDS = frozenset(('version', 'case_id', 'family', 'difficulty', 'budget', 'deadline',
    'preferred', 'requires_step_free', 'avoid_carriers', 'transfer', 'consent', 'waiver_type',
    'waiver_code', 'waiver_deadline', 'initial_request', 'documents', 'options', 'events',
    'horizon', 'handoff_minute', 'hold_minutes', 'interrupt_confirmation', 'booking_deadline'))
OPTIONAL_FIELDS = frozenset(('seed', 'variant', 'city', 'advanced_situation',
                            'operational_contract', 'operational_sources'))
EVENT_KINDS = frozenset(('user_update', 'document_update', 'transport_update', 'forecast_update',
                        'weather_update', 'provider_notice', 'stock_update', 'sellout'))
CHANGE_FIELDS = frozenset(('budget', 'deadline', 'preferred', 'waiver', 'waiver_version',
    'requires_step_free', 'avoid_carriers', 'transfer', 'document_text', 'forecast_text',
    'forecast_version', 'weather_delays', 'option_id', 'operational_contract', 'operational_documents'))


def _number(value, label, maximum=1000000, integer=False, minimum=0):
    if type(value) not in ((int,) if integer else (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(label + ' must be a finite number within the published range.')


def _text(value, label, maximum=MAX_DOCUMENT_CHARACTERS):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(label + ' must be nonempty text within its length limit.')


def _strings(values, label, maximum=24):
    if not isinstance(values, list) or len(values) > maximum:
        raise ValueError(label + ' must be a bounded list of strings.')
    for value in values: _text(value, label, 120)
    if len(set(values)) != len(values): raise ValueError(label + ' must not contain duplicates.')


def _transfer(values):
    if not isinstance(values, dict) or set(values) != MODES:
        raise ValueError('Transfers must specify all three modes exactly.')
    for amount in values.values(): _number(amount, 'Transfer duration', 180, integer=True)


def validate_document(document, expected_id=None):
    if not isinstance(document, dict) or set(document) != {'id', 'title', 'version', 'text', 'related'}:
        raise ValueError('Documents require exactly id, title, version, text and related.')
    _text(document['id'], 'Source ID', 120)
    _text(document['title'], 'Source title', 200)
    _text(document['text'], 'Source text')
    _number(document['version'], 'Source version', 1000, integer=True, minimum=1)
    _strings(document['related'], 'Related source IDs', MAX_DOCUMENTS)
    if expected_id is not None and document['id'] != expected_id:
        raise ValueError('The document ID must match its mapping key.')


def _validate_case(case):
    """Reject unsupported structure before execution; meaning needs case review.

    Returns None. This does not run a solver, disclose truth or establish feasibility.
    Both legacy-shaped and operational cases use the current release version.
    """
    if not isinstance(case, dict) or BASE_FIELDS - set(case) or set(case) - BASE_FIELDS - OPTIONAL_FIELDS:
        raise ValueError('Use a complete case with only the published fields.')
    try:
        encoded = json.dumps(case, allow_nan=False, ensure_ascii=False)
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError('Cases must contain finite ordinary JSON values.') from error
    if len(encoded.encode()) > MAX_CASE_BYTES:
        raise ValueError('A case may contain at most 100000 UTF-8 bytes.')
    if case['version'] != FP_VERSION or case['difficulty'] not in FP_TIERS:
        raise ValueError('Use the current project version and a published difficulty.')
    for field in ('case_id', 'family', 'consent', 'waiver_type', 'waiver_code'):
        _text(case[field], field, 120)
    for field in ('city', 'advanced_situation'):
        if field in case: _text(case[field], field, 200)
    for field in ('seed', 'variant'):
        if field in case: _number(case[field], field, 2**63-1, integer=True)
    _text(case['initial_request'], 'Initial request')
    _number(case['budget'], 'Budget')
    _number(case['deadline'], 'Arrival clock minute', 1439, integer=True)
    if case['preferred'] not in MODES: raise ValueError('Use a published preferred mode.')
    for field in ('requires_step_free', 'interrupt_confirmation'):
        if type(case[field]) is not bool: raise ValueError(field + ' must be boolean.')
    _strings(case['avoid_carriers'], 'Avoided carriers')
    _transfer(case['transfer'])
    if type(case['horizon']) is not int or case['horizon'] != 36:
        raise ValueError('The common horizon is 36 virtual minutes.')
    for field in ('handoff_minute', 'waiver_deadline'):
        _number(case[field], field, 36, integer=True)
    _number(case['hold_minutes'], 'Hold duration', 36, integer=True, minimum=1)
    if case['booking_deadline'] is not None:
        _number(case['booking_deadline'], 'Initial booking deadline', case['handoff_minute'], integer=True)
    documents = case['documents']
    required_docs = {'hotel-terms', 'hotel-bulletin', 'transport-guide', 'traveler-profile'}
    if not isinstance(documents, dict) or not required_docs <= set(documents) or len(documents) > MAX_DOCUMENTS:
        raise ValueError('Keep the four required documents and at most 16 sources.')
    for source_id, document in documents.items():
        validate_document(document, source_id)
        if set(document['related']) - set(documents): raise ValueError('Related sources must exist.')
    if documents['hotel-bulletin']['version'] != 2:
        raise ValueError('The initial hotel bulletin uses version 2.')
    options = case['options']
    if not isinstance(options, list) or not 1 <= len(options) <= MAX_OFFERS:
        raise ValueError('A case needs between 1 and 24 offers.')
    option_ids = set()
    required_option = {'id', 'mode', 'price', 'arrival_minute', 'carrier', 'step_free', 'inventory', 'expires_at'}
    optional_option = {'available_from', 'change_policy', 'cancel_fee_usd', 'weather_exposed', 'hold_fee_usd', 'comfort', 'connection'}
    for option in options:
        if not isinstance(option, dict) or required_option - set(option) or set(option) - required_option - optional_option:
            raise ValueError('Offer fields do not match the supported schema.')
        _text(option['id'], 'Offer ID', 120)
        if option['id'] in option_ids: raise ValueError('Offer IDs must be unique.')
        option_ids.add(option['id'])
        if option['mode'] not in MODES: raise ValueError('Use published transport modes.')
        _text(option['carrier'], 'Carrier', 120)
        if type(option['step_free']) is not bool or type(option.get('weather_exposed', False)) is not bool:
            raise ValueError('Offer accessibility and weather exposure must be boolean.')
        _number(option['price'], 'Fare price')
        _number(option['arrival_minute'], 'Terminal clock minute', 1439, integer=True)
        _number(option['inventory'], 'Inventory', 12, integer=True)
        opening, closing = option.get('available_from', 0), option['expires_at']
        _number(opening, 'Sale opening', 36, integer=True)
        _number(closing, 'Sale closing', 36, integer=True)
        if opening >= closing: raise ValueError('A sale must open before it closes.')
        if option.get('change_policy', 'flexible') not in ('locked', 'fee', 'flexible'):
            raise ValueError('Use locked, fee or flexible base fares.')
        for field in ('cancel_fee_usd', 'hold_fee_usd'):
            _number(option.get(field, 0), field, option['price'])
        if 'comfort' in option: _number(option['comfort'], 'Comfort', 10)
        if 'connection' in option: _text(option['connection'], 'Connection', 200)
    operational = 'operational_contract' in case or 'operational_sources' in case
    if not operational and any(option.get('hold_fee_usd', 0) for option in options):
        raise ValueError('Paid holds require the operational contract format.')
    events = case['events']
    if not isinstance(events, list) or len(events) > MAX_EVENTS:
        raise ValueError('At most eight external events are supported.')
    previous = 0
    total_text = len(case['initial_request']) + sum(len(d['text']) for d in documents.values())
    for event in events:
        if not isinstance(event, dict) or set(event) != {'at', 'kind', 'text', 'changes'}:
            raise ValueError('Events require exactly at, kind, text and changes.')
        _number(event['at'], 'Event time', 36, integer=True, minimum=previous)
        previous = event['at']
        if event['kind'] not in EVENT_KINDS: raise ValueError('Unsupported event kind.')
        _text(event['text'], 'Event notice')
        total_text += len(event['text'])
        changes = event['changes']
        if not isinstance(changes, dict) or set(changes) - CHANGE_FIELDS:
            raise ValueError('Unsupported event amendment fields.')
        if not operational and {'operational_contract', 'operational_documents'} & set(changes):
            raise ValueError('Operational amendments require an initial operational contract.')
        for field in ('budget', 'deadline'):
            if field in changes: _number(changes[field], field, 1439 if field == 'deadline' else 1000000, integer=field == 'deadline')
        if 'preferred' in changes and changes['preferred'] not in MODES: raise ValueError('Invalid amended mode.')
        if 'requires_step_free' in changes and type(changes['requires_step_free']) is not bool: raise ValueError('Accessibility must be boolean.')
        if 'avoid_carriers' in changes: _strings(changes['avoid_carriers'], 'Avoided carriers')
        if 'transfer' in changes: _transfer(changes['transfer'])
        if 'waiver' in changes: _text(changes['waiver'], 'Waiver type', 120)
        for field in ('waiver_version', 'forecast_version'):
            if field in changes: _number(changes[field], field, 1000, integer=True, minimum=1)
        for field in ('document_text', 'forecast_text'):
            if field in changes:
                _text(changes[field], field); total_text += len(changes[field])
        if event['kind'] in ('document_update', 'transport_update', 'forecast_update') and 'document_text' not in changes:
            raise ValueError('A source update needs its new document_text.')
        if event['kind'] in ('forecast_update', 'weather_update') and 'weather-forecast' not in documents:
            raise ValueError('Weather updates need a weather-forecast source.')
        if 'weather_delays' in changes:
            delays = changes['weather_delays']
            if event['kind'] != 'weather_update' or not isinstance(delays, dict) or set(delays) - MODES:
                raise ValueError('Realized delays belong to weather_update and published modes.')
            for delay in delays.values(): _number(delay, 'Weather delay', 1440, integer=True)
        if 'option_id' in changes and changes['option_id'] not in option_ids: raise ValueError('Unknown event offer ID.')
        if event['kind'] == 'sellout' and 'option_id' not in changes: raise ValueError('A sellout needs an offer ID.')
        revised = changes.get('operational_documents', [])
        if not isinstance(revised, list) or len(revised) > MAX_DOCUMENTS:
            raise ValueError('Revised documents must be a bounded list.')
        for document in revised:
            validate_document(document)
            if set(document['related']) - set(documents): raise ValueError('Related sources must exist.')
            total_text += len(document['text'])
    if total_text > MAX_TOTAL_TEXT_CHARACTERS:
        raise ValueError('Case prose may contain at most 30000 characters in total.')
    if operational:
        from .fp_operational import validate_operational_case
        validate_operational_case(case)


def validate_case(case):
    """Validate a complete case without mutation; always reject with ValueError."""
    try:
        _validate_case(case)
    except (KeyError, TypeError, RecursionError, OverflowError) as error:
        raise ValueError('Invalid case structure: ' + type(error).__name__) from error


def world_for_case(case, concurrency=3):
    """Select only the declared common engines after validating the complete case."""
    validate_case(case)
    if 'operational_contract' in case:
        from .fp_operational import OperationalTravelWorld
        return OperationalTravelWorld(case, concurrency=concurrency)
    return TravelWorld(case, concurrency=concurrency)
