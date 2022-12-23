from pymongo import MongoClient
from datetime import datetime

import os

from config import Config


class DbClient:

    def connect(self):
        config = Config()

        print(f'Connecting to DB at {config.MongoConnectionString}...')

        self.client = MongoClient(config.MongoConnectionString)
        self.client.server_info()

        self.db = self.client.get_database('asa')

        print('Successfully connected to DB')

        return self

    def insert_audit_record(self, record):
        record['insertDate'] = datetime.today()
        self.db.get_collection('audits').insert_one(record)

    def url_has_entry(self, url):
        return self.db.get_collection('audits').find_one({'url': url}) is not None

    def get_urls_by_host(self):

        return self.db.get_collection('audits').aggregate([
            {
                '$unwind': {
                    'path': '$host',
                    'includeArrayIndex': 'string',
                    'preserveNullAndEmptyArrays': False
                }
            }, {
                '$group': {
                    '_id': '$host',
                    'count': {
                        '$count': {}
                    },
                    'urls': {
                        '$addToSet': {
                            'url': '$url',
                            'audits': '$lighthouse.audits',
                            'scores': {
                                'performance': '$lighthouse.categories.performance.score'
                            }
                        }
                    }
                }
            }
        ], allowDiskUse=True)
    
    def get_saved_urls_count(self):
        return self.db.get_collection('audits').count_documents({})

    
