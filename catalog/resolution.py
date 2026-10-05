"""Phase 3: scoped value resolution (single source of truth).

Fallback chain for a (channel, locale) scope, most to least specific:
  exact (channel + locale) -> channel-only -> locale-only -> global.
A channel-exact beats a locale-exact on ties (documented tiebreak, encoded
as tuple ordering below). Empty MULTISELECT rows count as UNSET (2.1 audit
decision) and resolution keeps looking down the chain.

Used by the completeness engine and the resolved-values endpoint, so both
agree by construction.
"""
from .schemas import resolve_attribute_value


def _is_set(value_row) -> bool:
    resolved = resolve_attribute_value(value_row)
    return resolved not in (None, '', [])


def _scope_score(value_row, channel_id, locale_id):
    """(channel_score, locale_score) or None when outside the scope.

    Exact match scores 2, global (None) scores 0 on each axis. Tuple ordering
    yields the documented priority: exact > channel-only > locale-only >
    global, with channel beating locale on the (2,0)-vs-(0,2) tie.
    """
    c, loc = value_row.channel_id, value_row.locale_id
    if c is not None and c != channel_id:
        return None
    if loc is not None and loc != locale_id:
        return None
    return (2 if c is not None else 0, 2 if loc is not None else 0)


def resolve_scoped_value(values, attribute, channel_id, locale_id):
    """Best set value row for (owner values, attribute, scope), or None.

    `values` is any iterable of value rows (typically pre-filtered by owner).
    Only rows for `attribute` carrying real data participate; among them the
    most specific in-scope row wins, ties broken by lowest pk (deterministic).
    """
    best = None
    best_key = None
    for row in values:
        if row.attribute_id != attribute.pk:
            continue
        if not _is_set(row):
            continue
        score = _scope_score(row, channel_id, locale_id)
        if score is None:
            continue
        key = (score, -(row.pk or 0))
        if best_key is None or key > best_key:
            best, best_key = row, key
    return best
