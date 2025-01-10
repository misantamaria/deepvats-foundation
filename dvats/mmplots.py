# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/mstamp.ipynb.

# %% ../nbs/mstamp.ipynb 2
from __future__ import print_function
## -- Deepvats
import dvats.load as load
import dvats.memory as mem
import dvats.utils as ut
##-- MPlots
import stumpy as stump
from stumpy import config as stump_cfg
##-- Utilities
import os
import sys
import numpy as np
import pandas as pd
import datetime as dt
import math
import warnings

##--Fourier Transform
from aeon.segmentation._clasp import ClaSPSegmenter, find_dominant_window_sizes
from aeon.datasets import load_electric_devices_segmentation
from aeon.visualisation import plot_series_with_change_points, plot_series_with_profiles

## -- Classes & types
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Callable

## -- Plotting
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as dates

from matplotlib.gridspec import GridSpec
from matplotlib.patches import Rectangle
from mpl_toolkits.axes_grid1.inset_locator import inset_axes

from mpl_toolkits.axes_grid1 import ImageGrid

## -- Interactive Plots
import ipywidgets as widgets
from IPython.display import display, clear_output


from copy import deepcopy


# %% auto 0
__all__ = ['mSTAMP', 'stomp_mass_pre', 'stomp_mass', 'mstomp']

