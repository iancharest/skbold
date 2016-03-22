# Function to convert a nifti in MNI space to Epi-space. Only works with
# reg_dir as created by FSL.

# Author: Lukas Snoek [lukassnoek.github.io]
# Contact: lukassnoek@gmail.com
# License: 3 clause BSD

import os
import os.path as op
from nipype.interfaces import fsl


def convert2epi(f, reg_dir, out_dir=None, out_name=None,
                interpolation='trilinear'):
    """ Transforms a nifti from mni152 (2mm) to EPI (native) format.

    Assuming that reg_dir is a directory with transformation-files (warps)
    including standard2example_func warps, this function uses nipype's
    fsl interface to flirt a nifti to EPI format.

    Parameters
    ----------
    f : str
        Absolute path to nifti file that needs to be transformed
    reg_dir : str
        Absolute path to registration directory with warps
    out_dir : str
        Absolute path to desired out directory. Default is same directory as
        the to-be transformed file.
    out_name : str
        Name for transformed file. Default is basename of file to-be transformed
        + '_mni'.
    interpolation : str
        Interpolation used by flirt. Default is 'trilinear'.

    Returns
    -------
    out_file : str
        Absolute path to newly transformed file.

    To do: calculate warp if reg_dir doesn't exist
    """

    if out_dir is None:
        out_dir = op.dirname(f)
        if out_name is None:
            out_name = op.basename(f).split('.')[0] + '_epi.nii.gz'
            out_file = op.join(out_dir, out_name)
        else:
            out_file = op.join(out_dir, out_name + '.nii.gz')
    else:
        if out_name is None:
            out_name = op.basename(f).split('.')[0] + '_epi.nii.gz'
        else:
            out_name += '.nii.gz'

        out_file = op.join(out_dir, out_name)

    out_matrix_file = op.join(op.dirname(out_file), 'tmp_flirt')
    ref_file = op.join(reg_dir, 'example_func.nii.gz')
    matrix_file = op.join(reg_dir, 'standard2example_func.mat')
    apply_xfm = fsl.ApplyXfm()
    apply_xfm.inputs.in_file = f
    apply_xfm.inputs.reference = ref_file
    apply_xfm.inputs.in_matrix_file = matrix_file
    apply_xfm.inputs.out_matrix_file = out_matrix_file
    apply_xfm.interp = interpolation
    apply_xfm.inputs.out_file = out_file
    apply_xfm.inputs.apply_xfm = True
    apply_xfm.run()

    os.remove(out_matrix_file)

    return out_file
