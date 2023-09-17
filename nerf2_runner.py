# -*- coding: utf-8 -*-
"""NeRF2 runner for training and testing
"""

import os

os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"

import argparse
from shutil import copyfile

import torch
import torch.optim as optim
import yaml
from tensorboardX import SummaryWriter
from torch.utils.data import DataLoader
from tqdm import tqdm, trange

from dataloader import Spectrum_dataset, split_dataset
from utils.logger import logger_config
from model import *
# from model import NeRF2
from renderer import Renderer


class NeRF2_Runner():

    def __init__(self, mode, **kwargs) -> None:


        kwargs_path = kwargs['path']
        kwargs_render = kwargs['render']
        kwargs_network = kwargs['networks']
        kwargs_train = kwargs['train']

        ## Path settings
        self.expname = kwargs_path['expname']
        self.datadir = kwargs_path['datadir']
        self.logdir = kwargs_path['logdir']
        self.devices = torch.device('cuda')

        ## Logger
        log_filename = "logger.log"
        log_savepath = os.path.join(self.logdir, self.expname, log_filename)
        self.logger = logger_config(log_savepath=log_savepath, logging_name='locgpt')
        self.logger.info("expname:%s, datadir:%s, logdir:%s", self.expname, self.datadir, self.logdir)
        self.writer = SummaryWriter(os.path.join(self.logdir, self.expname, 'tensorboard'))


        ## Networks
        self.nerf2_network = NeRF2(**kwargs_network).to(self.devices)
        params = list(self.nerf2_network.parameters())
        self.optimizer = torch.optim.Adam(params, lr=float(kwargs_train['lr']),
                                          weight_decay=float(kwargs_train['weight_decay']),
                                          betas=(0.9, 0.999))
        self.cosine_scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer=self.optimizer,
                                                                        T_max=float(kwargs_train['T_max']), eta_min=float(kwargs_train['eta_min']),
                                                                        last_epoch=-1)

        self.renderer = Renderer(networks_fn=self.nerf2_network, **kwargs_render)

        total_params = sum(p.numel() for p in params if p.requires_grad)
        self.logger.info("Total number of parameters: %s", total_params)


        ## Train Settings
        self.current_epoch, self.global_step = 1, 1
        if kwargs_train['load_ckpt'] or mode == 'test':
            self.load_checkpoints()
        self.batch_size = kwargs_train['batch_size']
        self.total_epoches = kwargs_train['total_epoches']
        self.save_freq = kwargs_train['save_freq']


        ## Dataset
        train_index = os.path.join(self.datadir, "train_index.txt")
        test_index = os.path.join(self.datadir, "test_index.txt")
        if not os.path.exists(train_index) or not os.path.exists(test_index):
            split_dataset(self.datadir, ratio=0.8)
        train_set = Spectrum_dataset(self.datadir, train_index)
        test_set = Spectrum_dataset(self.datadir, test_index)

        self.train_iter = DataLoader(train_set, batch_size=self.batch_size, shuffle=True, num_workers=0)
        self.test_iter = DataLoader(test_set, batch_size=self.batch_size, shuffle=True, num_workers=0)
        self.logger("Train set size:%d, Test set size:%d", len(train_set), len(test_set))


    def load_checkpoints(self):
        """load checkpoints and epoch
        """
        ckptsdir = os.path.join(self.logdir, self.expname, 'ckpts')
        if not os.path.exists(ckptsdir):
            os.makedirs(ckptsdir)
        ckpts = [os.path.join(ckptsdir, f) for f in sorted(os.listdir(ckptsdir)) if 'tar' in f]

        print('Found ckpts', ckpts)
        if len(ckpts) > 0:
            ckpt_path = ckpts[-1]
            self.logger.info('Loading ckpt %s', ckpt_path)
            ckpt = torch.load(ckpt_path, map_location=self.devices)

            self.nerf2_network.load_state_dict(ckpt['nerf2_network_state_dict'])
            self.optimizer.load_state_dict(ckpt['optimizer_state_dict'])
            self.cosine_scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer=self.optimizer,T_max=20,eta_min=1e-5)
            self.cosine_scheduler.load_state_dict(ckpt['scheduler_state_dict'])
            self.current_epoch = ckpt['current_epoch']
            self.global_step = ckpt['global_step']


    def save_checkpoint(self):
        """load checkpoints and epoch
        """
        ckptsdir = os.path.join(self.logdir, self.expname, 'ckpts')
        model_lst = [x for x in sorted(os.listdir(ckptsdir)) if x.endswith('.tar')]
        if len(model_lst) > 2:
            os.remove(ckptsdir + '/%s' % model_lst[0])

        ckptname = os.path.join(ckptsdir, '{:06d}.tar'.format(self.current_epoch))
        torch.save({
            'current_epoch': self.current_epoch,
            'global_step': self.global_step,
            'nerf2_network_state_dict': self.nerf2_network.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'scheduler_state_dict': self.cosine_scheduler.state_dict()
        }, ckptname)
        self.logger.info('Saved checkpoints at %s', ckptname)


    def train(self):
        """train the model
        """

        self.logger.info("Start training. Current Epoch:%d", self.current_epoch)
        for epoch in range(self.current_epoch, self.total_epoches + 1):
            with tqdm(total=len(self.train_iter), desc=f"Epoch {epoch}/{self.total_epoches}") as pbar:
                for train_input, train_label in self.train_iter:
                    train_input, train_label = train_input.to(self.devices), train_label.to(self.devices)
                    rays_o, rays_d, tx_o = train_input[:, :3], train_input[:, 3:6], train_input[:, 6:9]
                    predict_spectrum = self.renderer.render_ss(tx_o, rays_o, rays_d)

                    loss = img2mse(predict_spectrum, train_label.view(-1))
                    self.optimizer.zero_grad()
                    loss.backward()
                    self.optimizer.step()
                    self.cosine_scheduler.step()
                    self.global_step += 1

                    self.writer.add_scalar('Loss/loss', loss, self.global_step)
                    pbar.update(1)
                    pbar.set_postfix_str('loss = {:.4f}, lr = {:.8f}'.format(loss.item(), self.optimizer.param_groups[0]['lr']))

                if epoch % self.save_freq == 0:
                    self.save_checkpoint()





if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=str, default='configs/spectrum.yml', help='config file path')
    parser.add_argument('--gpu', type=int, default=0)
    parser.add_argument('--mode', type=str, default='train')
    args = parser.parse_args()
    torch.cuda.set_device(args.gpu)

    with open(args.config) as f:
        kwargs = yaml.safe_load(f)
        f.close()

    ## backup config file
    if args.mode == 'train':
        logdir = os.path.join(kwargs['path']['logdir'], kwargs['path']['expname'])
        os.makedirs(logdir, exist_ok=True)
        copyfile(args.config, os.path.join(logdir,'config.yml'))

    worker = NeRF2_Runner(mode=args.mode, **kwargs)
    if args.mode == 'train':
        worker.train()