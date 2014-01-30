#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
from trytond.model import ModelView, ModelSingleton, ModelSQL, fields

__all__ = ['TrainingSequences',
           'TrainingConfiguration',
           'ConfigurationProduct']

# TRAINING SEQUENCES
class TrainingSequences(ModelSingleton, ModelSQL, ModelView):
    'Training Module for Tryton'
    __name__ = 'training.sequences'

    subscription_sequence = fields.Property(fields.Many2One(
        'ir.sequence', 'Subscription Sequence', required=True,
        domain=[('code', '=', 'training.subscription')]))
    
class TrainingConfiguration(ModelSingleton, ModelSQL, ModelView):
    'Training Subscription Configuration'
    __name__ = 'training.configuration'

    default_charges = fields.Many2Many('training.configuration-product.product', 
        'configuration', 'product', 'Default Charges')

class ConfigurationProduct(ModelSQL):
    'Configuration - Product'
    __name__ = 'training.configuration-product.product'
    _table = 'training_configuration_product_rel'
    
    configuration = fields.Many2One('training.configuration', 'Configuration',
            ondelete='CASCADE', select=True, required=True)
    product = fields.Many2One('product.product', 'Product',
            ondelete='RESTRICT', select=True, required=True)

    

## create default charges