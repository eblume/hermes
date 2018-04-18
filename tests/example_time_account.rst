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
    Tag('Tag A')
    >>> second_tag
    Tag('Tag B')
    >>> first_tag == second_tag
    False
