"""
Consumer/producer to test exception handling in threads. Both the producer
and the consumer can be made to fail deliberately when processing a certain
item using command line options.
"""
import logging
import optparse
import Queue
import threading
import time

_PRODUCTION_DELAY = 0.1
_CONSUMPTION_DELAY = 0.3

# Delay for ugly hacks and polling loops.
_HACK_DELAY = 0.05

class _Consumer(threading.Thread):
    """
    Thread to consume items from an item queue filled by a producer, which can
    be told to terminate in two ways:

    1. using `finish()`, which keeps processing the remaining items on the
       queue until it is empty
    2. using `cancel()`, which finishes consuming the current item and then
       terminates
    """
    def __init__(self, name, itemQueue, failedConsumers):
        super(_Consumer, self).__init__(name=name)
        self._log = logging.getLogger(name)
        self._itemQueue = itemQueue
        self._failedConsumers = failedConsumers
        self.error = None
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
            while not (self._isFinishing and self._itemQueue.empty()) \
                    and not self._isCanceled:
                # HACK: Use a timeout when getting the item from the queue
                # because between `empty()` and `get()` another consumer might
                # have removed it.
                try:
                    item = self._itemQueue.get(timeout=_HACK_DELAY)
                    self.consume(item)
                except Queue.Empty:
                    pass
            if self._isCanceled:
                self._log.info(u"canceled")
            if self._isFinishing:
                self._log.info(u"finished")
        except Exception, error:
            self._log.error(u"cannot continue to consume: %s", error)
            self.error = error
            self._failedConsumers.put(self)

        
class Worker(object):
    """
    Controller for interaction between producer and consumers.
    """
    def __init__(self, itemsToProduceCount, itemProducerFailsAt,
            itemConsumerFailsAt, consumerCount):
        self._itemsToProduceCount = itemsToProduceCount
        self._itemProducerFailsAt = itemProducerFailsAt
        self._itemConsumerFailsAt = itemConsumerFailsAt
        self._consumerCount = consumerCount
        self._itemQueue = Queue.Queue()
        self._failedConsumers = Queue.Queue()
        self._log = logging.getLogger("producer")
        self._consumers = []

    def _possiblyRaiseConsumerError(self):
            if not self._failedConsumers.empty():
                failedConsumer = self._failedConsumers.get()
                self._log.info(u"handling failed %s", failedConsumer.name)
                raise failedConsumer.error

    def _cancelAllConsumers(self):
        self._log.info(u"canceling all consumers")
        for consumerToCancel in self._consumers:
            consumerToCancel.cancel()
        self._log.info(u"waiting for consumers to be canceled")
        for possiblyCanceledConsumer in self._consumers:
            # In this case, we ignore possible consumer errors because there
            # already is an error to report.
            possiblyCanceledConsumer.join(_HACK_DELAY)
            if possiblyCanceledConsumer.isAlive():
                self._consumers.append(possiblyCanceledConsumer)
        
    def work(self):
        """
        Launch consumer thread and produce items. In case any consumer or the
        producer raise an exception, fail by raising this exception  
        """
        self.consumers = []
        for consumerId in range(self._consumerCount):
            consumerToStart = _Consumer(u"consumer %d" % consumerId,
                self._itemQueue, self._failedConsumers)
            self._consumers.append(consumerToStart)
            consumerToStart.start()
            if self._itemConsumerFailsAt is not None:
                consumerToStart.itemToFailAt = self._itemConsumerFailsAt
        
        self._log = logging.getLogger("producer  ")
        self._log.info(u"producing %d items", self._itemsToProduceCount)
    
        for itemNumber in range(self._itemsToProduceCount):
            self._possiblyRaiseConsumerError()
            self._log.info(u"produce item %d", itemNumber)
            if itemNumber == self._itemProducerFailsAt:
                raise ValueError("ucannot produce item %d" % itemNumber)
            # Do the actual work.
            time.sleep(_PRODUCTION_DELAY)
            self._itemQueue.put(itemNumber)

        self._log.info(u"telling consumers to finish the remaining items")
        for consumerToFinish in self._consumers:
            consumerToFinish.finish()
        self._log.info(u"waiting for consumers to finish")
        for possiblyFinishedConsumer in self._consumers:
            self._possiblyRaiseConsumerError()
            possiblyFinishedConsumer.join(_HACK_DELAY)
            if possiblyFinishedConsumer.isAlive():
                self._consumers.append(possiblyFinishedConsumer)


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
    try:
        worker.work()
        logging.info(u"processed all items")
    except KeyboardInterrupt:
        logging.warning(u"interrupted by user")
        worker._cancelAllConsumers()
    except Exception, error:
        logging.error(u"%s", error)
        worker._cancelAllConsumers()
