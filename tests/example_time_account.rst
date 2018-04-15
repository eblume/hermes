Hermes By Example
-----------------

Make some imports.

    >>> from hermes.timeaccount import TimeAccount

Create a time account and load it with testing data.

    >>> account = TimeAccount()
    >>> len(account)
    0
    >>> account._inject_test_data()
    >>> len(account)
    4

Copy the account.

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
