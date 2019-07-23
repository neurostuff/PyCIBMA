"""
Top-level namespace for nimare base.
"""

from .base import MetaResult
from .decode import Decoder
from .meta import (KernelTransformer, MetaEstimator, CBMAEstimator,
                   IBMAEstimator)
from .annotate import (AnnotationModel)
from .misc import (Parcellator)

__all__ = ['Decoder',
           'KernelTransformer', 'MetaEstimator', 'CBMAEstimator',
           'IBMAEstimator', 'MetaResult',
           'AnnotationModel', 'Parcellator']
