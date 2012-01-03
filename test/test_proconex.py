"""
Tests for `proconex`.
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
import optparse
import sys
import time
import unittest

import proconex

_PRODUCTION_DELAY = 0.1
_CONSUMPTION_DELAY = 0.3

_log = logging.getLogger("test_proconex")


class SleepyIntegerProducer(proconex.Producer):
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


class SleepyIntegerConsumer(proconex.Consumer):
    def __init__(self, name, itemConsumerFailsAt=None):
        super(SleepyIntegerConsumer, self).__init__(name)
        self._itemConsumerFailsAt = itemConsumerFailsAt

    def consume(self, item):
        self._log.info(u"consume item %d", item)
        if item == self._itemConsumerFailsAt:
            raise ValueError("cannot consume item %d" % item)
        time.sleep(_CONSUMPTION_DELAY)


def _createWorker(
        itemCount=10, producerFailsAt=None, consumerFailsAt=None,
        customerCount=2
    ):
    # Create producer and consumers.
    producer = SleepyIntegerProducer(itemCount, producerFailsAt)
    consumers = []
    for consumerId in xrange(customerCount):
        consumerToStart = SleepyIntegerConsumer(
            u"consumer %d" % consumerId,
            consumerFailsAt
        )
        consumers.append(consumerToStart)

    return proconex.Worker(producer, consumers)


class Test(unittest.TestCase):
    def testCanProduceAndConsume(self):
        worker = _createWorker(10, None,  None, 2)
        worker.work()

    def testCanProduceAndConsumeNothing(self):
        worker = _createWorker(0, None,  None, 2)
        worker.work()

    def testCanProduceLessThanAvailableConsumes(self):
        worker = _createWorker(5, None,  None, 10)
        worker.work()

    def testFailsOnConsumerError(self):
        worker = _createWorker(10, None,  3, 2)
        try:
            worker.work()
            self.fail("consumer must fail")
        except ValueError, error:
            self.assertTrue("consume" in unicode(error))
        finally:
            worker.close()

    def testFailsOnConsumerErrorAtLastItem(self):
        worker = _createWorker(10, None,  9, 2)
        try:
            worker.work()
            self.fail("consumer must fail")
        except ValueError, error:
            self.assertTrue("consume" in unicode(error))
        finally:
            worker.close()

    def testFailsOnProducerError(self):
        worker = _createWorker(10, 3, None, 2)
        try:
            worker.work()
            self.fail("producer must fail")
        except ValueError, error:
            self.assertTrue("produce" in unicode(error))
        finally:
            worker.close()

    def testCanRunMainWithDefaults(self):
        exitCode = main(["test_proconex"])
        self.assertEquals(exitCode, 0)


def main(argv=None):
    if argv is None:
        argv = sys.argv
    parser = optparse.OptionParser()
    parser.add_option("-c", "--consumer-fails-at", metavar="NUMBER",
        type="long",
        help="number of items at which consumer fails (default: %default)")
    parser.add_option("-i", "--items", metavar="NUMBER", type="long",
        help="number of items to produce (default: %default)", default=10)
    parser.add_option("-n", "--consumers", metavar="NUMBER", type="long",
        help="number of consumers (default: %default)", default=2)
    parser.add_option("-p", "--producer-fails-at", metavar="NUMBER",
        type="long",
        help="number of items at which producer fails (default: %default)")
    options, others = parser.parse_args(argv[1:])

    if others:
        parser.error(u"unknown options must be removed: %s" % others)

    # Create producer and consumers.
    producer = SleepyIntegerProducer(options.items, options.producer_fails_at)
    consumers = []
    for consumerId in xrange(options.consumers):
        consumerToStart = SleepyIntegerConsumer(
            u"consumer %d" % consumerId, options.consumer_fails_at
        )
        consumers.append(consumerToStart)

    exitCode = 1
    worker = proconex.Worker(producer, consumers)
    with worker:
        try:
            worker.work()
            _log.info(u"processed all items")
            exitCode = 0
        except KeyboardInterrupt:
            _log.warning(u"interrupted by user")
        except Exception, error:
            _log.error(u"%s", error)
    return exitCode


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # import sys;sys.argv = ['', 'Test.testFailsOnConsumerErrorAtLastItem']
    unittest.main()