# %% ../nbs/mstamp.ipynb 4
@dataclass
class mSTAMP:
    """ Computing multi-dimensional MPlot using STAMP """
    #-- Constants & utilities
    _EPS                      : float = 1e-14
    computation_time          : float = 0.0
    
    #-- Parameters
    # Numpy array: input sequence (seq)
    data                      : List [ List [ np.float64 ] ] = None
    # Subsequence length (sub_len)
    subsequence_len           : int                          = None
    
    #-- Outputs
    # Each row, k, contains the k-dimensional MP
    matrix_profile            : List [ List [ int ] ]        = None
    matrix_profile_idx        : List [ List [ int ] ]        = None 
    matrix_profile_dimensions : List [ List [ int ] ]        = None
    dominant_lens             : List [ int ]                 = None    

    def mass_pre(self : 'mSTAMP', seq, sub_len):
        """ pre-computation for iterative call to MASS

        Parameters
        ----------
        seq : numpy array
            input sequence
        sub_len : int
            subsequence length

        Returns
        -------
        seq_freq : numpy array
            sequence in frequency domain
        seq_mu : numpy array
            each subsequence's mu (mean)
        seq_sig : numpy array
            each subsequence's sigma (standard deviation)

        Notes
        -----
        This functions is modified from the code provided in the following URL
        http://www.cs.unm.edu/~mueen/FastestSimilaritySearch.html
        """
        seq_len = len(seq)
        seq_pad = np.zeros(seq_len * 2)
        seq_pad[0:seq_len] = seq
        seq_freq = np.fft.fft(seq_pad)
        seq_cum = np.cumsum(seq_pad)
        seq_sq_cum = np.cumsum(np.square(seq_pad))
        seq_sum = (seq_cum[sub_len - 1:seq_len] -
                   np.concatenate(([0], seq_cum[0:seq_len - sub_len])))
        seq_sq_sum = (seq_sq_cum[sub_len - 1:seq_len] -
                      np.concatenate(([0], seq_sq_cum[0:seq_len - sub_len])))
        seq_mu = seq_sum / sub_len
        seq_sig_sq = seq_sq_sum / sub_len - np.square(seq_mu)
        seq_sig = np.sqrt(seq_sig_sq)
        return seq_freq, seq_mu, seq_sig

    def mass(
            self     : 'mSTAMP', 
            seq_freq, que, seq_len, sub_len, seq_mu, seq_sig):
        """ iterative call of MASS
    
        Parameters
        ----------
        seq_freq : numpy array
            sequence in frequency domain
        que : numpy array
            query
        seq_len : int
            sequence length
        sub_len : int
            subsequence length
        seq_mu : numpy array
            each subsequence's mu (mean)
        seq_sig : numpy array
            each subsequence's sigma (standard deviation)
    
        Returns
        -------
        dist_profile : numpy array
            distance profile
        que_sig : float64
            query's sigma (standard deviation)
    
        Notes
        -----
        This functions is modified from the code provided in the following URL
        http://www.cs.unm.edu/~mueen/FastestSimilaritySearch.html
        """
        que = que[::-1]
        que_pad = np.zeros(seq_len * 2)
        que_pad[0:sub_len] = que
        que_freq = np.fft.fft(que_pad)
        product_freq = seq_freq * que_freq
        product = np.fft.ifft(product_freq)
        product = np.real(product)

        que_sum = np.sum(que)
        que_sq_sum = np.sum(np.square(que))
        que_mu = que_sum / sub_len
        que_sig_sq = que_sq_sum / sub_len - que_mu**2
        if que_sig_sq < _EPS:
            que_sig_sq = _EPS
        que_sig = np.sqrt(que_sig_sq)

        dist_profile = (2 * (sub_len - (product[sub_len - 1:seq_len] -
                                        sub_len * seq_mu * que_mu) /
                             (seq_sig * que_sig)))
        return dist_profile, que_sig
    
    def compute(
        self    : 'mSTAMP', 
        seq     : List[ int ]  = None, 
        sub_len : int          = None, 
        return_dimension: bool = False,
        verbose : int          = 0
    ):
        """ multidimensional matrix profile with mSTAMP (stamp based)

        Parameters
        ----------
        seq : numpy matrix, shape (n_dim, seq_len)
            input sequence
        sub_len : int
            subsequence length
        return_dimension : bool
            if True, also return the matrix profile dimension. It takses O(d^2 n)
            to store and O(d^2 n^2) to compute. (default is False)

        Returns
        -------
        matrix_profile : numpy matrix, shape (n_dim, sub_num)
            matrix profile
        profile_index : numpy matrix, shape (n_dim, sub_num)
            matrix profile index
        profile_dimension : list, optional, shape (n_dim)
            matrix profile dimension, this is only returned when return_dimension
            is True
    
        Notes
        -----
        C.-C. M. Yeh, N. Kavantzas, and E. Keogh, "Matrix Profile VI: Meaningful
        Multidimensional Motif Discovery," IEEE ICDM 2017.
        https://sites.google.com/view/mstamp/
        http://www.cs.ucr.edu/~eamonn/MatrixProfile.html
        """
        
        if self.data is None or seq is not None: 
            self.data = seq
            if verbose > 1: print(f"Updating data~{self.data.shape}")
        elif self.data is not None and seq is None :
            seq = self.data
            if verbose > 1: print(f"Updating seq~{seq.shape}")
        else: 
            print(f"Nothing computed. You must define the data sequence")
            return None, None
            
        if self.subsequence_len is None or sub_len is not None: 
            if verbose > 1:
                print(f"Updating len {self.subsequence_len}")
            self.subsequence_len = sub_len
        elif self.subsequence_len is not None and sub_len is None:
            sub_len = self.subsequence_len
        else:
            print(f"Nothing computed. You must define the subsequence length")
            return None, None
            
            
        if verbose > 0:
            print(f"mSTAMP | Compute | data~{self.data.shape}, sub_len = {self.subsequence_len}")

            
        if self.subsequence_len < 4:
            raise RuntimeError('Subsequence length (sub_len) must be at least 4')
            
        exc_zone = sub_len // 2
        seq = np.array(seq, dtype=float, copy=True)
    
        if seq.ndim == 1:
            seq = np.expand_dims(seq, axis=0)
    
        seq_len = seq.shape[1]
        sub_num = seq.shape[1] - sub_len + 1
        n_dim = seq.shape[0]
        skip_loc = np.zeros(sub_num, dtype=bool)
        for i in range(sub_num):
            if not np.all(np.isfinite(seq[:, i:i + sub_len])):
                skip_loc[i] = True
        seq[~np.isfinite(seq)] = 0
    
        matrix_profile = np.empty((n_dim, sub_num))
        matrix_profile[:] = np.inf
        profile_index = -np.ones((n_dim, sub_num), dtype=int)
        seq_freq = np.empty((n_dim, seq_len * 2), dtype=np.complex128)
        seq_mu = np.empty((n_dim, sub_num))
        seq_sig = np.empty((n_dim, sub_num))
        if return_dimension:
            profile_dimension = []
            for i in range(n_dim):
                profile_dimension.append(np.empty((i + 1, sub_num), dtype=int))
        for i in range(n_dim):
            seq_freq[i, :], seq_mu[i, :], seq_sig[i, :] = \
                self.mass_pre(seq[i, :], sub_len)
    
        dist_profile = np.empty((n_dim, sub_num))
        que_sig = np.empty(n_dim)
        tic = time.time()
        for i in range(sub_num):
            cur_prog = (i + 1) / sub_num
            time_left = ((time.time() - tic) / (i + 1)) * (sub_num - i - 1)
            print('\rProgress [{0:<50s}] {1:5.1f}% {2:8.1f} sec'
                  .format('#' * int(cur_prog * 50),
                          cur_prog * 100, time_left), end="")
            for j in range(n_dim):
                que = seq[j, i:i + sub_len]
                dist_profile[j, :], que_sig[j] = self.mass(
                seq_freq[j, :], que, seq_len, sub_len,
                seq_mu[j, :], seq_sig[j, :])
    
            if skip_loc[i] or np.any(que_sig < _EPS):
                continue
    
            exc_zone_st = max(0, i - exc_zone)
            exc_zone_ed = min(sub_num, i + exc_zone)
            dist_profile[:, exc_zone_st:exc_zone_ed] = np.inf
            dist_profile[:, skip_loc] = np.inf
            dist_profile[seq_sig < _EPS] = np.inf
            dist_profile = np.sqrt(dist_profile)
    
            dist_profile_dim = np.argsort(dist_profile, axis=0)
            dist_profile_sort = np.sort(dist_profile, axis=0)
            dist_profile_cumsum = np.zeros(sub_num)
            for j in range(n_dim):
                dist_profile_cumsum += dist_profile_sort[j, :]
                dist_profile_mean = dist_profile_cumsum / (j + 1)
                update_pos = dist_profile_mean < matrix_profile[j, :]
                profile_index[j, update_pos] = i
                matrix_profile[j, update_pos] = dist_profile_mean[update_pos]
                if return_dimension:
                    profile_dimension[j][:, update_pos] = \
                        dist_profile_dim[:j + 1, update_pos]
    
        # matrix_profile = np.sqrt(matrix_profile)
        if return_dimension:
            return matrix_profile, profile_index, profile_dimension
        else:
            return matrix_profile, profile_index

        def find_top_k_dimensions(profile_dimension, k=3):
            # Flatten the profile_dimension list and count occurrences of each dimension
            dim_counts = np.zeros(len(profile_dimension), dtype=int)
            for dim_array in profile_dimension:
                for dims in dim_array.T:
                    for dim in dims:
                        dim_counts[dim] += 1
    
            # Find the top-k dimensions
            top_k_dims = np.argsort(dim_counts)[-k:][::-1]
            return top_k_dims
        
        def plot_motifs(dimensionality=1):
            motif_at   = self.matrix_profile[dimensionality - 1, :].argsort()[:2]
            discord_at = self.matrix_profile[dimensionality - 1, :].argsort()[-2:]
            print("Motifs")
            plt.figure(figsize=(14, 7))
            for i in range(3):
                plt.subplot(4, 1, i + 1)
                plt.plot(self.data.T[dimensions[i], :])
                plt.title('$T-{}$'.format(dimensions[i] + 1))
                for m in motif_at:
                    plt.plot(range(m, m + sub_len), self.data.T[dimensions[i], :][m:m + self.subsequence_len], c='r')
                plt.xlim((0, self.matrix_profile.shape[1]))

            plt.subplot(414)
            plt.title('{}-dimensional Matrix Profile'.format(dimensionality))
            plt.plot(self.matrix_profile[dimensionality - 1, :])
            for m in motif_at:
                plt.axvline(m, c='r')
            plt.xlim((0, self.matrix_profile.shape[1]))
            plt.tight_layout()
            plt.show()
            print("Discord")
            plt.close("all")
            plt.figure(figsize=(14, 7))
            for i in range(3):
                plt.subplot(4, 1, i + 1)
                plt.plot(self.data.T[dimensions[i], :])
                plt.title('$T-{}$'.format(dimensions[i] + 1))
                for m in discord_at:
                    plt.plot(range(m, m + self.subsequence_len), self.data.T[dimensions[i], :][m:m + self.subsequence_len], c='r')
                plt.xlim((0, matrix_profile.shape[1]))
        
            plt.subplot(414)
            plt.title('{}-dimensional Matrix Profile'.format(dimensionality))
            plt.plot(self.matrix_profile[dimensionality - 1, :])
            for m in discord_at:
                plt.axvline(m, c='r')
            plt.xlim((0, self.matrix_profile.shape[1]))
            plt.tight_layout()
            plt.show()
            return motif_at, discord_at

