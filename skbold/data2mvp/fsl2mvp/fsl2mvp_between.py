# Class to extract and store first-level (meta)data from an FSL first-level
# (feat) directory.

# Author: Lukas Snoek [lukassnoek.github.io]
# Contact: lukassnoek@gmail.com
# License: 3 clause BSD

from __future__ import print_function, division, absolute_import
import cPickle
import h5py
import shutil
import numpy as np
import nibabel as nib
import pandas as pd
import os
from glob import glob
import os.path as op
from skbold.utils import sort_numbered_list
from skbold.data2mvp.fsl2mvp import Fsl2mvp
from sklearn.preprocessing import LabelEncoder
from skbold.core import convert2mni, convert2epi


class Fsl2mvpBetween(Fsl2mvp):
    """ Fsl2mvp (multiVoxel Pattern) class, a subclass of Mvp (skbold.core)

    Creates an object, specialized for storing fMRI data that will be analyzed
    using machine learning or RSA-like analyses, that stores both the data
    (X: an array of samples by features, y: numeric labels corresponding to
    X's classes/conditions) and the corresponding meta-data (e.g. nifti header,
    mask info, etc.).
    """

    def __init__(self, directory, output_var_file=None, mask_threshold=0, beta2tstat=True,
                 ref_space='mni', mask_path=None, remove_contrast=[], invert_selection=False):

        super(Fsl2mvpBetween, self).__init__(directory=directory,
                                             mask_threshold=mask_threshold,
                                             beta2tstat=beta2tstat,
                                             remove_contrast=remove_contrast,
                                             ref_space=ref_space,
                                             mask_path=mask_path,
                                             invert_selection=invert_selection)

        self.output_var_file = output_var_file
#        self.X_dict = {}
        self.contrast_id = np.zeros(0, dtype=np.uint8)
        self.contrast_labels = None
        self.n_cope = None
        self.n_runs = None

    def _update_metadata(self):
        contrasts = self.contrast_labels
        self.n_contrast = len(contrasts)
        self.contrast_names = np.unique(contrasts)

    # def _update_X_dict(self, mvp_meta):
    #     for key, value in mvp_meta.iteritems():
    #         mvp_meta[key] = value + len(self.X_dict) * self.n_features
    #
    #     self.X_dict.update(mvp_meta)

    def _add_outcome_var(self, filename):
        file_path = op.join(op.dirname(self.directory), filename)

        with open(file_path, 'rb') as f:
            y = float(f.readline())
        self.y = np.array(y)

    def glm2mvp(self, extract_labels=True):

        """ Extract (meta)data from FSL first-level directory.

        This method extracts the class labels (y) and corresponding data
        (single-trial patterns; X) from a FSL first-level directory and
        subsequently stores it in the attributes of self.

        """
        sub_path = self.directory
        sub_name = self.sub_name

        reg_dir = op.join(sub_path, 'reg')

        # Load mask, create index
        if self.mask_path is not None:
            mask_vol = nib.load(self.mask_path)

            if self.ref_space == 'epi' and mask_vol.shape == (91, 109, 91):
                # In this case, we need to transform mask to epi-space
                self.mask_path = convert2epi(self.mask_path, reg_dir, out_dir=reg_dir)[0]
                mask_vol = nib.load(self.mask_path)

            self.mask_shape = mask_vol.shape
            self.mask_index = mask_vol.get_data().ravel() > self.mask_threshold
            self.n_features = self.mask_index.sum()

        mat_dir = op.join(op.dirname(sub_path), 'mvp_data')
        n_feat = len(glob(op.join(os.path.dirname(sub_path), '*.feat')))
        n_converted = len(glob(op.join(mat_dir, '*header*')))

        # Ugly hack to remove existing mvp_data dir and start over
        if op.exists(mat_dir) and n_feat <= n_converted:
            shutil.rmtree(mat_dir)
            os.makedirs(mat_dir)
            n_converted = 0
        elif not op.exists(mat_dir):
            os.makedirs(mat_dir)

        # Extract class vector (class_labels)
        if extract_labels:
            self._extract_labels()

        if self.output_var_file is not None:
            self._add_outcome_var(self.output_var_file)

        # Update metadata, excluding X_dict
        self._update_metadata()

        print('Processing %s (run %i / %i)...' % (sub_name, n_converted + 1,
                                                      n_feat), end='')

        # Specify appropriate stats-directory
        if self.ref_space == 'epi':
            stat_dir = op.join(sub_path, 'stats')
        elif self.ref_space == 'mni':
            stat_dir = op.join(sub_path, 'reg_standard')
        else:
            raise ValueError('Specify valid reference-space (ref_space),' \
                             'choose from: %r' % ['epi', 'mni'])

        if self.ref_space == 'mni' and not op.isdir(stat_dir):
            stat_dir = op.join(sub_path, 'stats')
            transform2mni = True
        else:
            transform2mni = False

        copes = glob(op.join(stat_dir, 'cope*.nii.gz'))
        varcopes = glob(op.join(stat_dir, 'varcope*.nii.gz'))
        copes, varcopes = sort_numbered_list(copes), sort_numbered_list(varcopes)

        # Moved this from below transform2mni, so that it may save computation time
        _ = [copes.pop(idx) for idx in sorted(self.remove_idx, reverse=True)]

        varcopes = sort_numbered_list(varcopes)
        _ = [varcopes.pop(ix) for ix in sorted(self.remove_idx, reverse=True)]

        if transform2mni:
            copes.extend(varcopes)
            out_dir = op.join(sub_path, 'reg_standard')
            transformed_files = convert2mni(copes, reg_dir, out_dir)
            half = int(len(transformed_files) / 2)
            copes, varcopes = transformed_files[:half], transformed_files[half:]

        # We need to 'peek' at the first cope to know the dimensions
        if self.mask_path is None:
            tmp = nib.load(copes[0]).get_data()
            self.n_features = tmp.size
            self.mask_index = np.ones(tmp.shape, dtype=bool).ravel()
            self.mask_shape = tmp.shape

        columns = self.n_features * len(self.contrast_labels)

        # Pre-allocate
        mvp_data = np.zeros(columns)

        # Load in data (COPEs)
        for i, (cope, varcope) in enumerate(zip(copes, varcopes)):
            cope_img = nib.load(cope)
            cope_shape = cope_img.header.get_data_shape()
            copedat = cope_img.get_data().ravel()[self.mask_index]

            vox_idx = np.arange(np.prod(cope_shape, dtype=np.uint32), dtype=np.uint32).reshape(cope_shape).ravel()[self.mask_index]

            if self.beta2tstat:
                var = nib.load(varcope).get_data()
                var_sq = np.sqrt(var.ravel()[self.mask_index])
                copedat = np.divide(copedat, var_sq)

            mvp_data[(i * self.n_features):(i*self.n_features + self.n_features)] = copedat
            self.contrast_id = np.concatenate((self.contrast_id, np.ones(self.n_features, dtype=np.uint8) * i), axis=0)
            self.voxel_idx = np.concatenate((self.voxel_idx, vox_idx))

