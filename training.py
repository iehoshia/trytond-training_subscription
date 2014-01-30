#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
from decimal import Decimal
from datetime import datetime
from trytond.model import Workflow, ModelView, ModelSQL, fields
from trytond.modules.company import CompanyReport
from trytond.pyson import If, Eval, PYSONEncoder, Date, Id
from trytond.transaction import Transaction
from trytond.pool import Pool, PoolMeta
import logging

_ZERO = Decimal(0)

STATES = {
    'readonly': (Eval('state') != 'draft'),
}

GUARANTEE = [
    ('payment', 'Payment'),
    ('voucher', 'Voucher'),
    ('credit_card', 'Credit Card'),
    ('letter', 'Letter'),
    ]

MEDIA = [
    ('', ''),
    ('web', 'Web'),
    ('yellow_pages', 'Paginas Amarillas'),
    ('recommended', 'Referido'),
    ('volante', 'Volante'),
    ('manta17', 'Manta 17'),
    ('mantas', 'Mantas ciudad '),
    ('other', 'Other'),
    ('llamada', 'Llamada')
    ]

INVOICE = [
    ('by_subscriptor', 'By Subscriptor'),
    ('by_student', 'By Student')
    ]

__all__ = ['TrainingSubscription', 'TrainingSubscriptionLine',
           'TrainingSubscriptionSale', 'TrainingSubscriptionInvoice',
           'TrainingSubscriptionHistory',
           'TrainingOffer',
           'Sale',
           'SubscriptionReport',
           'TrainingSession']

__metaclass__ = PoolMeta

