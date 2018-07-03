# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta
import logging
import pooler

from osv import osv, fields


class GiscedataPolissa(osv.osv):
    _name = 'giscedata.polissa'
    _inherit = 'giscedata.polissa'

    _columns = {
        'empowering_profile_id': fields.many2one(
            'empowering.customize.profile',
            'Empowering Profile'
        ),
        'empowering_channels_log': fields.one2many(
            'empowering.customize.profile.channel.log',
            'contract_id',
            'Empowering Log'
        )
    }

    def send_empowering_report(self, cursor, uid, reports, context=None):
        if context is None:
            context = {}

        logger = logging.getLogger('openerp.{0}.send_empowering_report'.format(
            __name__
        ))

        cl_obj = self.pool.get('empowering.customize.profile.channel.log')
        pe_send_obj = self.pool.get('poweremail.send.wizard')
        imd_obj = self.pool.get('ir.model.data')
        attach_obj = self.pool.get('ir.attachment')
        tmpl_obj = self.pool.get('poweremail.templates')

        for report in reports:
            polissa = self.browse(cursor, uid, report['contract_id'],
                context=context)
            if not polissa.empowering_profile_id:
                continue

            vals = {
                'name': report['report_name'],
                'datas': report['pdf'],
                'datas_fname': report['report_name'],
                'res_model': 'giscedata.polissa',
                'res_id': polissa.id
            }
            try:
                db = pooler.get_db_only(cursor.dbname)
                cr_new = None
                cr_new = db.cursor()
                attachment_id = attach_obj.create(cr_new, uid, vals, context)
                cr_new.commit()
            except:
                if not cr_new:
                    cr_new.rollback()
            finally:
                cr_new.close()
            now = datetime.now()
            for channel in polissa.empowering_profile_id.channels_ids:
                measure = channel.interval_id.measure
                number = channel.interval_id.number
                if measure and measure != 'on_demand':
                    cl = cl_obj.search_reader(cursor, uid, [
                        ('channel_id.id', '=', channel.id),
                        ('contract_id.id', '=', polissa.id)
                    ], ['last_generated'], order='last_generated desc', limit=1)
                    if cl:
                        last_generated = datetime.strptime(
                            cl[0]['last_generated'], '%Y-%m-%d %H:%M:%S'
                        )
                    else:
                        last_generated = datetime(1, 1, 1)
                    last_generated += relativedelta(**{measure: number})
                    if last_generated > now:
                        continue
                period = context.get('period')
                if not period:
                    period = now.strftime('%Y%m')
                body_common = context.get('body', '')
                body_personal = report.get('body', '')
                channel_code = channel.channel_id.code

                template_id = imd_obj.get_object_reference(
                    cursor, uid, 'empowering_customize', 'env_empowering_report'
                )[1]

                tmpl = tmpl_obj.browse(cursor, uid, template_id)

                ctx = context.copy()
                ctx.update({
                    'period': period,
                    'body_common': body_common,
                    'body_personal': body_personal,
                    'empowering_channel': channel_code,
                    'src_rec_ids': [polissa.id],
                    'src_model': 'giscedata.polissa',
                    'template_id': template_id,
                    'active_id': polissa.id
                })
                logger.info(
                    'Sending email to contract {polissa.name} channel: '
                    '{channel.code} ane period: {period}'.format(
                        polissa=polissa, channel=channel.channel_id,
                        period=period
                    )
                )
                send_id = pe_send_obj.create(cursor, uid, {}, context=ctx)
                pe_send_obj.write(cursor, uid, [send_id],
                    {'from': tmpl.enforce_from_account.id,
                     'attachment_ids': [(6, 0, [attachment_id])]}, context=ctx)
                sender = pe_send_obj.browse(cursor, uid, send_id, context=ctx)
                sender.send_mail(context=ctx)

    def poweremail_create_callback(self, cursor, uid, ids, vals, context=None):
        """Hook que cridarà el poweremail quan es creei un email
        a partir d'una pòlisssa.
        """
        if context is None:
            context = {}
        log_obj = self.pool.get('empowering.customize.profile.channel.log')
        channel_obj = self.pool.get('empowering.customize.profile.channel')
        channel_code = context.get('empowering_channel')
        period = context.get('period')
        if not channel_code:
            return True

        channel_id = channel_obj.search(cursor, uid, [
            ('channel_id.code', '=', channel_code)
        ])[0]
        folder = vals.get('folder', False)
        origin_ids = context.get('pe_callback_origin_ids', {})
        for polissa_id in ids:
            log_obj.create(cursor, uid, {
                'contract_id': polissa_id,
                'channel_id': channel_id,
                'period': period,
                'last_generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'mail_id': origin_ids.get(polissa_id, False),
                'date_sent': vals.get('date_mail'),
                'folder': folder,
                'sent': 1
            })
        return True

    def poweremail_write_callback(self, cursor, uid, ids, vals, context=None):
        """Hook que cridarà el poweremail quan es modifiqui un email.
        """
        if context is None:
            context = {}
        log_obj = self.pool.get('empowering.customize.profile.channel.log')
        if 'date_mail' in vals and 'folder' in vals:
            vals_w = {
                'date_sent': vals['date_mail'],
                'folder': vals['folder']
            }
            origin_ids = context.get('pe_callback_origin_ids', {})
            if vals_w:
                for polissa_id in ids:
                    mail_id = origin_ids.get(polissa_id, False)
                    if mail_id:
                        log_id = log_obj.search(cursor, uid, [
                            ('contract_id.id', '=', polissa_id),
                            ('mail_id.id', '=', mail_id)
                        ])
                        if log_id:
                            log_obj.write(cursor, uid, log_id, vals_w)
        return True


GiscedataPolissa()
