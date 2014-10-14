#!/usr/bin/env python
# -*- coding: utf-8 -*-
import logging
import sys
import time

from .tasks import push_amon_measures, push_contracts
from .utils import Popper, setup_mongodb, setup_peek, setup_logging


setup_logging('/tmp/amon.log')
logger = logging.getLogger('amon')


if __name__ == '__main__':
    if sys.argv[1] == 'push_all_amon_measures':
        bucket = 500
        serials = open('serials', 'r')
        for serial in serials:
            meter_name = serial.replace('\n', '').strip()
            if not meter_name.startswith('ZIV00'):
                continue
            filters = {
                'name': meter_name,
                'type': 'day',
                'value': 'a',
                'valid': True,
                'period': 0
            }
            mongo = setup_mongodb()
            collection = mongo['tg_billing']
            measures = collection.find(filters, {'id': 1})
            measures_to_push = []
            for idx, measure in enumerate(measures):
                if idx and not idx % bucket:
                    j = push_amon_measures.delay(measures_to_push)
                    logger.info("Job id:%s | %s/%s/%s" % (
                        j.id, meter_name, idx, bucket)
                    )
                    time.sleep(0.1)
                    measures_to_push = []
                measures_to_push.append(measure['id'])
        mongo.connection.disconnect()

    elif sys.argv[1] == 'push_all_contracts':
        O = setup_peek()
        cids = O.GiscedataLecturesComptador.search([('tg', '=', 1)], 0, 0, False, {'active_test': False})
        contracts_ids = [
            x['polissa'][0]
            for x in O.GiscedataLecturesComptador.read(cids, ['polissa'])
        ]
        contracts_ids = list(set(contracts_ids))
        contracts_ids = O.GiscedataPolissa.search([
            ('id', 'in', contracts_ids),
            ('state', 'not in', ('esborrany', 'validar'))
        ])
        popper = Popper(contracts_ids)
        bucket = 500
        pops = popper.pop(bucket)
        while pops:
            j = push_contracts.delay(pops)
            logger.info("Job id:%s" % j.id) 
            pops = popper.pop(bucket)
