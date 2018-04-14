Hermes
======
copyright Erich Blume <blume.erich@gmail.com> 2018


About Hermes
------------
Hermes is the project name for an automated personal assistant framework
thatour I am developing. Hermes is a component in that system, and is
responsible for handling the accounting of time. Hermes understands the world
through slices of time.

Time Slices
-----------

A time slice is a span of time, possibly with 0 'width' or 'duration' (a
special case that denotes a single instant, and which for convenience can often
be represented as a `datetime.datetime` object).

Given any single slice of time, Hermes will return a TimeAccount. Exactly how
Hermes decides on this time account is an implementation detail of Hermes, but
it is important to note that Hermes is happy returning slices that slice from
the past in to the future. (Accounting of future time is, obviously, the realm
of the automated assistants mentioned previously.)

Time Account
------------

A Time Account is an object that is sliceable by a Time Slice. When returned
from Hermes, a Time Account is typically only defined on the interval that
Hermes was given (although in some cases the Time Account may be sliced further
on either end, but this is not necessarily a supported case.) A Time Account
can also be indexed via a 0-width time slice or a `datetime.datetime`. A sliced
Time Account simply returns a new Time Account for just that period. Typically
this results in an more narrowly parsed account of time, but note that
**slicing a time account can change the level of detail in the annotations
returned by a Time Account**.

Details of how to read a full Time Account are found elsewhere (TODO), but
there will be helper functions to read time accounts out to a variety of
serializations including a simple string (even `str` works!)

How to use Hermes
-----------------

Currently, Hermes is a library which implements the Hermes interface summarized
above as a **deterministic, finite state machine**. Plans exist to extend
Hermes to use neural network with live retraining based on the Stress
parameter, for more on this see Long Term Vision.

(TODO - basic useage w/examples).

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

Currently, no special license is available. I retain full copyright. I plan on
placing this code in some sort of open source license in the future, but I want
to put thought in to which one to use. Please contact me with questions if you
have any in the mean time. Just include LICENSING in the subject line so I know
what it's about. Thanks!


