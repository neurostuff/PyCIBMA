"""Utilities for generating data for testing"""
from itertools import zip_longest
import gzip
import tempfile
from pathlib import Path

import nibabel as nib
import requests
import numpy as np
import nilearn

from .dataset import Dataset
from .meta.utils import compute_ale_ma, get_ale_kernel
from .transforms import vox2mm, mm2vox

NEUROSYNTH_WHITE_LIST = [
    "spatial",
    "language",
    "visual",
    "auditory",
    "motor",
    "taste",
    "perception",
    "emotions",
    "thoughts",
    "sensation",
    "reward",
    "navigation",
    "interoceptive",
    "episodic",
    "planning",
    "attention",
    "working%20memory",
    "executive",
    "pain",
    "touch",
    "speech",
]


def create_coordinate_dataset(
    foci=1,
    foci_percentage="100%",
    fwhm=10,
    sample_size=30,
    n_studies=30,
    n_noise_foci=0,
    seed=None,
    space="MNI",
):
    """Generate coordinate based dataset for meta analysis.

    Parameters
    ----------
    foci : :obj:`int` or :obj:`list`
        The number of foci to be generated per study or the
        x,y,z coordinates of the ground truth foci. (Default=1)
    foci_percentage : :obj:`float`
        Percentage of studies where the foci appear. (Default="100%")
    fwhm : :obj:`float`
        Full width at half maximum (fwhm) to define the probability
        spread of the foci. (Default=10)
    sample_size : :obj:`int` or :obj:`list`
        Either mean number of participants in each study
        or a list specifying the sample size for each
        study. If a list of two numbers and n_studies is
        not two, then the first number will represent a lower
        bound and the second number will represent an upper bound
        of a uniform sample. (Default=30)
    n_studies : :obj:`int`
        Number of studies to generate. (Default=30)
    n_noise_foci : :obj:`int`
        Number of foci considered to be noise in each study. (Default=0)
    seed : :obj:`int` or None
        Random state to reproducibly initialize random numbers.
        If seed is None, then the random state will try to be initialized
        with data from /dev/urandom (or the Windows analogue) if available
        or will initialize from the clock otherwise. (Default=None)
    space : :obj:`str`
        The template space the coordinates are reported in. (Default='MNI')

    Returns
    -------
    ground_truth_foci : :obj:`list`
        generated foci in xyz (mm) coordinates
    dataset : :class:`nimare.Dataset`
    """
    # set random state
    rng = np.random.RandomState(seed=seed)

    # check foci argument
    if not isinstance(foci, int) and not _array_like(foci):
        raise ValueError("foci must be a positive integer or array like")

    # check foci_percentage argument
    if (
        (not isinstance(foci_percentage, (float, str)))
        or (isinstance(foci_percentage, str) and foci_percentage[-1] != "%")
        or (isinstance(foci_percentage, float) and not (0.0 <= foci_percentage <= 1.0))
    ):
        raise ValueError(
            "foci_percentage must be a string (example '96%') or a float between 0 and 1"
        )

    # check sample_size argument
    if _array_like(sample_size) and len(sample_size) != n_studies and len(sample_size) != 2:
        raise ValueError("sample_size must be the same length as n_studies or list of 2 items")
    elif not _array_like(sample_size) and not isinstance(sample_size, int):
        raise ValueError("sample_size must be array like or integer")

    # check space argument
    if space != "MNI":
        raise NotImplementedError("Only coordinates for the MNI atlas has been defined")

    # process foci_percentage argument
    if isinstance(foci_percentage, str) and foci_percentage[-1] == "%":
        foci_percentage = float(foci_percentage[:-1]) / 100

    # process sample_size argument
    if isinstance(sample_size, int):
        sample_size = [sample_size] * n_studies
    elif _array_like(sample_size) and len(sample_size) == 2 and n_studies != 2:
        sample_size_lower_limit = sample_size[0]
        sample_size_upper_limit = sample_size[1]
        sample_size = rng.randint(sample_size_lower_limit, sample_size_upper_limit, size=n_studies)

    ground_truth_foci, foci_dict = _create_foci(
        foci, foci_percentage, fwhm, n_studies, n_noise_foci, rng, space
    )

    source_dict = _create_source(foci_dict, sample_size, space)
    dataset = Dataset(source_dict)

    return ground_truth_foci, dataset


