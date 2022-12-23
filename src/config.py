import os

class Config:
    def __init__(self):
        self.MongoConnectionString = os.getenv('MONGO_CONNECTION_STRING')
        self.AuditThreadPoolCount = int(os.getenv('AUDIT_THREAD_POOL_COUNT', 1))
        