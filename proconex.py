"""
Proconex is a module to simplify the implementation of the producer/consumer
idiom. In addition to simple implementations based on Python's ``Queue.Queue``,
proconex also takes care of exceptions raised during producing or consuming
items and ensures that all the work shuts down in a clean manner without
leaving zombie threads.

Example Usage
=============

In order to use proconex, we need a few preparations.

First, set up Python's logging:

>>> import logging
>>> logging.basicConfig(level=logging.INFO)

In case you want to use the `with` statement to clean up and still use Python
2.5, you need to import it:

>>> from __future__ import with_statement

And finally, we of course need to import proconex itself:

>>> import proconex

Here is a simple producer that reads lines from a file:

>>> class LineProducer(proconex.Producer):
...     def __init__(self, fileToReadPath):
...         super(LineProducer, self).__init__()
...         self._fileToReadPath = fileToReadPath
...     def items(self):
...         with open(self._fileToReadPath, 'rb') as fileToRead:
...             for lineNumber, line in enumerate(fileToRead, start=1):
...                 yield (lineNumber, line.rstrip('\\n\\r'))

The constructor can take any parameters you need to set up the producer. In
this case, all we need is the path to the file to read, ``fileToReadPath``.
The constructor simply stores the value in an attribute for later reference.

The function ``items()`` typically is implemented as generator and yields the
produced items one after another until there are no more items to produce. In
this case, we just return the file line by line as a tuple of line number and
line contents without trailing newlines.

Next, we need a consumer. Here is a simple one that processes the lines read
by the producer above and prints its number and text:

>>> class LineConsumer(proconex.Consumer):
...     def consume(self, item):
...         lineNumber, line = item
...         if "self" in line:
...             print u"line %d: %s" % (lineNumber, line)

With classes for producer and consumer defined, we can create a producer and a
list of consumers:

>>> producer =  LineProducer(__file__)
>>> consumers = [LineConsumer("consumer#%d" % consumerId)
...         for consumerId in xrange(3)]

To actually start the production process, we need a worker to control the
producer and consumers:

>>> with proconex.Worker(producer, consumers) as lineWorker:
...     lineWorker.work() # doctest: +ELLIPSIS
line ...

The with statement makes sure that all threads are terminated once the worker
finished or failed. Alternatively you can use ``try ... except ... finally``
to handle errors and cleanup:

>>> producer =  LineProducer(__file__)
>>> consumers = [LineConsumer("consumer#%d" % consumerId)
...         for consumerId in xrange(3)]
>>> lineWorker = proconex.Worker(producer, consumers)
>>> try:
...     lineWorker.work()
... except Exception, error:
...     print error
... finally:
...    lineWorker.close() # doctest: +ELLIPSIS
line ...

Limitations
===========

When using proconex, there are a few things you should be aware of:

* Due to Python's Global Interpreter Lock (GIL), at least one of producer and
   consumer should be I/O bound in order to allow thread switches.
* The code contains a few polling loops because ``Queue`` does
   not support canceling `get()` and `put()`. However, the polling does not
   drain the CPU because it uses a timeout when waiting for events to happen.
* The only way to recover from errors during production is to restart the
   whole process from the beginning.

If you need more flexibility and control than proconex offers, try
`celery <http://celeryproject.org/>`_.

Source code
===========

Proconex is distributed under the GNU Lesser General Public License, version 3
or later.

The source code is available from <https://github.com/roskakori/proconex>.

Version history
===============

Version 0.3, 2012-01-05

* ...

Version 0.2, 2012-01-04

* Added support for multiple producers.
* Added limit for queue size. By default it is twice the number of consumers.

Version 0.1, 2012-01-03

* Initial public release.
"""
# Copyright (C) 2012 Thomas Aglassinger
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public
# License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
from __future__ import with_statement

import logging
import Queue
import threading

__version__ = "0.2"

# Delay in seconds for ugly polling hacks.
_HACK_DELAY = 0.02

_log = logging.getLogger("proconex")


class WorkEnv(object):
    """
    Environment in which production and consumption takes place and
    information about a possible error is stored.
    """
    def __init__(self, queueSize):
        self._queue = Queue.Queue(queueSize)
        self._error = None
        self._failedConsumers = Queue.Queue()

    def fail(self, failedConsumer, error):
        """
        Inform environment that ``consumer`` failed because of ``error``.
        """
        assert failedConsumer is not None
        assert error is not None
        self._error = error
        self._failedConsumers.put(failedConsumer)

    def possiblyRaiseError(self):
        """"Provided that `hasFailed` raise `error`, otherwise do nothing."""
        if self.hasFailed:
            _log.debug(u"raising notified error: %s", self.error)
            raise self.error

    @property
    def hasFailed(self):
        """``True`` after `fail()` has been called."""
        return not self._failedConsumers.empty()

    @property
    def queue(self):
        """Queue containing items exchanged between producers and consumers."""
        return self._queue

    @property
    def error(self):
        """First error that prevents work from continuing."""
        return self._error


class _CancelableThread(threading.Thread):
    """
    Thread that can be canceled using `cancel()`.
    """
    def __init__(self, name):
        assert name is not None

        super(_CancelableThread, self).__init__(name=name)
        self._log = logging.getLogger(u"proconex.%s" % name)
        self._isCanceled = False
        self.workEnv = None

    def cancel(self):
        self._isCanceled = True

    @property
    def isCanceled(self):
        return self._isCanceled

    @property
    def log(self):
        return self._log