def create_image_dataset(
    signal_map=True, noise_maps=10, n_studies=5, n_participants=5,
    standard_error=5, img_dir=None, seed=None
):
    """create an image dataset for meta-analysis

    Parameters
    ----------
    signal_map: :obj:`bool` or :obj:`str`
        The map used to indicate consistency between studies,
        if `True`, a map will be selected randomly, if `str`,
        the map associated with the concept will be used.
    noise_maps: :obj:`int`
        The number of noise maps to include (randomly selected),
        or a specific list of images to include.

    Returns
    -------
    ground_truth_img: :class:`nibabel.Nifti1Image`
    dataset : :class:`nimare.Dataset`
    """
    rng = np.random.default_rng(seed=seed)

    terms_list = NEUROSYNTH_WHITE_LIST.copy()
    if isinstance(signal_map, str) and signal_map in NEUROSYNTH_WHITE_LIST:
        download_term = signal_map.replace(" ", "%20")
        signal_data = _download_img(download_term)
        terms_list.remove(download_term)
    elif signal_map is True:
        download_term = rng.choice(terms_list)
        signal_data = _download_img(download_term)
        terms_list.remove(download_term)
    elif signal_map is False:
        download_term = None
        signal_data = None
    else:
        raise ValueError(
            "signal map must be a boolean or string in this list:",
            NEUROSYNTH_WHITE_LIST,
        )
    if img_dir is None:
        img_dir = Path(tempfile.mkdtemp(prefix="simulation"))
    else:
        img_dir = Path(img_dir)
        img_dir.ensure_dir()

    mni_img = nilearn.datasets.load_mni152_brain_mask()
    mni_mask = mni_img.get_fdata().astype(bool)
    noise_terms = rng.choice(terms_list, size=(noise_maps, n_studies))
    noise_weights = rng.random(size=(noise_maps, n_studies))

    noise_arr = np.zeros(mni_mask[mni_mask].shape)
    used_terms = np.unique(noise_terms)
    term_dict = {
        term: idx for idx, term in enumerate(used_terms)
    }

    term_data = np.vstack([_download_img(term)[mni_mask] for term in used_terms])

    dataset_dict = {}
    for study_idx in range(n_studies):
        term_idxs = [term_dict[term] for term in noise_terms[:, study_idx]]
        study_data = term_data[term_idxs, :]
        sign_shuffle = rng.choice([-1, 1], study_data.shape)
        noise_arr = (
            study_data * sign_shuffle * np.atleast_2d(noise_weights[:, study_idx]).T
        ).sum(axis=0)
        # brain_betas[mni_mask] = noise_arr.sum(axis=0)
        if signal_data is not None:
            signal_arr = signal_data[mni_mask]
            betas_arr = noise_arr + signal_arr
        else:
            betas_arr = noise_arr
        beta_path = _create_nii_file(
            betas_arr, mni_mask, mni_img.affine, img_dir, f"study-{study_idx}_beta"
        )

        # standard_error data
        std_err_arr = np.full(betas_arr.shape, standard_error)
        se_path = _create_nii_file(
            std_err_arr, mni_mask, mni_img.affine, img_dir, f"study-{study_idx}_se"
        )

        # t-statistic data
        tstat_arr = betas_arr / std_err_arr
        tstat_path = _create_nii_file(
            tstat_arr, mni_mask, mni_img.affine, img_dir, f"study-{study_idx}_tstat"
        )

        # z-statistic data
        zstat_arr = (betas_arr - betas_arr.mean()) / std_err_arr
        zstat_path = _create_nii_file(
            zstat_arr, mni_mask, mni_img.affine, img_dir, f"study-{study_idx}_zstat"
        )

        dataset_dict[f'study-{study_idx}'] = {
            "contrasts": {
                "1": {
                    "images": {
                        "beta": beta_path,
                        "se": se_path,
                        "t": tstat_path,
                        "z": zstat_path,
                        "varcope": se_path,
                    },
                    "metadata": {
                        "sample_sizes": [
                            n_participants,
                        ],
                    }
                }
            }
        }

    dataset = Dataset(dataset_dict)

    return signal_data, dataset


