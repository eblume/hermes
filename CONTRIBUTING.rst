.. highlight:: shell

Contributing
============

Contributions are welcome, and they are greatly appreciated! Every little bit
helps, and credit will always be given.

You can contribute in many ways:

Types of Contributions
----------------------

Report Bugs
~~~~~~~~~~~

Report bugs at https://github.com/eblume/hermes/issues.

If you are reporting a bug, please include:

* Your operating system name and version.
* Any details about your local setup that might be helpful in troubleshooting.
* Detailed steps to reproduce the bug.

Fix Bugs
~~~~~~~~

Look through the GitHub issues for bugs. Anything tagged with "bug" and "help
wanted" is open to whoever wants to implement it.

Implement Features
~~~~~~~~~~~~~~~~~~

Look through the GitHub issues for features. Anything tagged with "enhancement"
and "help wanted" is open to whoever wants to implement it.

Write Documentation
~~~~~~~~~~~~~~~~~~~

Hermes could always use more documentation, whether as part of the
official Hermes docs, in docstrings, or even on the web in blog posts,
articles, and such.

Submit Feedback
~~~~~~~~~~~~~~~

The best way to send feedback is to file an issue at
https://github.com/eblume/hermes/issues.

If you are proposing a feature:

* Explain in detail how it would work.
* Keep the scope as narrow as possible, to make it easier to implement.
* Remember that this is a volunteer-driven project, and that contributions
  are welcome :)

Get Started!
------------

Ready to contribute? Here's how to set up `hermes` for local development::

$ pipenv update
$ pipenv run tests

That's it! Once the tests pass, you'll know you've got a fully functioning
development environment. There are some requirements you will need to install
first:

* `pipenv`: https://github.com/pypa/pipenv

Additionally, you'll almost certainly want:

* `pyenv`: https://github.com/pyenv/pyenv

If you've got those two systems installed, `pipenv` should take care of
everything. Please file an issue if it does not. You SHOULD see a fully
passing set of tests, with a message like:

    ============= 28 passed in 0.18 seconds ===================

This will be your indicator that you are ready to develop!

Before You Submit
-----------------

Before you submit any work, please run the full linting setup to ensure that
code linters (mypy, black, pep8, etc.) pass on the code. SUBMISSIONS THAT DO
NOT LINT WILL NOT BE ACCEPTED. If you've run `pipenv update` you should get all
of these 'for free' with no further action required on your part. You may
notice that `git commit` runs the linters for you, as is expected. You may
wish to integrate these linters with your editor for live linting, if you use
`vim`, I recommend syntastic: https://github.com/vim-syntastic/syntastic. Then
add something like this to your `.vimrc`:

    let g:syntastic_python_checkers=['flake8', 'python, 'mypy]


Special Thanks
--------------

I would like to thank Phildini, author of `thanks`
<https://github.com/phildini/thanks>. Aside from being an excellent tool,
thanks also provided the basis for this file.
