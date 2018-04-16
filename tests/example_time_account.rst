Hermes By Example
-----------------

Let's assume we've already got a TimeAccount. We'll get to know it as we
examine its properties.

This account has four main tags.

    >>> len(account)
    4

We can copy the account.

    >>> account == account[:]
    True
    >>> account is account[:]
    False

Query for some tag info.

    >>> tags = iter(account)
    >>> first_tag = next(tags)
    >>> second_tag = next(tags)
    >>> first_tag
    Tag('Fake Tag 1')
    >>> second_tag
    Tag('Fake Tag 2')
    >>> first_tag == second_tag
    False

Reverse the order of events.

    >>> reversed_account = reversed(account)
    >>> reversed_account_tags = iter(reversed_account)
    >>> _ = next(reversed_account_tags); _ = next(reversed_account_tags)
    >>> third_reversed_tag = next(reversed_account_tags)
    >>> third_reversed_tag == second_tag
    True
    >>> fourth_reversed_tag = next(reversed_account_tags)
    >>> fourth_reversed_tag == first_tag
    True

Reverse the order a different way.

    >>> reversed_account == account[::-1]
    True