def create_simple_image_dataset(
    signal_voxels=0.10, n_studies=5, n_participants=5,
    standard_error=5, img_dir=None, seed=None
):
    """create an image dataset for meta-analysis

    Parameters
    ----------
    signal_map: :obj:`bool` or :obj:`str`
        The map used to indicate consistency between studies,
        if `True`, a map will be selected randomly, if `str`,
        the map associated with the concept will be used.
    noise_maps: :obj:`int`
        The number of noise maps to include (randomly selected),
        or a specific list of images to include.

    Returns
    -------
    ground_truth_img: :class:`nibabel.Nifti1Image`
    dataset : :class:`nimare.Dataset`
    """
    rng = np.random.default_rng(seed=seed)

    # check sample_size argument
    if _array_like(n_participants) and len(n_participants) != n_studies and len(n_participants) != 2:
        raise ValueError("sample_size must be the same length as n_studies or list of 2 items")
    elif not _array_like(n_participants) and not isinstance(n_participants, int):
        raise ValueError("sample_size must be array like or integer")

    # process sample_size argument
    if isinstance(n_participants, int):
        n_participants = [n_participants] * n_studies
    elif _array_like(n_participants) and len(n_participants) == 2 and n_studies != 2:
        sample_size_lower_limit = n_participants[0]
        sample_size_upper_limit = n_participants[1]
        n_participants = rng.uniform(
            sample_size_lower_limit, sample_size_upper_limit, size=n_studies
        )

    n_voxels = 1000
    lower_stat = -10
    upper_stat = 10
    signal_magnitude = 3
    num_sig_voxels = int(n_voxels * signal_voxels)
    data_arr = rng.uniform(lower_stat, upper_stat, (n_studies, n_voxels))
    signal_arr = np.zeros(n_voxels)
    signal_arr[:num_sig_voxels] = signal_magnitude
    data_arr[:, :num_sig_voxels] += signal_magnitude
    mask_arr = np.ones(n_voxels).astype(bool)

    if img_dir is None:
        img_dir = Path(tempfile.mkdtemp(prefix="simulation"))
    else:
        img_dir = Path(img_dir)
        img_dir.ensure_dir()

    dataset_dict = {}
    for n_part, (study_idx, betas_arr) in zip(n_participants, enumerate(data_arr)):
        # write betas to file
        beta_path = _create_nii_file(
            betas_arr, np.atleast_3d(mask_arr),
            np.eye(4) * 2, img_dir, f"study-{study_idx}_beta"
        )

        # standard_error data
        std_err_arr = np.full(betas_arr.shape, standard_error)
        se_path = _create_nii_file(
            std_err_arr, np.atleast_3d(mask_arr),
            np.eye(4) * 2, img_dir, f"study-{study_idx}_se"
        )

        # varcope data
        varcope_arr = std_err_arr ** 2
        varcope_path = _create_nii_file(
            varcope_arr, np.atleast_3d(mask_arr),
            np.eye(4) * 2, img_dir, f"study-{study_idx}_varcope"
        )

        # t-statistic data
        tstat_arr = betas_arr / std_err_arr
        tstat_path = _create_nii_file(
            tstat_arr, np.atleast_3d(mask_arr),
            np.eye(4) * 2, img_dir, f"study-{study_idx}_tstat"
        )

        # z-statistic data
        zstat_arr = (betas_arr - betas_arr.mean()) / std_err_arr
        zstat_path = _create_nii_file(
            zstat_arr, np.atleast_3d(mask_arr),
            np.eye(4) * 2, img_dir, f"study-{study_idx}_zstat"
        )

        dataset_dict[f'study-{study_idx}'] = {
            "contrasts": {
                "1": {
                    "images": {
                        "beta": beta_path,
                        "se": se_path,
                        "t": tstat_path,
                        "z": zstat_path,
                        "varcope": varcope_path,
                    },
                    "metadata": {
                        "sample_sizes": [
                            n_part,
                        ]
                    }
                }
            }
        }

    # create mask
    mask_path = _create_nii_file(mask_arr, np.atleast_3d(mask_arr), np.eye(4) * 2, img_dir, "mask")
    dataset = Dataset(dataset_dict, mask=mask_path)

    return np.atleast_3d(signal_arr), dataset


def _create_source(foci, sample_sizes, space="MNI"):
    """Create dictionary according to nimads(ish) specification

    Parameters
    ----------
    foci : :obj:`dict`
        A dictionary of foci in xyz (mm) coordinates whose keys represent
        different studies.
    sample_sizes : :obj:`list`
        The sample size for each study
    space : :obj:`str`
        The template space the coordinates are reported in. (Default='MNI')

    Returns
    -------
    source : :obj:`dict`
        study information in nimads format
    """
    source = {}
    for sample_size, (study, study_foci) in zip(sample_sizes, foci.items()):
        source[f"study-{study}"] = {
            "contrasts": {
                "1": {
                    "coords": {
                        "space": space,
                        "x": [c[0] for c in study_foci],
                        "y": [c[1] for c in study_foci],
                        "z": [c[2] for c in study_foci],
                    },
                    "metadata": {"sample_sizes": [sample_size]},
                }
            }
        }

    return source