class Producer(_CancelableThread):
    """
    Producer putting items on a `WorkEnv`'s queue.
    """
    def __init__(self, name="producer"):
        assert name is not None

        super(Producer, self).__init__(name)

    def items(self):
        """
        A sequence of items to produce. Typically this is implemented as
        generator.
        """
        raise NotImplementedError()

    def run(self):
        """
        Process `items()`. Normally there is no need to modify this procedure.
        """
        assert self.workEnv is not None
        try:
            for item in self.items():
                itemHasBeenPut = False
                while not itemHasBeenPut:
                    self.workEnv.possiblyRaiseError()
                    try:
                        self.workEnv.queue.put(item, True, _HACK_DELAY)
                        itemHasBeenPut = True
                    except Queue.Full:
                        pass
        except Exception, error:
            self.log.warning(u"cannot continue to produce: %s", error)
            self.workEnv.fail(self, error)


class Consumer(_CancelableThread):
    """
    Thread to consume items from an item queue filled by a producer, which can
    be told to terminate in two ways:

    1. using `finish()`, which keeps processing the remaining items on the
       queue until it is empty
    2. using `cancel()`, which finishes consuming the current item and then
       terminates
    """
    def __init__(self, name="consumer"):
        assert name is not None

        super(Consumer, self).__init__(name)
        self._isFinishing = False
        self.log.debug(u"waiting for items to consume")

    def finish(self):
        self._isFinishing = True

    def consume(self, item):
        raise NotImplementedError("Consumer.consume()")

    def run(self):
        assert self.workEnv is not None
        try:
            while not (self._isFinishing and self.workEnv.queue.empty()) \
                    and not self._isCanceled:
                # HACK: Use a timeout when getting the item from the queue
                # because between `empty()` and `get()` another consumer might
                # have removed it.
                try:
                    item = self.workEnv.queue.get(timeout=_HACK_DELAY)
                    self.consume(item)
                except Queue.Empty:
                    pass
            if self._isCanceled:
                self.log.debug(u"canceled")
            if self._isFinishing:
                self.log.debug(u"finished")
        except Exception, error:
            self.log.warning(u"cannot continue to consume: %s", error)
            self.workEnv.fail(self, error)


class Worker(object):
    """
    Controller for interaction between producers and consumers.
    """
    def __init__(self, producers, consumers, queueSize=None):
        assert producers is not None
        assert consumers is not None

        # TODO: Consider using tuples instead of lists for producers and
        # consumers.
        if isinstance(producers, Producer):
            self._producers = [producers]
        else:
            self._producers = list(producers)
        if isinstance(consumers, Consumer):
            self._consumers = [consumers]
        else:
            self._consumers = list(consumers)
        if queueSize is None:
            actualQueueSize = 2 * len(self._consumers)
        else:
            actualQueueSize = queueSize
        self._workEnv = WorkEnv(actualQueueSize)

    def _cancelThreads(self, name, threadsToCancel):
        assert name
        if threadsToCancel is not None:
            _log.debug(u"canceling all %s", name)
            for threadToCancel in threadsToCancel:
                threadToCancel.cancel()
            _log.debug(u"waiting for %s to be canceled", name)
            for possiblyCanceledThread in threadsToCancel:
                # In this case, we ignore possible errors because there
                # already is an error to report.
                possiblyCanceledThread.join(_HACK_DELAY)
                if possiblyCanceledThread.isAlive():
                    threadsToCancel.append(possiblyCanceledThread)

    def _cancelAllConsumersAndProducers(self):
        self._cancelThreads("consumers", self._consumers)
        self.consumers = None
        self._cancelThreads("producers", self._producers)
        self._producers = None

    def work(self):
        """
        Launch consumer threads and produce items. In case any consumer or the
        producer raise an exception, fail by raising this exception.
        """
        assert self._consumers is not None, "work() must be called only once"

        _log.debug(u"starting consumers")
        for consumerToStart in self._consumers:
            consumerToStart.workEnv = self._workEnv
            consumerToStart.start()
        _log.debug(u"starting producers")
        for producerToStart in self._producers:
            producerToStart.workEnv = self._workEnv
            producerToStart.start()

        _log.debug(u"waiting for producers to finish")
        for possiblyFinishedProducer in self._producers:
            self._workEnv.possiblyRaiseError()
            while possiblyFinishedProducer.isAlive():
                possiblyFinishedProducer.join(_HACK_DELAY)
                self._workEnv.possiblyRaiseError()
        self._producers = None

        _log.debug(u"telling consumers to finish the remaining items")
        for consumerToFinish in self._consumers:
            consumerToFinish.finish()
        _log.debug(u"waiting for consumers to finish")
        for possiblyFinishedConsumer in self._consumers:
            self._workEnv.possiblyRaiseError()
            possiblyFinishedConsumer.join(_HACK_DELAY)
            if possiblyFinishedConsumer.isAlive():
                self._consumers.append(possiblyFinishedConsumer)
        self._consumers = None

    def close(self):
        """
        Close the whole production and consumption, releasing all resources
        and stopping all threads (in case there are still any running).

        The simplest way to call this is by wrapping the worker in a ``with``
        statement.
        """
        self._cancelAllConsumersAndProducers()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


if __name__ == "__main__":
    import doctest
    doctest.testmod()