#            mvp_meta[self.contrast_labels[i]] = np.array([(i * self.n_features), (i*self.n_features + self.n_features)])

        mvp_data[np.isnan(mvp_data)] = 0
        self.nifti_header = cope_img.header  # pick header from last cope
        self.affine = cope_img.affine
#        self._update_X_dict(mvp_meta)

        fn_header = op.join(mat_dir, '%s_header_run%i.pickle' % (self.sub_name,
                            n_converted+1))

        with open(fn_header, 'wb') as handle:
            cPickle.dump(self, handle)


        fn_data = op.join(mat_dir, '%s_data_run%i.hdf5' % (self.sub_name,
                          n_converted+1))

        h5f = h5py.File(fn_data, 'w')
        h5f.create_dataset('data', data=mvp_data)
        h5f.close()
        self.X = mvp_data

        print(' done.')

        return self

    def glm2mvp_and_merge(self):
        """ Chains glm2mvp() and merge_runs(). """
        self.glm2mvp().merge_runs()
        return self


if __name__ == '__main__':
    import skbold.utils
    from skbold import DataHandler
    import os.path as op
    from glob import glob

    feat_dir = '/users/steven/Desktop/pioptest'
    subs = glob(op.join(feat_dir, 'pi*'))
    gm_mask = op.join(op.dirname(skbold.__file__), 'data', 'ROIs', 'GrayMatter.nii.gz')

    copes = {'wm': ['act-pas', 'act'],
             'harriri': ['emo-control'],
             'gstroop': ['con-incon']}

    # loop over subjects & tasks
    for sub in subs:
        tasks = glob(op.join(sub, '*.feat'))
        tasks = [x for x in tasks if x.split('piop')[-1][:-5] in copes.keys()]
        tasknames = [x.split('piop')[-1][:-5] for x in tasks]

        for (taskdir, taskname) in zip(tasks, tasknames):
            tmp = Fsl2mvpBetween(directory=taskdir, mask_threshold=0, beta2tstat=True,
                                 ref_space='mni', mask_path=gm_mask, remove_contrast=copes[taskname],
                                 invert_selection=True, output_var_file='zraven.txt')
            tmp.glm2mvp()

            # print('\nSub %s, task %s, data (GM-masked):' %(sub[-4:], taskname))
            # print(tmp.X)

        tmp.merge_runs()

    tmp = DataHandler()
    data = tmp.load_concatenated_subs(directory=op.dirname(subs[0]))

    print(data.voxel_idx)
    print(data.voxel_idx.shape)

    print('Merged %s data, GM masked: ' % (data.contrast_labels[0]))
    idx = data.contrast_id == 0
    print(idx.shape)
    print(data.X.shape)
    print(data.X[:, idx])
    print(data.voxel_idx[idx])

    print('\n Merged %s data, GM masked:' % (data.contrast_labels[1]))
    idx = data.contrast_id == 1
    print(data.X[:, idx])
    print(data.voxel_idx[idx])

    print('\n Merged %s data, GM masked:' % (data.contrast_labels[2]))
    idx = data.contrast_id == 2
    print(data.X[:, idx])
    print(data.voxel_idx[idx])


    print(data.y)