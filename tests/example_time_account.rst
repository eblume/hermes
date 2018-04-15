Hermes By Example
-----------------

Make some imports.

    >>> from hermes.timeaccount import TimeAccount
    >>> import datetime as dt

Create a time account.

    >>> account = TimeAccount()
    >>> account._inject_test_data()

Some consistency checks for the interface.

    >>> len(account)
    0
    >>> account == account[:]
    True
    >>> account is account[:]
    False