# %% ../nbs/mstamp.ipynb 16
def stomp_mass_pre(seq, sub_len):
    """ pre-computation for iterative call to MASS

    Parameters
    ----------
    seq : numpy array
        input sequence
    sub_len : int
        subsequence length

    Returns
    -------
    seq_freq : numpy array
        sequence in frequency domain
    seq_mu : numpy array
        each subsequence's mu (mean)
    seq_sig : numpy array
        each subsequence's sigma (standard deviation)

    Notes
    -----
    This functions is modified from the code provided in the following URL
    http://www.cs.unm.edu/~mueen/FastestSimilaritySearch.html
    """
    seq_len = len(seq)
    seq_pad = np.zeros(seq_len * 2)
    seq_pad[0:seq_len] = seq
    seq_freq = np.fft.fft(seq_pad)
    seq_cum = np.cumsum(seq_pad)
    seq_sq_cum = np.cumsum(np.square(seq_pad))
    seq_sum = (seq_cum[sub_len - 1:seq_len] -
               np.concatenate(([0], seq_cum[0:seq_len - sub_len])))
    seq_sq_sum = (seq_sq_cum[sub_len - 1:seq_len] -
                  np.concatenate(([0], seq_sq_cum[0:seq_len - sub_len])))
    seq_mu = seq_sum / sub_len
    seq_sig_sq = seq_sq_sum / sub_len - np.square(seq_mu)
    seq_sig = np.sqrt(seq_sig_sq)
    return seq_freq, seq_mu, seq_sig


