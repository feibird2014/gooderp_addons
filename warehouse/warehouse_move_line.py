# -*- coding: utf-8 -*-

from openerp.osv import osv
import openerp.addons.decimal_precision as dp
from utils import safe_division
from jinja2 import Environment, PackageLoader
from openerp import models, fields, api

env = Environment(loader=PackageLoader('openerp.addons.warehouse', 'html'), autoescape=True)


class wh_move_line(models.Model):
    _name = 'wh.move.line'

    _rec_name = 'note'

    MOVE_LINE_TYPE = [
        ('out', u'出库'),
        ('in', u'入库'),
        ('internal', u'内部调拨'),
    ]

    MOVE_LINE_STATE = [
        ('draft', u'草稿'),
        ('done', u'已审核'),
    ]

    ORIGIN_EXPLAIN = {
        ('wh.assembly', 'out'): u'组装单子件',
        ('wh.assembly', 'in'): u'组装单组合件',
        ('wh.disassembly', 'out'): u'拆卸单组合件',
        ('wh.disassembly', 'in'): u'拆卸单子件',
        ('wh.internal', True): u'调拨出库',
        ('wh.internal', False): u'调拨入库',
        'wh.out.inventory': u'盘亏',
        'wh.out.others': u'其他出库',
        'wh.in.inventory': u'盘盈',
        'wh.in.others': u'其他入库',
        'buy.receipt.sell': u'采购入库',
        'buy.receipt.return': u'采购退货',
        'sell.delivery.sell': u'销售出库',
        'sell.delivery.return': u'销售退货',
    }

    @api.one
    @api.depends('goods_qty', 'price_taxed', 'discount_amount', 'tax_rate')
    def _compute_all_amount(self):
        '''当订单行的数量、含税单价、折扣额、税率改变时，改变金额、税额、价税合计'''
        self.price = self.price_taxed / (1 + self.tax_rate * 0.01)
        self.amount = self.goods_qty * self.price - self.discount_amount  # 折扣后金额
        self.tax_amount = self.amount * self.tax_rate * 0.01  # 税额
        self.subtotal = self.amount + self.tax_amount

    @api.one
    @api.depends('goods_id')
    def _compute_using_attribute(self):
        self.using_attribute = self.goods_id.attribute_ids and True or False
    
    @api.one
    @api.depends('move_id.warehouse_id')
    def _get_line_warehouse(self):
        self.warehouse_id = self.move_id.warehouse_id.id
        if (self.move_id.origin == 'wh.assembly' or self.move_id.origin == 'wh.disassembly') and self.type == 'in':
            self.warehouse_id = self.env.ref('warehouse.warehouse_production').id

    @api.one
    @api.depends('move_id.warehouse_dest_id')
    def _get_line_warehouse_dest(self):
        self.warehouse_dest_id = self.move_id.warehouse_dest_id.id
        if (self.move_id.origin == 'wh.assembly' or self.move_id.origin == 'wh.disassembly') and self.type == 'out':
            self.warehouse_dest_id = self.env.ref('warehouse.warehouse_production').id

    move_id = fields.Many2one('wh.move', string=u'移库单', ondelete='cascade',
                              help=u'出库/入库/移库单行对应的移库单')
    date = fields.Date(u'完成日期', copy=False,
                       help=u'单据完成日期')
    cost_time = fields.Datetime(u'审核时间', copy=False,
                                help=u'单据审核时间')
    type = fields.Selection(MOVE_LINE_TYPE, u'类型', default=lambda self: self.env.context.get('type'),
                            help=u'类型：出库、入库 或者 内部调拨')
    state = fields.Selection(MOVE_LINE_STATE, u'状态', copy=False, default='draft',
                             help=u'状态标识，新建时状态为草稿;审核后状态为已审核')
    goods_id = fields.Many2one('goods', string=u'产品', required=True,
                               index=True, ondelete='restrict',
                               help=u'该单据行对应的产品')
    using_attribute = fields.Boolean(compute='_compute_using_attribute', string=u'使用属性',
                                     help=u'该单据行对应的产品是否存在属性，存在True否则False')
    attribute_id = fields.Many2one('attribute', u'属性', ondelete='restrict',
                                   help=u'该单据行对应的产品的属性')
    using_batch = fields.Boolean(related='goods_id.using_batch', string=u'批号管理',
                                 help=u'该单据行对应的产品是否使用批号管理')
    force_batch_one = fields.Boolean(related='goods_id.force_batch_one', string=u'每批号数量为1',
                                     help=u'该单据行对应的产品是否每批号数量为1,是True否则False')
    lot = fields.Char(u'批号',
                      help=u'该单据行对应的产品的批号，一般是入库单行')
    lot_id = fields.Many2one('wh.move.line', u'批号',
                             help=u'该单据行对应的产品的批号，一般是出库单行')
    lot_qty = fields.Float(related='lot_id.qty_remaining', string=u'批号数量',
                           digits=dp.get_precision('Quantity'),
                           help=u'该单据行对应的产品批号的商品剩余数量')
    lot_uos_qty = fields.Float(u'批号辅助数量',
                           digits=dp.get_precision('Quantity'),
                               help=u'该单据行对应的产品的批号辅助数量')
    production_date = fields.Date(u'生产日期', default=fields.Date.context_today,
                                  help=u'产品的生产日期')
    shelf_life = fields.Integer(u'保质期(天)',
                                help=u'产品的保质期(天)')
    valid_date = fields.Date(u'有效期至',
                             help=u'产品的有效期')
    uom_id = fields.Many2one('uom', string=u'单位', ondelete='restrict',
                             help=u'产品的计量单位')
    uos_id = fields.Many2one('uom', string=u'辅助单位', ondelete='restrict',
                             help=u'产品的辅助单位')
    warehouse_id = fields.Many2one('warehouse', u'调出仓库',
                                   ondelete='restrict',
                                   store=True,
                                   compute=_get_line_warehouse,
                                   help=u'单据的来源仓库')
    warehouse_dest_id = fields.Many2one('warehouse', u'调入仓库',
                                        ondelete='restrict',
                                        store=True,
                                        compute=_get_line_warehouse_dest,
                                        help=u'单据的目的仓库')
    goods_qty = fields.Float(u'数量', digits=dp.get_precision('Quantity'), default=1,
                             help=u'产品的数量')
    goods_uos_qty = fields.Float(u'辅助数量', digits=dp.get_precision('Quantity'),
                                 default=1, help=u'产品的辅助数量')
    price = fields.Float(u'单价', compute=_compute_all_amount,
                         store=True, readonly=True,
                         digits=dp.get_precision('Amount'),
                         help=u'产品的单价')
    price_taxed = fields.Float(u'含税单价',
                               digits=dp.get_precision('Amount'),
                               help=u'产品的含税单价')
    discount_rate = fields.Float(u'折扣率%',
                                 help=u'单据的折扣率%')
    discount_amount = fields.Float(u'折扣额',
                                   digits=dp.get_precision('Amount'),
                                   help=u'单据的折扣额')
    amount = fields.Float(u'金额',compute=_compute_all_amount, store=True, readonly=True,
                          digits=dp.get_precision('Amount'),
                          help=u'单据的金额,计算得来')
    tax_rate = fields.Float(u'税率(%)',
                            help=u'单据的税率(%)')
    tax_amount = fields.Float(u'税额', compute=_compute_all_amount, store=True, readonly=True,
                              digits=dp.get_precision('Amount'),
                              help=u'单据的税额,有单价×数量×税率计算得来')
    subtotal = fields.Float(u'价税合计', compute=_compute_all_amount, store=True, readonly=True,
                            digits=dp.get_precision('Amount'),
                            help=u'价税合计,有不含税金额+税额计算得来')
    note = fields.Text(u'备注',
                       help=u'可以为该单据添加一些需要的标识信息')
    cost_unit = fields.Float(u'单位成本', digits=dp.get_precision('Amount'),
                             help=u'入库/出库单位成本')
    cost = fields.Float(u'成本', compute='_compute_cost', inverse='_inverse_cost',
                        digits=dp.get_precision('Amount'), store=True,
                        help=u'入库/出库成本')

    @api.one
    @api.depends('cost_unit', 'goods_qty')
    def _compute_cost(self):
        self.cost = self.cost_unit * self.goods_qty

    @api.one
    def _inverse_cost(self):
        self.cost_unit = safe_division(self.cost, self.goods_qty)

    def get_origin_explain(self):
        self.ensure_one()
        if self.move_id.origin in ('wh.assembly', 'wh.disassembly'):
            return self.ORIGIN_EXPLAIN.get((self.move_id.origin, self.type))
        elif self.move_id.origin == 'wh.internal':
            return self.ORIGIN_EXPLAIN.get((self.move_id.origin, self.env.context.get('internal_out', False)))
        elif self.move_id.origin in self.ORIGIN_EXPLAIN.keys():
            return self.ORIGIN_EXPLAIN.get(self.move_id.origin)

        return ''

    @api.model
    def default_get(self, fields):
        res = super(wh_move_line, self).default_get(fields)
        if self.env.context.get('goods_id') and self.env.context.get('warehouse_id'):
            res.update({
                'goods_id': self.env.context.get('goods_id'),
                'warehouse_id': self.env.context.get('warehouse_id')
            })

        return res

    def get_real_cost_unit(self):
        self.ensure_one()
        return safe_division(self.cost, self.goods_qty)

    @api.multi
    def name_get(self):
        res = []
        for line in self:
            if self.env.context.get('match'):
                res.append((line.id, '%s-%s->%s(%s, %s%s)' %
                    (line.move_id.name, line.warehouse_id.name, line.warehouse_dest_id.name,
                        line.goods_id.name, str(line.goods_qty), line.uom_id.name)))
            else:
                res.append((line.id, line.lot))
        return res
    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        ''' 批号下拉的时候显示批次和剩余数量 '''
        result = []
        domain = []
        if args:
            domain = args
        if name:
            domain.append(('lot',operator,name))
        records = self.search(domain,limit=limit)
        for line in records:
            result.append((line.id, u'%s %s 余 %s' % (line.lot, line.warehouse_dest_id.name, line.qty_remaining)))
        return result

    def check_availability(self):
        if self.warehouse_dest_id == self.warehouse_id:
            raise osv.except_osv(u'错误', u'调出仓库不可以和调入仓库一样')

    def prev_action_done(self):
        pass

    @api.multi
    def action_done(self):
        for line in self:
            line.check_availability()
            line.prev_action_done()
            line.write({
                'state': 'done',
                'date': line.move_id.date,
                'cost_time': fields.Datetime.now(self),
            })

    def check_cancel(self):
        pass

    def prev_action_cancel(self):
        pass

    @api.multi
    def action_cancel(self):
        for line in self:
            line.check_cancel()
            line.prev_action_cancel()
            line.write({
                'state': 'draft',
                'date': False,
            })

    @api.one
    def compute_lot_compatible(self):
        if self.warehouse_id and self.lot_id and self.lot_id.warehouse_dest_id != self.warehouse_id:
            self.lot_id = False

        if self.goods_id and self.lot_id and self.lot_id.goods_id != self.goods_id:
            self.lot_id = False

    def compute_lot_domain(self):
        lot_domain = [('goods_id', '=', self.goods_id.id), ('state', '=', 'done'),
            ('lot', '!=', False), ('qty_remaining', '>', 0)]

        if self.move_id:
            lot_domain.append(('warehouse_dest_id', '=', self.move_id.warehouse_id.id))

        if self.attribute_id:
            lot_domain.append(('attribute_id', '=', self.attribute_id.id))

        return lot_domain

    @api.one
    def compute_suggested_cost(self):
        if self.env.context.get('type') == 'out' and self.goods_id and self.warehouse_id and self.goods_qty:
            cost, cost_unit = self.goods_id.get_suggested_cost_by_warehouse(
                self.warehouse_id, self.goods_qty, self.lot_id, self.attribute_id)

            self.cost_unit = cost_unit
            self.cost = cost

    @api.multi
    @api.onchange('goods_id')
    def onchange_goods_id(self):
        if self.goods_id:
            self.uom_id = self.goods_id.uom_id
            self.uos_id = self.goods_id.uos_id
            self.attribute_id = False
            self.cost_unit = self.goods_id.cost
            if self.goods_id.using_batch and self.goods_id.force_batch_one:
                self.goods_qty = 1
                self.goods_uos_qty = self.goods_id.anti_conversion_unit(
                    self.goods_qty)
            else:
                self.goods_qty = self.goods_id.conversion_unit(
                    self.goods_uos_qty or 1)

        self.compute_suggested_cost()
        self.compute_lot_compatible()

        return {'domain': {'lot_id': self.compute_lot_domain()}}

    @api.multi
    @api.onchange('warehouse_id')
    def onchange_warehouse_id(self):
        self.compute_suggested_cost()
        self.compute_lot_domain()
        self.compute_lot_compatible()

        return {'domain': {'lot_id': self.compute_lot_domain()}}

    @api.multi
    @api.onchange('attribute_id')
    def onchange_attribute_id(self):
        self.compute_suggested_cost()
        return {'domain': {'lot_id': self.compute_lot_domain()}}

    @api.one
    @api.onchange('goods_qty')
    def onchange_goods_qty(self):
        self.compute_suggested_cost()

    @api.one
    @api.onchange('goods_uos_qty')
    def onchange_goods_uos_qty(self):
        if self.goods_id:
            self.goods_qty = self.goods_id.conversion_unit(self.goods_uos_qty)
        self.compute_suggested_cost()

    @api.one
    @api.onchange('lot_id')
    def onchange_lot_id(self):
        if self.lot_id:
            self.lot_qty = self.lot_id.qty_remaining
            self.lot_uos_qty = self.goods_id.anti_conversion_unit(self.lot_qty)

            if self.env.context.get('type') == 'internal':
                self.lot = self.lot_id.lot

    @api.one
    @api.onchange('goods_qty', 'price_taxed', 'discount_rate')
    def onchange_discount_rate(self):
        '''当数量、单价或优惠率发生变化时，优惠金额发生变化'''
        price = self.price_taxed / (1 + self.tax_rate * 0.01)
        self.discount_amount = self.goods_qty * price * self.discount_rate * 0.01

    @api.multi
    def unlink(self):
        for line in self:
            if line.state == 'done':
                raise osv.except_osv(u'错误', u'不可以删除已经完成的明细')

        return super(wh_move_line, self).unlink()
