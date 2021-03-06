# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
"""

.. _metas5:

==========================================================
 Run coordinate-based subtraction and conjunction analyses
==========================================================

The (coordinate-based) ALE subtraction method tests at which voxels
the meta-analytic results from two groups of studies differ reliably from
one another. [1]_:superscript:`,` [2]_
"""
import os

from nilearn.image import math_img
from nilearn.plotting import plot_stat_map

from nimare.correct import FWECorrector
from nimare.io import convert_sleuth_to_dataset
from nimare.meta.cbma import ALE, ALESubtraction
from nimare.tests.utils import get_test_data_path

###############################################################################
# Load Sleuth text files into Datasets
# --------------------------------------------------
# The data for this example are a subset of studies from a meta-analysis on
# semantic cognition in children. [3]_ A first group of studies probed
# childrens semantic world knowledge (e.g., correctly naming an object after
# hearing its auditory description) while a second group of studies asked
# children to decide if two (or more) words were semantically related to one
# another or not.
sleuth_file = os.path.join(get_test_data_path(), "semantic_knowledge_children.txt")
sleuth_file2 = os.path.join(get_test_data_path(), "semantic_relatedness_children.txt")

dset = convert_sleuth_to_dataset(sleuth_file)
dset2 = convert_sleuth_to_dataset(sleuth_file2)

###############################################################################
# Individual group ALEs
# --------------------------------------------------
# Computing seperate ALE analyses for each group is not strictly necessary for
# performing the subtraction analysis but will help to appreciate the
# similarities and differences between the groups.
ale = ALE(null_method="approximate")
res = ale.fit(dset)
res2 = ale.fit(dset2)

corr = FWECorrector(method="montecarlo", voxel_thresh=0.001, n_iters=100, n_cores=1)
cres = corr.transform(res)
cres2 = corr.transform(res2)

img = cres.get_map("z_level-cluster_corr-FWE_method-montecarlo")
plot_stat_map(
    img,
    cut_coords=4,
    display_mode="z",
    title="Semantic knowledge",
    threshold=2.326,  # cluster-level p < .01, one-tailed
    cmap="RdBu_r",
    vmax=4,
)

img2 = cres2.get_map("z_level-cluster_corr-FWE_method-montecarlo")
plot_stat_map(
    img2,
    cut_coords=4,
    display_mode="z",
    title="Semantic relatedness",
    threshold=2.326,  # cluster-level p < .01, one-tailed
    cmap="RdBu_r",
    vmax=4,
)

###############################################################################
# Subtraction analysis
# --------------------------------------------------
sub = ALESubtraction(n_iters=100, memory_limit=None)
res_sub = sub.fit(dset, dset2)
img_sub = res_sub.get_map("z_desc-group1MinusGroup2")

plot_stat_map(
    img_sub,
    cut_coords=4,
    display_mode="z",
    title="Subtraction",
    cmap="RdBu_r",
    vmax=4,
)

###############################################################################
# Conjunction analysis
# --------------------------------------------------
# To determine the overlap of the meta-analytic results, a conjunction image
# can be computed by (a) identifying voxels that were statistically significant
# in *both* individual group maps and (b) selecting, for each of these voxels,
# the smaller of the two group-specific *z* values. [4]_ Since this is simple
# arithmetic on images, conjunction is not implemented as a seperate method in
# :code:`NiMARE` but can easily be achieved with the :code:`math_img()`
# function from :code:`nilearn.image`.
formula = "np.where(img * img2 > 0, np.minimum(img, img2), 0)"
img_conj = math_img(formula, img=img, img2=img2)

plot_stat_map(
    img_conj,
    cut_coords=4,
    display_mode="z",
    title="Conjunction",
    threshold=2.326,  # cluster-level p < .01, one-tailed
    cmap="RdBu_r",
    vmax=4,
)

###############################################################################
# References
# --------------------------------------------------
# .. [1] Laird, Angela R., et al. "ALE meta‐analysis: Controlling the
#     false discovery rate and performing statistical contrasts." Human
#     brain mapping 25.1 (2005): 155-164.
#     https://doi.org/10.1002/hbm.20136
# .. [2] Eickhoff, Simon B., et al. "Activation likelihood estimation
#     meta-analysis revisited." Neuroimage 59.3 (2012): 2349-2361.
#     https://doi.org/10.1016/j.neuroimage.2011.09.017
# .. [3] Enge, Alexander, et al. "A meta-analysis of fMRI studies of
#     semantic cognition in children." bioRxiv (2021): 2021.05.17.442947.
#     https://doi.org/10.1101/2021.05.17.442947
# .. [4] Nichols, Thomas, et al. "Valid conjunction inference with the
#     minimum statistic." Neuroimage 25.3 (2005): 653-660.
#     https://doi.org/10.1016/j.neuroimage.2004.12.005