class TrainingSubscription(Workflow, ModelView, ModelSQL):
    'Training Subscription'
    __name__ = 'training.subscription'
    
    @classmethod
    def get_model(cls):
        cr = Transaction().cursor
        cr.execute('''\
            SELECT
                m.model,
                m.name
            FROM
                ir_model m
            ORDER BY
                m.name
        ''')
        return cr.fetchall()

    company = fields.Many2One('company.company', 'Company', required=True,
        states={
            'readonly': (Eval('state') != 'draft'),
            },
        domain=[
            ('id', If(Eval('context', {}).contains('company'), '=', '!='),
                Eval('context', {}).get('company', -1)),
            ],
        depends=['state'], select=True)
    
    code = fields.Char('Code', readonly=True, select=True)
    
    description = fields.Char('Description',
        states=STATES)
    
    date = fields.Date('Date', 
            states=STATES)
    
    subscriptor = fields.Many2One('party.party', 'Subscriptor',
                            domain=[
                                    ('is_person', '=', True),
                                    ],
                              required=True, 
                              states=STATES)
    student = fields.Many2One('training.student', 'Student', 
                              required=True,
                              states=STATES)
    invoice_method = fields.Selection(INVOICE, 'Invoice Method',
        required=True, states=STATES)
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('quotation', 'Quotation'),
        ('confirmed', 'Confirmed'),
        ('processing', 'Processing'),
        ('done', 'Done'),
        ('cancel', 'Canceled'),
        ('stop', 'Stopped'),
    ], 'State', readonly=True, required=True)
    
    lines = fields.One2Many('training.subscription.line', 'subscription',
                                    'Subscription Lines',
                                    on_change=['lines'],
                                    states=STATES)
    session = fields.Function(fields.Char('Session'), 'get_session')
    price_list = fields.Many2One('product.price_list', 'Price List',
        domain=[('company', '=', Eval('company'))], 
        states=STATES)
    currency = fields.Many2One('currency.currency', 'Currency', required=False,
        states={
            'readonly': (Eval('state') != 'draft') |
                (Eval('lines', [0]) & Eval('currency', 0)),
            },
        depends=['state'])
    
    payment_term = fields.Many2One('account.invoice.payment_term',
        'Payment Term', required=True, states=STATES)
    media_contact = fields.Selection(MEDIA, 'Media Contact', states=STATES,
                                     help="Advertising media that create subscription by offer.")
    salesman = fields.Many2One('company.employee','Educative Salesman', 
                               states=STATES)
    #total_without_tax = fields.Function(fields.Numeric('Without Tax',
    #        states=STATES), 'get_without_tax')
    #taxes = fields.Function(fields.One2Many('account.tax', None, 'Taxes',
    #        states=STATES), 'get_taxes')
    total_amount = fields.Function(fields.Numeric('Total',
                                                  readonly=True, 
                                                  states=STATES, 
                                                  depends=['lines']), 
                                   'get_total_amount')
    
    sales = fields.Many2Many('training.subscription-sale.sale', 
                             'subscription', 'sale', 'Sales',
                             readonly=True)
    invoices = fields.Many2Many('training.subscription-account.invoice',
            'subscription', 'invoice', 'Invoices', readonly=True)
    
    active = fields.Boolean('Active', select=True, states=STATES,
            help='If the active field is set to False, it will allow you to ' \
                'hide the subscription without removing it.')
    user = fields.Many2One('res.user', 'User', required=True,
        domain=[('active', '=', False)], states=STATES)
    request_user = fields.Many2One(
        'res.user', 'Request User', required=True, states=STATES,
        help='The user who will receive requests in case of failure.')
    request_group = fields.Many2One('res.group', 'Request Group', states=STATES,
        help='The group who will receive requests.')
    
    interval_number = fields.Integer('Interval Qty', states=STATES)
    interval_type = fields.Selection([
            ('minutes', 'Minutes'),
            ('hours', 'Hours'),
            ('days', 'Days'),
            ('weeks', 'Weeks'),
            ('months', 'Months')
        ], 'Interval Unit', states=STATES)
    next_call = fields.DateTime('First Date', states=STATES)
    number_calls = fields.Integer('Number of documents', states=STATES)
    cron = fields.Many2One('ir.cron', 'Cron Job', states=STATES, 
            help='Scheduler which runs on subscription.', ondelete='CASCADE')
    
    model_source = fields.Reference('Source Document',
            selection='get_model', depends=['state'],
            help='User can choose the source model on which he wants to ' \
                'create models.', states=STATES)
        
    @classmethod
    def __setup__(cls):
        super(TrainingSubscription, cls).__setup__()
        cls._transitions |= set((
                ('draft', 'quotation'),
                ('quotation', 'confirmed'),
                ('confirmed', 'processing'),
                ('processing', 'done'),
                ('draft', 'cancel'),
                ('quotation', 'cancel'),
                ('quotation', 'draft'),
                ('cancel', 'draft'),
                ('processing', 'stop'),
                ('stop', 'processing'),
                ))
        cls._buttons.update({
                'cancel': {
                    'invisible': ~Eval('state').in_(['draft', 'quotation']),
                    },
                'draft': {
                    'invisible': ~Eval('state').in_(['cancel', 'quotation']),
                    'icon': If(Eval('state') == 'cancel', 'tryton-clear',
                        'tryton-go-previous'),
                    },
                'quotation': {
                    'invisible': Eval('state') != 'draft',
                    'readonly': ~Eval('lines', []),
                    },
                'confirmed': {
                    'invisible': ~Eval('state').in_(['quotation']),
                    },
                'processing': {
                    'invisible': ~Eval('state').in_(['confirmed', 'stop']),
                    },
                'done': {
                    'invisible': Eval('state') != 'processing',
                    },                             
                'stop': {
                    'invisible': Eval('state') != 'processing',
                    },
                })
        cls._error_messages.update({
            'payterm_missing': ('The payment term is missing!'),
            'error': 'Error. Wrong Source Document',
            'provide_another_source': 'Please provide another source ' \
                'model.\nThis one does not exist!',
            'error_creating': 'Error creating document \'%s\'',
            'created_successfully': 'Document \'%s\' created successfully',
            'invoice_missing': 'The invoice is missing',
            })
    
    @classmethod
    def copy(cls, subscriptions, default=None):
        if default is None:
            default = {}
        default = default.copy()
        default['state'] = 'draft'
        default['code'] = None
        default['sales'] = None
        default['invoices'] = None
        default.setdefault('date', None)
        return super(TrainingSubscription, cls).copy(subscriptions, default=default)
    
    @staticmethod
    def default_date():
        Date_ = Pool().get('ir.date')
        return Date_.today()
    
    @staticmethod
    def default_invoice_method():
        return 'by_student'
    
    @staticmethod
    def default_user():
        User = Pool().get('res.user')
        user_ids = User.search([
                ('active', '=', False),
                ('login', '=', 'user_cron_trigger'),
            ])
        return user_ids[0].id
    
    @staticmethod
    def default_next_call():
        return datetime.now()
    
    @staticmethod
    def default_request_user():
        return Transaction().user
    
    @staticmethod
    def default_interval_number():
        return 1

    @staticmethod
    def default_number_calls():
        return 1

    @staticmethod
    def default_interval_type():
        return 'months'

    @staticmethod
    def default_state():
        return 'draft'
    
    @staticmethod
    def default_company():
        return Transaction().context.get('company')
    
    @staticmethod
    def default_active():
        return True
    
    @staticmethod
    def default_currency():
        Company = Pool().get('company.company')
        company = Transaction().context.get('company')
        if company:
            return Company(company).currency.id
    
    @staticmethod
    def default_model_source():
        return ('sale.sale', -1)

    @classmethod
    @ModelView.button
    @Workflow.transition('cancel')
    def cancel(cls, subscriptions):
        for subscription in subscriptions:
            cls.write(subscription, {'state':'cancel'}) 

    @classmethod
    @ModelView.button
    @Workflow.transition('draft')
    def draft(cls, subscriptions):
        pass

    @classmethod
    @ModelView.button
    @Workflow.transition('quotation')
    def quotation(cls, subscriptions):
        cls.set_code(subscriptions)

    @classmethod
    def set_code(cls, subscriptions):
        '''
        Fill the code field with the sale sequence
        '''
        pool = Pool()
        Sequence = pool.get('ir.sequence')
        Config = Pool().get('training.sequences')

        config = Config(1)
        for subscription in subscriptions:
            if subscription.code:
                continue
            code = Sequence.get_id(config.subscription_sequence.id)
            cls.write([subscription], {
                    'code': code,
                    })

    @classmethod
    @ModelView.button
    @Workflow.transition('confirmed')
    def confirmed(cls, subscriptions):
        for subscription in subscriptions:
            cls._create_sale(subscription)
    
    @classmethod
    def _create_sale(cls, subscription):
        pool = Pool()
        Party = pool.get('party.party')
        Sale = pool.get('sale.sale')
        SaleLine = pool.get('sale.line')
        Invoice = Pool().get('account.invoice')
        Configuration = pool.get('training.configuration')
        configuration = Configuration(1)
        SaleInvoice = Pool().get('sale.sale-account.invoice')
        
        date_ = datetime.today().date()
        
        Model = pool.get('ir.model')
        model = Model.search([('name', '=', str(cls.__name__))])

        if not subscription.payment_term:
            cls.raise_user_error('payterm_missing')

        if not subscription.price_list:
            price_list = None
        else:
            price_list = subscription.price_list.id
            
        if not model:
            model = 'subscription'
        else:
            model = model[0].name
            
        description = subscription.description

        if subscription.invoice_method == 'by_subscriptor':
            subscriptions_ = [(subscription.subscriptor, subscription.lines),]
        
        elif subscription.invoice_method == 'by_student':
            subscriptions_ = [(subscription.student.name, subscription.lines), ]
        else:
            subscriptions_ = []
            
        #TODO again
        #Add-Create default charges lines if exists
        if configuration.default_charges:
        
            for product in configuration.default_charges:
            
                for party, lines in subscriptions_:
                    sale, = Sale.create([{
                        'company': subscription.company.id,
                        'payment_term': subscription.payment_term.id,
                        'subscription_code': subscription.code + ' ' + product.code,
                        'party': party.id,
                        'price_list' : price_list,
                        'sale_date': date_,
                        'state': 'draft',
                        'invoice_address': Party.address_get(party, type='invoice'),
                        'shipment_address': Party.address_get(party, type='delivery'),
                        'description': description,
                    }])
                
                    new_line = cls._create_new_line(
                            sale, 1, product.template, 
                            product.template.list_price
                            )
                    if new_line:
                        SaleLine.create([new_line])

                Sale.quote([sale])
                Sale.confirm([sale])
                Sale.process([sale])
                cls.write([subscription], {'sales': [('add', [sale.id])],
                               'model_source':('sale.sale', sale.id), 
                })
        
                saleinvoice = SaleInvoice.search([
                    ('sale', '=', sale.id),
                ])
        
                invoices = Invoice.search( [
                    ('id', '=', saleinvoice[0].invoice.id)
                ])

                Invoice.write(invoices, {
                    'reference': sale.subscription_code,
                    'invoice_date': sale.sale_date,
                })

                Invoice.post(invoices)
                   
                if invoices:
                    for invoice in invoices:
                        cls.write([subscription], {'invoices': [('add', [invoice.id])],   
                    })

        # Party Subscription 
        for party, lines in subscriptions_:
            sale, = Sale.create([{
                'company': subscription.company.id,
                'payment_term': subscription.payment_term.id,
                'subscription_code': subscription.code,
                'party': party.id,
                'price_list' : price_list,
                'sale_date': date_,
                'state': 'draft',
                'invoice_address': Party.address_get(party, type='invoice'),
                'shipment_address': Party.address_get(party, type='delivery'),
                'description': description,
                }])

            for res_line in lines:
                if res_line.quantity <= 0:
                    continue
                new_line = cls._create_new_line(
                        sale, res_line.quantity, res_line.session.offer.name,
                        res_line.unit_price
                        )
                if new_line:
                    SaleLine.create([new_line])

        Sale.quote([sale])
        Sale.confirm([sale])
        Sale.process([sale])
        cls.write([subscription], {'sales': [('add', [sale.id])],
                                   'model_source':('sale.sale', sale.id), 
                                   })
        
        saleinvoice = SaleInvoice.search([
                ('sale', '=', sale.id),
                ])
        
        invoices = Invoice.search( [
                ('id', '=', saleinvoice[0].invoice.id)
                ])

        Invoice.write(invoices, {
                'reference': sale.subscription_code,
                'invoice_date': sale.sale_date,
                })

        Invoice.post(invoices)
        if invoices:
            for invoice in invoices:
                cls.write([subscription], {'invoices': [('add', [invoice.id])],   
                                   })
        
    @classmethod
    def _create_new_line(cls, sale, quantity, template, unit_price):
        pool = Pool()
        SaleLine = pool.get('sale.line')
        product = template.products[0]

        line = SaleLine()
        line.unit = template.sale_uom
        line.sale = sale.id

        new_line = {
                'sale': sale.id,
                'type': 'line',
                'unit': template.default_uom.id,
                'quantity': quantity,
                'unit_price': unit_price,
                'product': product.id,
                'description': (product.rec_name),
                 }
        return new_line              
    
    @classmethod
    @ModelView.button
    @Workflow.transition('processing')
    def processing(cls, subscriptions):
        for subscription in subscriptions:
            vals = {
                'model': subscription.__name__,
                'name': subscription.code,
                'user': subscription.user.id,
                'request_user': subscription.request_user.id,
                'interval_number': subscription.interval_number,
                'interval_type': subscription.interval_type,
                'number_calls': subscription.number_calls or 1,
                'next_call': subscription.next_call,
                'args': str([subscription.id]),
                'function': 'model_copy',
            }
            Cron = Pool().get('ir.cron')
            domain = [
                ('model', '=', subscription.__name__),
                ('name', '=', subscription.code),
                ('active', '=', False),
            ]
            cron = Cron.search([domain])
            if not cron:
                cron = Cron.create([vals])[0]
            else:
                vals['active'] = True
                Cron.write(cron, vals)
                cron = cron[0]
            vals = {
                'cron': cron.id,
                'state': 'processing',
            }
            cls.write([subscription], vals)

    @classmethod
    def model_copy(cls, subscription_id):
        Cron = Pool().get('ir.cron')
        History = Pool().get('training.subscription.history')
        Invoice = Pool().get('account.invoice')
        Sale = Pool().get('sale.sale')
        SaleInvoice = Pool().get('sale.sale-account.invoice')
        
        subscription = cls(subscription_id)
        logger = logging.getLogger('training_subscription')
        number_calls = subscription.number_calls
        remaining = Cron.browse([subscription.cron.id])[0].number_calls
        actual = number_calls - remaining + 1
        model_id = subscription.model_source and subscription.model_source.id \
                or False
        if model_id:
            Model = Pool().get(subscription.model_source.__name__)
            default = {'state':'draft'}
            #default['subscription_code'] = subscription.model_source.subscription_code + ' ' +str(actual)
            default['subscription_code'] = subscription.model_source.subscription_code

            try:
                model = Model.copy([subscription.model_source], default)
            except:
                history_vals = {
                    'log': cls.raise_user_error(
                        error='error_creating',
                        error_args=subscription.model_source.__name__, 
                        raise_exception=False)
                }
            else:
                history_vals = {
                    'log': cls.raise_user_error(
                        error='created_successfully',
                        error_args=subscription.model_source.__name__, 
                        raise_exception=False)
                }
                history_vals['document'] = (subscription.model_source.__name__,
                                        model[0].id)
            History.create([history_vals])
            
            sales = Sale.search([
                         ('id','=',model[0].id)
                         ])
            
            for sale in sales:
                Sale.quote([sale])
                Sale.confirm([sale])
                Sale.process([sale])
                
                saleinvoices = SaleInvoice.search([
                    ('sale', '=', sale.id),
                    ])
                invoices = Invoice.search( [
                    ('id','=',saleinvoices[0].invoice.id)
                    ])
                Invoice.write(invoices, {
                    'reference': sale.subscription_code,
                    'invoice_date': sale.sale_date,
                    })
                Invoice.post(invoices)
                
                if invoices:
                    for invoice in invoices:
                        cls.write([subscription], 
                                           {'sales': [('add', [sale.id])],
                                           'invoices': [('add', [invoice.id])]
                                               })

            # If it is the last cron execution, set the state of the
            # subscription to done
            if remaining == 1:
                subscription.write([subscription], {'state': 'done'})
        else:
            logger.error('Document in subscription %s not found.\n' % \
                         subscription.code)   
    
    @classmethod
    @ModelView.button
    @Workflow.transition('done')
    def done(cls, subscriptions):
        for subscription in subscriptions:
            Pool().get('ir.cron').write([subscription.cron], {'active': False})
            cls.write([subscription], {'state':'done'})
    
    def get_total_amount(self, name):
        res = Decimal(0)
        if self.lines:
            for line in self.lines:
                res += line.total_amount
        return res

    def on_change_lines(self):
        res = {
               'total_amount':Decimal('0'),
               'number_calls':Decimal('0')
               }
        
        if self.lines:
            for line in self.lines:
                if line.total_amount: 
                    res['total_amount'] += line.total_amount
                if line.number_calls:
                    res['number_calls'] += line.number_calls
        return res
    
    def get_session(self, name=None):
        res = {}
        if self.lines:
            return self.lines[0].session.name
        return res
    
    @classmethod
    @ModelView.button
    @Workflow.transition('stop')
    def stop(cls, subscriptions):
        for subscription in subscriptions:
            Pool().get('ir.cron').write([subscription.cron], {'active': False})
            cls.write([subscription], {'state':'stop'})

