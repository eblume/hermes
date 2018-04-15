Hermes By Example
-----------------

Make some imports.

    >>> from hermes.timeaccount import TimeAccount
    >>> import datetime as dt

Create a time account and load it with testing data.

    >>> account = TimeAccount()
    >>> len(account)
    0
    >>> account._inject_test_data()
    >>> len(account)
    4

Some consistency checks for the interface.

    >>> account == account[:]
    True
    >>> account is account[:]
    False
