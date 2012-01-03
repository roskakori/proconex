"""
Consumer/producer to test exception handling in threads. Both the producer
and the consumer can be made to fail deliberately when processing a certain
item using command line options.
"""
from __future__ import with_statement

import logging
import optparse
import Queue
import threading
import time

_PRODUCTION_DELAY = 0.1
_CONSUMPTION_DELAY = 0.3

# Delay for ugly hacks and polling loops.
_HACK_DELAY = 0.05

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


class Consumer(threading.Thread):
    """
    Thread to consume items from an item queue filled by a producer, which can
    be told to terminate in two ways:

    1. using `finish()`, which keeps processing the remaining items on the
       queue until it is empty
    2. using `cancel()`, which finishes consuming the current item and then
       terminates
    """
    def __init__(self, name, workEnv):
        assert name is not None
        assert workEnv is not None

        super(Consumer, self).__init__(name=name)
        self._log = logging.getLogger(name)
        self._workEnv = workEnv
        self.itemToFailAt = None
        self._log.info(u"waiting for items to consume")
        self._isFinishing = False
        self._isCanceled = False

    def finish(self):
        self._isFinishing = True

    def cancel(self):
        self._isCanceled = True

    def consume(self, item):
        self._log.info(u"consume item %d", item)
        if item == self.itemToFailAt:
            raise ValueError("cannot consume item %d" % item)
        time.sleep(_CONSUMPTION_DELAY)

    def run(self):
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


class Producer(object):
    def items(self):
        raise NotImplementedError()

    def produce(self, workEnv):
        assert workEnv is not None
        for item in self.items():
            workEnv.possiblyRaiseError()
            workEnv.queue.put(item)


class SleepyIntegerProducer(Producer):
    def __init__(self, itemCount, itemProducerFailsAt=None):
        assert itemCount >= 0
        assert (itemProducerFailsAt is None) or (itemProducerFailsAt >= 0)
        self._itemCount = itemCount
        self._itemProducerFailsAt = itemProducerFailsAt
        self._log = logging.getLogger("producer")

    def items(self):
        self._log.info(u"producing %d items", self._itemCount)
        for item in xrange(self._itemCount):
            self._log.info(u"produce item %d", item)
            time.sleep(_PRODUCTION_DELAY)
            if item == self._itemProducerFailsAt:
                raise ValueError(u"cannot produce item %d" % item)
            yield item


class Worker(object):
    """
    Controller for interaction between producer and consumers.
    """
    def __init__(self, itemsToProduceCount, itemProducerFailsAt,
            itemConsumerFailsAt, consumerCount):
        # Set up _consumers first so it is available for `__exit__()` even
        # when `__init__()` fails.
        self._consumers = None

        # Set up the remaining attributes.
        self._itemsToProduceCount = itemsToProduceCount
        self._itemProducerFailsAt = itemProducerFailsAt
        self._itemConsumerFailsAt = itemConsumerFailsAt
        self._consumerCount = consumerCount
        self._workEnv = WorkEnv()

    def _cancelAllConsumers(self):
        if self._consumers is not None:
            _log.info(u"canceling all consumers")
            for consumerToCancel in self._consumers:
                consumerToCancel.cancel()
            _log.info(u"waiting for consumers to be canceled")
            for possiblyCanceledConsumer in self._consumers:
                # In this case, we ignore possible consumer errors because there
                # already is an error to report.
                possiblyCanceledConsumer.join(_HACK_DELAY)
                if possiblyCanceledConsumer.isAlive():
                    self._consumers.append(possiblyCanceledConsumer)
        self.consumers = None

    def work(self):
        """
        Launch consumer threads and produce items. In case any consumer or the
        producer raise an exception, fail by raising this exception  
        """
        self._consumers = []
        for consumerId in range(self._consumerCount):
            consumerToStart = Consumer(u"consumer %d" % consumerId, self._workEnv)
            self._consumers.append(consumerToStart)
            consumerToStart.start()
            if self._itemConsumerFailsAt is not None:
                consumerToStart.itemToFailAt = self._itemConsumerFailsAt
        
        producer = SleepyIntegerProducer(self._itemsToProduceCount, self._itemProducerFailsAt)
        producer.produce(self._workEnv)
    
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = optparse.OptionParser()
    parser.add_option("-c", "--consumer-fails-at", metavar="NUMBER",
        type="long", help="number of items at which consumer fails (default: %default)")
    parser.add_option("-i", "--items", metavar="NUMBER", type="long",
        help="number of items to produce (default: %default)", default=10)
    parser.add_option("-n", "--consumers", metavar="NUMBER", type="long",
        help="number of consumers (default: %default)", default=2)
    parser.add_option("-p", "--producer-fails-at", metavar="NUMBER",
        type="long", help="number of items at which producer fails (default: %default)")
    options, others = parser.parse_args()
    worker = Worker(options.items, options.producer_fails_at,
        options.consumer_fails_at, options.consumers)
    with worker:
        try:
            worker.work()
            _log.info(u"processed all items")
        except KeyboardInterrupt:
            _log.warning(u"interrupted by user")
        except Exception, error:
            _log.error(u"%s", error)