class TrainingSubscriptionLine(ModelView, ModelSQL):
    'Training Subscription Line'
    __name__ = 'training.subscription.line'

    subscription =fields.Many2One('training.subscription', 'Subscription',
                                            required=True,
                                            ondelete='CASCADE')
    session = fields.Many2One('training.session', 'Session', required=True,
            domain=[('state', 'in', ['open']),],
            on_change=['session', 'uom', 'quantity', 
            '_parent_subscription.currency', '_parent_subscription.price_list',
            '_parent_subscription.date'],
            depends=['subscription'],
            help='Select the session')
    unit_price = fields.Numeric('Unit Price', digits=(16,2), select=True)
    quantity = fields.Numeric('Quantity', digits=(16, 2), readonly=True)
    uom = fields.Many2One('product.uom', 'UOM', depends=['session'])
    number_calls = fields.Integer('Number of documents', states=STATES)
    total_amount = fields.Function(fields.Numeric('Total Amount', 
            digits=(16, 2)), 'get_total_amount')
    notes = fields.Char('Notes')

    @classmethod
    def __setup__(cls):
        super(TrainingSubscriptionLine, cls).__setup__()
    
    @staticmethod
    def default_state():
        return 'draft'
    
    @staticmethod
    def default_quantity():
        return 1
    
    def get_total_amount(self, name):
        '''
        The total amount of session subscription.
        '''
        res = Decimal(0)
        if self.quantity and self.unit_price:
            res = self.quantity * self.unit_price
        return res
    
    def on_change_unit_price(self):
        res = {'total_amount':0}
        if self.quantity and self.unit_price:
            total = self.quantity * self.unit_price
            res['total_amount'] = total
        return res 
    
    def on_change_session(self):
        Product = Pool().get('product.product')
        res = {}
        if self.session:
            res = {'uom': self.session.offer.name.default_uom.id}
            with Transaction().set_context(self._get_context_subscription_price(self.subscription)):
                for session_product in self.session.offer.name.products: 
                    product = session_product

                res['unit_price'] = Product.get_sale_price([product],
                        self.quantity or 0)[product.id]
                if res['unit_price']:
                    res['unit_price'] = res['unit_price'].quantize(
                        Decimal(1) / 10 ** self.__class__.unit_price.digits[1])
            self.unit_price = res['unit_price']
            res['number_calls'] = self.session.offer.number_calls
            if self.quantity and self.unit_price:
                total = self.quantity * self.unit_price
                res['total_amount'] = total
        return res
    
    def _get_context_subscription_price(self, subscription):
        context = {}
        if getattr(self, 'subscription', None):
            if getattr(self.subscription, 'currency', None):
                context['currency'] = self.subscription.currency.id
            if getattr(self.subscription, 'subscriptor', None):
                context['subscriptor'] = self.subscription.subscriptor.id
            if getattr(self.subscription, 'date', None):
                context['date'] = self.subscription.date
            if getattr(self.subscription, 'price_list', None):
                context['price_list'] = self.subscription.price_list.id

        if self.uom:
            context['uom'] = self.uom.id
        else:
            context['uom'] = self.session.offer.name.sale_uom.id
        return context

