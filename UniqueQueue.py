from queue import Queue

class UniqueQueue(Queue):

    def _init(self, maxsize):
        self.all_items = set()
        Queue._init(self, maxsize)

    def put(self, item, block=True, timeout=None):
        if not self.exists(item):
            self.all_items.add(item)
            Queue.put(self, item, block, timeout)
        else:
            raise 'Item already in queue'
        
    def exists(self, item):
        return item in self.all_items