# %% ../nbs/mstamp.ipynb 17
def stomp_mass(seq_freq, que, seq_len, sub_len, seq_mu, seq_sig):
    """ iterative call of MASS

    Parameters
    ----------
    seq_freq : numpy array
        sequence in frequency domain
    que : numpy array
        query
    seq_len : int
        sequence length
    sub_len : int
        subsequence length
    seq_mu : numpy array
        each subsequence's mu (mean)
    seq_sig : numpy array
        each subsequence's sigma (standard deviation)

    Returns
    -------
    dist_profile : numpy array
        distance profile
    last_product : numpy array
        cross term
    que_sum : float64
        query's sum
    que_sq_sum : float64
        query's squre sum
    que_sig : float64
        query's sigma (standard deviation)

    Notes
    -----
    This functions is modified from the code provided in the following URL
    http://www.cs.unm.edu/~mueen/FastestSimilaritySearch.html
    """
    que = que[::-1]
    que_pad = np.zeros(seq_len * 2)
    que_pad[0:sub_len] = que
    que_freq = np.fft.fft(que_pad)
    product_freq = seq_freq * que_freq
    product = np.fft.ifft(product_freq)
    product = np.real(product)

    que_sum = np.sum(que)
    que_sq_sum = np.sum(np.square(que))
    que_mu = que_sum / sub_len
    que_sig_sq = que_sq_sum / sub_len - que_mu**2
    if que_sig_sq < _EPS:
        que_sig_sq = _EPS
    que_sig = np.sqrt(que_sig_sq)

    dist_profile = (2 * (sub_len - (product[sub_len - 1:seq_len] -
                                    sub_len * seq_mu * que_mu) /
                         (seq_sig * que_sig)))
    last_product = product[sub_len - 1:seq_len]
    return dist_profile, last_product, que_sum, que_sq_sum, que_sig