class TrainingOffer:
    __name__ = 'training.offer'
    
    interval_number = fields.Integer('Interval Qty', states=STATES)
    number_calls = fields.Integer('Number of Calls', states=STATES,
                                  required=True)
    
    @staticmethod
    def default_number_calls():
        return 1
    
    @staticmethod
    def default_interval_number():
        return 1


class TrainingSubscriptionSale(ModelSQL):
    'Training Subscription - Sale'
    __name__ = 'training.subscription-sale.sale'
    _table = 'subscription_sales_rel'
    
    subscription = fields.Many2One('training.subscription', 'Subscription', ondelete='CASCADE',
        select=True, required=True)
    sale = fields.Many2One('sale.sale', 'Sale',
            ondelete='RESTRICT', select=True, required=True)

class TrainingSubscriptionInvoice(ModelSQL):
    'Training Subscription - Invoice'
    __name__ = 'training.subscription-account.invoice'
    _table = 'subscription_invoices_rel'
    
    subscription = fields.Many2One('training.subscription', 'Subscription', ondelete='CASCADE',
        select=True, required=True)
    invoice = fields.Many2One('account.invoice', 'Invoice',
            ondelete='RESTRICT', select=True, required=True)
    
class TrainingSubscriptionHistory(ModelSQL, ModelView):
    "Subscription History"
    __name__ = "training.subscription.history"
    _rec_name = 'date'

    @classmethod
    def get_model(cls):
        cr = Transaction().cursor
        cr.execute('''\
            SELECT
                m.model,
                m.name
            FROM
                ir_model m
            ORDER BY
                m.name
        ''')
        return cr.fetchall()

    date = fields.DateTime('Date', readonly=True)
    log = fields.Char('Result', readonly=True)
    subscription = fields.Many2One('training.subscription',
            'Subscription', ondelete='CASCADE', readonly=True)
    document = fields.Reference('Created Document', selection='get_model',
            readonly=True)

    @staticmethod
    def default_date():
        return datetime.now()

class Sale:
    'Sale'
    __name__ = 'sale.sale'
    
    subscription_code = fields.Char('Subscription Code', 
                                    states = {
                                              'readonly': Eval('state') != 'draft'})

class SubscriptionReport(CompanyReport):
    __name__ = 'subscription.report'

class TrainingSession(ModelView, ModelSQL):
    'Session'
    __name__ = 'training.session'
   
    count_subscriptions = fields.Function(
                                fields.Integer('Confirmed Subscriptions'),
                                'get_subscriptions_count')
    
    #participants = fields.Function(fields.Char('Students'),
    #                               'get_participants')
    
    def get_subscriptions_count(self, name):
        pool = Pool()
        SubscriptionLine = pool.get('training.subscription.line')
        return SubscriptionLine.search_count([ ('session', '=', self.id) ])
    
   # def get_participants(self, name):
   #     pool = Pool()
   #     SubscriptionLine = pool.get('training.subscription.line')
   #     return SubscriptionLine.search([ ('session', '=', self.id) ])
        