def _create_foci(foci, foci_percentage, fwhm, n_studies, n_noise_foci, rng, space):
    """Generate study specific foci.

    Parameters
    ----------
    foci : :obj:`int` or :obj:`list`
        The number of foci to be generated per study or the
        x,y,z coordinates of the ground truth foci.
    foci_percentage : :obj:`float`
        Percentage of studies where the foci appear.
    fwhm : :obj:`float`
        Full width at half maximum (fwhm) to define the probability
        spread of the foci.
    n_studies : :obj:`int`
        Number of n_studies to generate.
    n_noise_foci : :obj:`int`
        Number of foci considered to be noise in each study.
    rng : :class:`numpy.random.RandomState`
        Random state to reproducibly initialize random numbers.
    space : :obj:`str`
        The template space the coordinates are reported in.

    Returns
    -------
    ground_truth_foci : :obj:`list`
        List of 3-item tuples containing x, y, z coordinates
        of the ground truth foci or an empty list if
        there are no ground_truth_foci.
    foci_dict : :obj:`dict`
        Dictionary with keys representing the study, and
        whose values represent the study specific foci.
    """
    # convert foci_percentage to float between 0 and 1
    if isinstance(foci_percentage, str) and foci_percentage[-1] == "%":
        foci_percentage = float(foci_percentage[:-1]) / 100

    if space == "MNI":
        template_img = nilearn.datasets.load_mni152_brain_mask()

    # use a template to find all "valid" coordinates
    template_data = template_img.get_fdata()
    possible_ijks = np.argwhere(template_data)

    # number of "convergent" foci each study should report
    if isinstance(foci, int):
        foci_idxs = np.unique(rng.choice(range(possible_ijks.shape[0]), foci, replace=True))
        # if there are no foci_idxs, give a dummy coordinate (0, 0, 0)
        ground_truth_foci_ijks = possible_ijks[foci_idxs] if foci_idxs.size else np.array([[]])
    elif isinstance(foci, list):
        ground_truth_foci_ijks = np.array([mm2vox(coord, template_img.affine) for coord in foci])

    # create a probability map for each peak
    kernel = get_ale_kernel(template_img, fwhm)[1]
    foci_prob_maps = {
        tuple(peak): compute_ale_ma(template_data.shape, np.atleast_2d(peak), kernel)
        for peak in ground_truth_foci_ijks
        if peak.size
    }

    # get study specific instances of each foci
    signal_studies = int(round(foci_percentage * n_studies))
    signal_ijks = {
        peak: np.argwhere(prob_map)[
            rng.choice(
                np.argwhere(prob_map).shape[0],
                size=signal_studies,
                replace=True,
                p=prob_map[np.nonzero(prob_map)] / sum(prob_map[np.nonzero(prob_map)]),
            )
        ]
        for peak, prob_map in foci_prob_maps.items()
    }

    # reshape foci coordinates to be study specific
    paired_signal_ijks = (
        np.transpose(np.array(list(signal_ijks.values())), axes=(1, 0, 2))
        if signal_ijks
        else (None,)
    )

    foci_dict = {}
    for study_signal_ijks, study in zip_longest(paired_signal_ijks, range(n_studies)):
        if study_signal_ijks is None:
            study_signal_ijks = np.array([[]])
            n_noise_foci = max(1, n_noise_foci)

        if n_noise_foci > 0:
            noise_ijks = possible_ijks[
                rng.choice(possible_ijks.shape[0], n_noise_foci, replace=True)
            ]

            # add the noise foci ijks to the existing signal ijks
            foci_ijks = (
                np.unique(np.vstack([study_signal_ijks, noise_ijks]), axis=0)
                if np.any(study_signal_ijks)
                else noise_ijks
            )
        else:
            foci_ijks = study_signal_ijks

        # transform ijk voxel coordinates to xyz mm coordinates
        foci_xyzs = [vox2mm(ijk, template_img.affine) for ijk in foci_ijks]
        foci_dict[study] = foci_xyzs

    ground_truth_foci_xyz = [
        tuple(vox2mm(ijk, template_img.affine)) for ijk in ground_truth_foci_ijks if np.any(ijk)
    ]
    return ground_truth_foci_xyz, foci_dict


def _array_like(obj):
    """Test if obj is array-like"""
    return isinstance(obj, (list, tuple, np.ndarray))


def _create_nii_file(arr, mask, affine, out_dir, prefix):
    brain_stat = np.zeros(mask.shape)
    brain_stat[mask] = arr
    stat_img = nib.Nifti1Image(brain_stat, affine)
    stat_path = out_dir / (prefix + ".nii.gz")
    stat_img.to_filename(stat_path)

    return str(stat_path)


def _download_img(term):

    url = "https://neurosynth.org/api/analyses/{}/images/association"

    image_query = url.format(term)

    data = nib.Nifti1Image.from_bytes(
        gzip.decompress(
            requests.get(image_query).content
        )
    ).get_fdata()

    return data
