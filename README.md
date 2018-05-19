Hermes
======

by Erich Blume (blume.erich@gmail.com)

This project contains the code for Hermes, which is a Time Accountant. That is
to say, Hermes is a set of tools for managing time. The scope of Hermes is
quite large, but right now this project primarily provides `hermes`, which is a
python package for manipulating, building, querying, filtering, and tabulating
timespans.

How to use Hermes
-----------------

TODO - expand this documentation! Please seen CONTRIBUTING.rst.

For now, please check out the `tests` directory for usage examples.

Hermes' Design
--------------

Eventually, Hermes' interface will outgrow a simple python library and will
probably become some sort of networked asynchronous API. Hermes will become an
always-on personal automaton, working in concert with other assistent AI's that
help Hermes decide on the current accounting of time as well as projecting
future accounting of time (which is how Hermes understands 'planning'). Let me
reiterate that in bold as it is key. We will call it the First Rule of Hermes.

1. **Hermes understands planning to mean 'accounting of future time'.**

Alone, Hermes probably doesn't have a great grasp on the future. Planning
involves opinions. Hermes doesn't have opinions and doesn't make judgements.
This is important because we never want the user to lie to Hermes, nor be lied
to by Hermes. In some cases, Hermes won't know what's going on, but rather than
try and judge what is going on, Hermes will keep track of that uncertainty and
account for it.

2. **Hermes doesn't have opinions and doesn't make judgements.**

Hermes works in silence and does not record anything anywhere. While this is
plenty of work for Hermes, it isn't very useful to anyone unless that account
is stored so that it can be queried for later. Somewhat in opposition of that,
Hermes may need a log of what happened to answer queries in the future about
what happened in the past. This brings up two important rules:

3. **Hermes needs a scribe process to serialize a resumable log.**
4. **Hermes is ephemeral, and needs a resumable log to resume in case of an
   interruption.**

A corollary of 4 is that Hermes is totally fine NOT resuming a log, but will
be unable to answer questions about time before it began its log.

Long Term Vision
----------------

Hermes is just one component in a planned automation assistant framework.
Hermes is designed to be one of the central components that orchestrates this
framework, by speaking in an unopinionated way with the other components and to
account for what actually happened from time to time. Very briefly, the planned
components looks a little like:

Human <---> Hermes <----> Stress Atenuator / Decider <------> Haphaestus
              |                                         |
           Scribe --> S3, Airtable, logfile, etc...     |---> Persephone
                                                        |
                                                        |---> etc...

The Stress Atenuator / Decider (name pending because the current one is SAD) is
a multiplexer across the various scheduling automatons to decide which
automaton is 'in control'. If the stress level that is being tracked by the
atenuator reaches some definable cap, the decider will reset the system's
stress and select a new scheduler. (The Human will be involved in this
selection.) ALL automatons (and the Human) can increase the stress of the
system but only way the stress can reset to 0 is if the Human decides to do so,
which typically happens when the Stress Atenuator / Decider trips due to high
stress and starts a selection process. Ultimately, this component is run by
Hermes, so it is basically part of Hermes. The specifics for how Hermes uses
the Stress Atenuator / Decider is rather complicated, but but you can think of
it as a PID loop controller controlling the system's stress level to prevent
wild oscilations in stress, AND a system for choosing between (that is,
'multiplexing') which automation assistant is 'in control'.

The automatons... are a whole thing. I'll need to document them another time.

Modifying / Licensing
=====================

Please see LICENSE and CONTRIBUTING.rst