# %% ../nbs/mstamp.ipynb 18
def mstomp(seq, sub_len, return_dimension=False):
    """ multidimensional matrix profile with mSTAMP (stomp based)

    Parameters
    ----------
    seq : numpy matrix, shape (n_dim, seq_len)
        input sequence
    sub_len : int
        subsequence length
    return_dimension : bool
        if True, also return the matrix profile dimension. It takses O(d^2 n)
        to store and O(d^2 n^2) to compute. (default is False)

    Returns
    -------
    matrix_profile : numpy matrix, shape (n_dim, sub_num)
        matrix profile
    profile_index : numpy matrix, shape (n_dim, sub_num)
        matrix profile index
    profile_dimension : list, optional, shape (n_dim)
        matrix profile dimension, this is only returned when return_dimension
        is True

    Notes
    -----
    C.-C. M. Yeh, N. Kavantzas, and E. Keogh, "Matrix Profile VI: Meaningful
    Multidimensional Motif Discovery," IEEE ICDM 2017.
    https://sites.google.com/view/mstamp/
    http://www.cs.ucr.edu/~eamonn/MatrixProfile.html
    """
    if sub_len < 4:
        raise RuntimeError('Subsequence length (sub_len) must be at least 4')
    exc_zone = sub_len // 2
    seq = np.array(seq, dtype=float, copy=True)

    if seq.ndim == 1:
        seq = np.expand_dims(seq, axis=0)

    seq_len = seq.shape[1]
    sub_num = seq.shape[1] - sub_len + 1
    n_dim = seq.shape[0]
    skip_loc = np.zeros(sub_num, dtype=bool)
    for i in range(sub_num):
        if not np.all(np.isfinite(seq[:, i:i + sub_len])):
            skip_loc[i] = True
    seq[~np.isfinite(seq)] = 0

    drop_val = 0
    matrix_profile = np.empty((n_dim, sub_num))
    matrix_profile[:] = np.inf
    profile_index = -np.ones((n_dim, sub_num), dtype=int)
    seq_freq = np.empty((n_dim, seq_len * 2), dtype=np.complex128)
    seq_mu = np.empty((n_dim, sub_num))
    seq_sig = np.empty((n_dim, sub_num))
    if return_dimension:
        profile_dimension = []
        for i in range(n_dim):
            profile_dimension.append(np.empty((i + 1, sub_num), dtype=int))
    for i in range(n_dim):
        seq_freq[i, :], seq_mu[i, :], seq_sig[i, :] = \
            stomp_mass_pre(seq[i, :], sub_len)

    dist_profile = np.empty((n_dim, sub_num))
    last_product = np.empty((n_dim, sub_num))
    first_product = np.empty((n_dim, sub_num))
    drop_val = np.empty(n_dim)
    que_sum = np.empty(n_dim)
    que_sq_sum = np.empty(n_dim)
    que_sig = np.empty(n_dim)
    tic = time.time()
    for i in range(sub_num):
        cur_prog = (i + 1) / sub_num
        time_left = ((time.time() - tic) / (i + 1)) * (sub_num - i - 1)
        print('\rProgress [{0:<50s}] {1:5.1f}% {2:8.1f} sec'
              .format('#' * int(cur_prog * 50),
                      cur_prog * 100, time_left), end="")
        for j in range(n_dim):
            que = seq[j, i:i + sub_len]
            if i == 0:
                (dist_profile[j, :], last_product[j, :],
                 que_sum[j], que_sq_sum[j], que_sig[j]) = \
                    stomp_mass(seq_freq[j, :], que, seq_len, sub_len,
                          seq_mu[j, :], seq_sig[j, :])
                first_product[j, :] = last_product[j, :].copy()
            else:
                que_sum[j] = que_sum[j] - drop_val[j] + que[-1]
                que_sq_sum[j] = que_sq_sum[j] - drop_val[j]**2 + que[-1]**2
                que_mu = que_sum[j] / sub_len
                que_sig_sq = que_sq_sum[j] / sub_len - que_mu**2
                if que_sig_sq < _EPS:
                    que_sig_sq = _EPS
                que_sig[j] = np.sqrt(que_sig_sq)
                last_product[j, 1:] = (last_product[j, 0:-1] -
                                       seq[j, 0:seq_len - sub_len] *
                                       drop_val[j] +
                                       seq[j, sub_len:seq_len] * que[-1])
                last_product[j, 0] = first_product[j, i]
                dist_profile[j, :] = \
                    (2 * (sub_len - (last_product[j, :] -
                                     sub_len * seq_mu[j, :] * que_mu) /
                          (seq_sig[j, :] * que_sig[j])))
                dist_profile[j, dist_profile[j, :] < _EPS] = 0
            drop_val[j] = que[0]

        if skip_loc[i] or np.any(que_sig < _EPS):
            continue

        exc_zone_st = max(0, i - exc_zone)
        exc_zone_ed = min(sub_num, i + exc_zone)
        dist_profile[:, exc_zone_st:exc_zone_ed] = np.inf
        dist_profile[:, skip_loc] = np.inf
        dist_profile[seq_sig < _EPS] = np.inf
        dist_profile = np.sqrt(dist_profile)

        dist_profile_dim = np.argsort(dist_profile, axis=0)
        dist_profile_sort = np.sort(dist_profile, axis=0)
        dist_profile_cumsum = np.zeros(sub_num)
        for j in range(n_dim):
            dist_profile_cumsum += dist_profile_sort[j, :]
            dist_profile_mean = dist_profile_cumsum / (j + 1)
            update_pos = dist_profile_mean < matrix_profile[j, :]
            profile_index[j, update_pos] = i
            matrix_profile[j, update_pos] = dist_profile_mean[update_pos]
            if return_dimension:
                profile_dimension[j][:, update_pos] = \
                    dist_profile_dim[:j + 1, update_pos]

    # matrix_profile = np.sqrt(matrix_profile)
    if return_dimension:
        return matrix_profile, profile_index, profile_dimension
    else:
        return matrix_profile, profile_index,

