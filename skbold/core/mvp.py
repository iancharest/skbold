# Basic Mvp class, from which first-level specific (e.g. FSL or, perhaps in the
# future, SPM) containers/converters are subclassed.

# Author: Lukas Snoek [lukassnoek.github.io]
# Contact: lukassnoek@gmail.com
# License: 3 clause BSD

from __future__ import print_function, absolute_import, division
import glob
import cPickle
import h5py
import numpy as np
import os
import os.path as op
from sklearn.preprocessing import LabelEncoder


class Mvp(object):
    """ Mvp (multiVoxel Pattern) class.

    Creates an object, specialized for storing fMRI data that will be analyzed
    using machine learning or RSA-like analyses, that stores both the data
    (X: an array of samples by features, y: numeric labels corresponding to
    X's classes/conditions) and the corresponding meta-data (e.g. nifti header,
    mask info, etc.).

    """

    def __init__(self, directory, mask_threshold=0, beta2tstat=True,
                 ref_space='mni', mask_path=None):

        """ Initializes a (bare-bones) Mvp object.

        Parameters
        ----------
        directory : str
            Absolute path to directory from which first-level data should be
            extracted.
        mask_threshold : Optional[int or float]
            If a probabilistic mask is used, mask_threshold sets the lower-
            bound for the mask
        beta2tstat : bool
            Whether to convert extracted beta-values to t-statistics by
            dividing by their corresponding standard deviation.
        ref_space : str
            Indicates in which space the multivoxel patterns should be
            returned, either 'mni' (MNI152 2mm space) or 'epi' (native
            functional space). Thus far, MNI space only works for first-level
            data returned by fsl.
        mask_path : str
            Absolute path to the mask that will be used to index the patterns
            with.
        remove_class : list[str]
            List of condition names (or substrings of condition names) that
            need not to be included in the pattern-data (e.g. covariates,
            nuisance regressors, etc.).

        """

        self.directory = directory

        if not op.exists(directory):
            raise OSError("The directory '%s' doesn't seem to exist!" % directory)

        self.sub_name = op.basename(op.dirname(directory))
        self.run_name = op.basename(directory).split('.')[0].split('_')[-1]
        self.ref_space = ref_space
        self.beta2tstat = beta2tstat
        self.mask_path = mask_path
        self.mask_threshold = mask_threshold

        if mask_path is not None:
            self.mask_name = op.basename(op.dirname(mask_path))
        else:
            self.mask_name = 'WholeBrain'

        self.n_features = None

        self.mask_index = None
        self.mask_shape = None

        self.nifti_header = None
        self.affine = None

        self.X = None
        self.y = None

    def update_mask(self, new_idx):

        if new_idx.size != self.mask_index.sum():
            msg = 'Shape of new index (%r) is not the same as the current ' \
                    'pattern (%r)!' % (new_idx.size, self.mask_index.sum())
            raise ValueError(msg)

        tmp_idx = np.zeros(self.mask_shape)
        tmp_idx[self.mask_index.reshape(self.mask_shape)] += new_idx
        self.mask_index = tmp_idx.astype(bool).ravel()

    def glm2mvp(self):
        msg = "This method can only be called by subclasses of Mvp!"
        raise ValueError(msg)