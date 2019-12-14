"""
Base classes for correction
"""
import logging
from abc import ABCMeta, abstractmethod, abstractproperty

import numpy as np

from ..results import MetaResult
from ..stats import p_to_z

LGR = logging.getLogger(__name__)


class Corrector(metaclass=ABCMeta):
    '''
    Base class for multiple comparison correction methods.
    '''

    # The name of the method that must be implemented in an Estimator class
    # in order to override the default correction method.
    _correction_method = None

    # Maps that must be available in the MetaResult instance
    _required_maps = ('p',)

    def __init__(self):
        pass

    @abstractproperty
    def _name_suffix(self):
        pass

    def _validate_input(self, result):
        if not isinstance(result, MetaResult):
            raise ValueError("First argument to transform() must be an "
                             "instance of class MetaResult, not {}."
                             .format(type(result)))

        if self.method not in self._native_methods:
            raise ValueError("Unsupported {} correction method: {}".format(
                self._correction_method, self.method))

        for rm in self._required_maps:
            if result.maps.get(rm) is None:
                raise ValueError("{0} requires {1} maps to be present in the "
                                 "MetaResult, but none were found."
                                 .format(type(self), rm))

    def _generate_secondary_maps(self, result, corr_maps):
        # Generates corrected version of z and log-p maps if they exist
        p = corr_maps['p']
        if 'z' in result.maps:
            corr_maps['z'] = p_to_z(p) * np.sign(result.maps['z'])
        if 'log_p' in result.maps:
            corr_maps['log_p'] = -np.log10(p)
        return corr_maps

    def transform(self, result):
        """
        Apply the multiple comparisons correction method to a MetaResult object.

        Parameters
        ----------
        result : :obj:`nimare.results.MetaResult`
            MetaResult generated by an Estimator to be corrected for multiple
            comparisons.

        Returns
        -------
        result : :obj:`nimare.results.MetaResult`
            MetaResult with new corrected maps added.
        """
        est = result.estimator
        correction_method = 'correct_' + self._correction_method + '_' + self.method

        # Make sure we return a copy of the MetaResult
        result = result.copy()

        # If a correction method with the same name exists in the current
        # MetaEstimator, use it. Otherwise fall back on _transform.
        if (correction_method is not None and hasattr(est, correction_method)):
            LGR.info('Using correction method implemented in Estimator: {}.'
                     '{}.'.format(est, correction_method))
            corr_maps = getattr(est, correction_method)(result, **self.parameters)
        else:
            self._validate_input(result)
            corr_maps = self._transform(result)

        # Update corrected map names and add them to maps dict
        corr_maps = {(k + self._name_suffix): v for k, v in corr_maps.items()}
        result.maps.update(corr_maps)

        return result

    @abstractmethod
    def _transform(self, result, **kwargs):
        # Must return a dictionary of new maps to add to .maps, where keys are
        # map names and values are the maps. Names must _not_ include
        # the _name_suffix:, as that will be added in transform() (i.e.,
        # return "p" not "p_corr-FDR_q-0.05_method-indep").
        pass
