ProConEx is a module to simplify the implementation of the producer/consumer
idiom. In addition to simple implementations based on Python's Queue.Queue,
ProConEx also takes care of exceptions raised during producing or consuming
items and ensures that all the work shuts down in a clean manner without
leaving zombie threads.
