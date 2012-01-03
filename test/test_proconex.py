"""
Tests for `proconex`.
"""
import logging
import unittest

import proconex

class Test(unittest.TestCase):
    def testCanProduceAndConsume(self):
        worker = proconex.Worker(10, None,  None, 2)
        worker.work()

    def testCanProduceAndConsumeNothing(self):
        worker = proconex.Worker(0, None,  None, 2)
        worker.work()

    def testCanProduceLessThanAvailableConsumes(self):
        worker = proconex.Worker(5, None,  None, 10)
        worker.work()

    def testFailsOnConsumerError(self):
        worker = proconex.Worker(10, None,  3, 2)
        try:
            worker.work()
            self.fail("consumer must fail")
        except ValueError, error:
            self.assertTrue("consume" in unicode(error))
        finally:
            worker.close()

    def testFailsOnConsumerErrorAtLastItem(self):
        worker = proconex.Worker(10, None,  9, 2)
        try:
            worker.work()
            self.fail("consumer must fail")
        except ValueError, error:
            self.assertTrue("consume" in unicode(error))
        finally:
            worker.close()

    def testFailsOnProducerError(self):
        worker = proconex.Worker(10, 3, None, 2)
        try:
            worker.work()
            self.fail("producer must fail")
        except ValueError, error:
            self.assertTrue("produce" in unicode(error))
        finally:
            worker.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # import sys;sys.argv = ['', 'Test.testFailsOnConsumerErrorAtLastItem']
    unittest.main()
