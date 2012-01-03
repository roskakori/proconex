"""
Consumer/producer to test exception handling in threads. Both the producer
and the consumer can be made to fail deliberately when processing a certain
item using command line options.
"""
from __future__ import with_statement

import logging
import Queue
import threading

# Delay in seconds for ugly polling hacks.
_HACK_DELAY = 0.02

_log = logging.getLogger("proconex")


class WorkEnv(object):
    """
    Environment in which production and consumption takes place and
    information about a possible error is stored.
    """
    def __init__(self):
        self._queue = Queue.Queue()
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
            _log.info(u"raising notified error: %s", self.error)
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


class Producer(object):
    """
    Producer putting items on a `WorkEnv`'s queue.
    """
    def items(self):
        """
        A sequence of items to produce. Typically this is implemented as
        generator.
        """
        raise NotImplementedError()

    def produce(self, workEnv):
        """
        Process `items()`. Normally there is no need to modify this procedure.
        """
        assert workEnv is not None
        for item in self.items():
            workEnv.possiblyRaiseError()
            workEnv.queue.put(item)


class Consumer(threading.Thread):
    """
    Thread to consume items from an item queue filled by a producer, which can
    be told to terminate in two ways:

    1. using `finish()`, which keeps processing the remaining items on the
       queue until it is empty
    2. using `cancel()`, which finishes consuming the current item and then
       terminates
    """
    def __init__(self, name):
        assert name is not None

        super(Consumer, self).__init__(name=name)
        self._log = logging.getLogger(name)
        self.itemToFailAt = None
        self._isFinishing = False
        self._isCanceled = False
        self._workEnv = None
        self._log.info(u"waiting for items to consume")

    def finish(self):
        self._isFinishing = True

    def cancel(self):
        self._isCanceled = True

    def consume(self, item):
        raise NotImplementedError("Consumer.consume()")

    def run(self):
        assert self._workEnv is not None
        try:
            while not (self._isFinishing and self._workEnv.queue.empty()) \
                    and not self._isCanceled:
                # HACK: Use a timeout when getting the item from the queue
                # because between `empty()` and `get()` another consumer might
                # have removed it.
                try:
                    item = self._workEnv.queue.get(timeout=_HACK_DELAY)
                    self.consume(item)
                except Queue.Empty:
                    pass
            if self._isCanceled:
                self._log.info(u"canceled")
            if self._isFinishing:
                self._log.info(u"finished")
        except Exception, error:
            self._log.error(u"cannot continue to consume: %s", error)
            self._workEnv.fail(self, error)


class Worker(object):
    """
    Controller for interaction between producer and consumers.
    """
    def __init__(self, producer, consumers):
        assert producer is not None
        assert consumers is not None

        self._producer = producer
        self._consumers = consumers
        self._workEnv = WorkEnv()

    def _cancelAllConsumers(self):
        if self._consumers is not None:
            _log.info(u"canceling all consumers")
            for consumerToCancel in self._consumers:
                consumerToCancel.cancel()
            _log.info(u"waiting for consumers to be canceled")
            for possiblyCanceledConsumer in self._consumers:
                # In this case, we ignore possible consumer errors because
                # there already is an error to report.
                possiblyCanceledConsumer.join(_HACK_DELAY)
                if possiblyCanceledConsumer.isAlive():
                    self._consumers.append(possiblyCanceledConsumer)
        self.consumers = None

    def work(self):
        """
        Launch consumer threads and produce items. In case any consumer or the
        producer raise an exception, fail by raising this exception.
        """
        assert self._consumers is not None, "work() must be called only once"

        for consumerToStart in self._consumers:
            consumerToStart._workEnv = self._workEnv
            consumerToStart.start()
        self._producer.produce(self._workEnv)

        _log.info(u"telling consumers to finish the remaining items")
        for consumerToFinish in self._consumers:
            consumerToFinish.finish()
        _log.info(u"waiting for consumers to finish")
        for possiblyFinishedConsumer in self._consumers:
            self._workEnv.possiblyRaiseError()
            possiblyFinishedConsumer.join(_HACK_DELAY)
            if possiblyFinishedConsumer.isAlive():
                self._consumers.append(possiblyFinishedConsumer)
        self._consumers = None

    def close(self):
        """
        Close the whole production and consumption, releasing all resources
        and stopping all threads.

        The simplest way to call this is by wrapping the worker in a ``with``
        statement, for example:

        >>> with Worker(...) as worker:
        ...    worker.work()
        """
        self._cancelAllConsumers()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
