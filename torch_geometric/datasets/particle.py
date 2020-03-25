import os.path as osp
import glob

import torch
import pandas
import numpy as np
from torch_scatter import scatter_add
from torch_geometric.data import Data, Dataset


class TrackingData(Data):
    def __inc__(self, key, item):
        if key == 'y_index':
            return torch.tensor([item[0].max().item() + 1, self.num_nodes])
        else:
            return super(TrackingData, self).__inc__(key, item)


class TrackMLParticleTrackingDataset(Dataset):
    r"""The `TrackML Particle Tracking Challenge
    <https://www.kaggle.com/c/trackml-particle-identification>`_ dataset to
    reconstruct particle tracks from 3D points left in the silicon detectors.

    Args:
        root (string): Root directory where the dataset should be saved.
        transform (callable, optional): A function/transform that takes in an
            :obj:`torch_geometric.data.Data` object and returns a transformed
            version. The data object will be transformed before every access.
            (default: :obj:`None`)
    """

    url = 'https://www.kaggle.com/c/trackml-particle-identification'

    def __init__(self, root, transform=None):
        super(TrackMLParticleTrackingDataset, self).__init__(root, transform)
        events = glob.glob(osp.join(self.raw_dir, 'event*-hits.csv'))
        events = [e.split(osp.sep)[-1].split('-')[0][5:] for e in events]
        self.events = sorted(events)

    @property
    def raw_file_names(self):
        event_indices = ['000001000']
        file_names = []
        file_names += [f'event{idx}-cells.csv' for idx in event_indices]
        file_names += [f'event{idx}-hits.csv' for idx in event_indices]
        file_names += [f'event{idx}-particles.csv' for idx in event_indices]
        file_names += [f'event{idx}-truth.csv' for idx in event_indices]
        return file_names

    def download(self):
        raise RuntimeError(
            'Dataset not found. Please download it from {} and move all '
            '*.csv files to {}'.format(self.url, self.raw_dir))

    def len(self):
        return len(glob.glob(osp.join(self.raw_dir, 'event*-hits.csv')))

    def get(self, idx):
        idx = self.events[idx]

        # Get hit positions.
        hits_path = osp.join(self.raw_dir, f'event{idx}-hits.csv')
        pos = pandas.read_csv(hits_path, usecols=['x', 'y', 'z'],
                              dtype=np.float32)
        pos = torch.from_numpy(pos.values).div_(1000.)

        # Get hit features.
        cells_path = osp.join(self.raw_dir, f'event{idx}-cells.csv')
        cells = pandas.read_csv(cells_path, usecols=['hit_id', 'value'])
        hit_id = torch.from_numpy(cells['hit_id'].values).to(torch.long)
        hit_id.sub_(1)
        value = torch.from_numpy(cells['value'].values).to(torch.float)
        ones = torch.ones(hit_id.size(0))
        num_cells = scatter_add(ones, hit_id, dim_size=pos.size(0)).div_(10.)
        value = scatter_add(value, hit_id, dim_size=pos.size(0))
        x = torch.stack([num_cells, value], dim=-1)

        # Get ground-truth hit assignments.
        truth_path = osp.join(self.raw_dir, f'event{idx}-truth.csv')
        y = pandas.read_csv(truth_path, usecols=['particle_id'],
                            dtype=np.int64)
        y = torch.from_numpy(y.values).squeeze()
        y_row = y.unique(return_inverse=True)[1].sub_(1)
        mask = y_row != -1
        y_row = y_row[mask]
        y_col = torch.arange(y.size(0))[mask]
        perm = (y_row * y.size(0) + y_col).argsort()
        y_index = torch.stack([y_row[perm], y_col[perm]], dim=0)

        return TrackingData(x=x, pos=pos, y_index=y_index)